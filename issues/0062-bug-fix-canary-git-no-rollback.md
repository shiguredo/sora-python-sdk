# canary.py の git_operations が途中失敗時にローカルとリモートの整合が壊れる問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-canary-git-no-rollback
- Polished: 2026-07-28

## 目的

`canary.py` の `git_operations` は VERSION ファイルを更新後、`git add` → `git commit` → `git tag` → `git push` → `git push --tags` を `check=True` で 5 段直列に実行する。
どこか 1 つでも失敗 (例: `git push` が non-fast-forward で reject される) すると、Python プロセスは例外で停止するが、その時点でローカルには「VERSION の変更コミット」と「リリースタグ」だけが残り、リモートには反映されない状態になる。

この状態から開発者が何も知らずに `git pull` や次の `canary.py` を実行すると、ローカルのリリースコミット・リリースタグが不整合のまま伝搬する。
リリース手順を支える dev 版バンプ専用スクリプトとしての安全性を確保するため、途中失敗時のロールバックまたは事前検証を整備する。

## 優先度根拠

Medium とする。

- canary.py は dev 版バンプ専用 (`[canary] Bump version to ...`) で頻繁に実行されるため、reject される実害は十分に発生し得る。
- ただし発生条件は「リモートが先に更新されている」など限定的で、毎回起きるわけではない。
- 失敗時のリカバリは熟練者であれば数コマンドで戻せるため、即時の本番リリース事故にはならない。
- 一方、リリースに紐づくスクリプトであり「壊れた窓」を残すことの心理的負債は大きいため Low ではなく Medium。

## 現状

`canary.py` の `main()` は `update_version` → `run_uv_sync` → `git_operations` の順に呼び出す。`run_uv_sync` (canary.py:53) が `git add uv.lock` を実行済みであるため、`git_operations` の `git commit` は VERSION と uv.lock の両方をコミットする。

`canary.py:65-72` の実装は次の通り。

```python
else:
    subprocess.run(["git", "add", "VERSION"], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"[canary] Bump version to {new_version}"], check=True
    )
    subprocess.run(["git", "tag", new_version], check=True)
    subprocess.run(["git", "push"], check=True)
    subprocess.run(["git", "push", "--tags"], check=True)
```

各ステップは `check=True` のため、失敗するとそこで例外が上がり後続は実行されない。
失敗パターンと残骸の関係は以下のとおり (uv.lock は `run_uv_sync` により既に staged)。

| 失敗ステップ        | ローカルに残る残骸                          | リモート反映 |
|---------------------|---------------------------------------------|--------------|
| `git add VERSION`   | staged 状態の uv.lock                       | 無し         |
| `git commit`        | staged 状態の VERSION + uv.lock             | 無し         |
| `git tag`           | コミット 1 個 (VERSION + uv.lock)           | 無し         |
| `git push`          | コミット 1 個 + ローカルタグ                | 無し         |
| `git push --tags`   | コミット 1 個 + ローカルタグ + push 済 HEAD | コミットのみ |

`git push` が non-fast-forward で reject されるケースが最も問題で、ローカルに「コミット + タグ」だけが残った状態でリトライしても、リモート反映を取り込まないまま再度 push が試みられて同じ失敗を繰り返す。

## 設計方針

方針 1 (事前検証) + 方針 2 (順序変更) を採用する。方針 3 (自動ロールバック) は採用しない。

1. push 可能性を事前確認してから commit / tag を行う (採用)
   - `git fetch origin` で上流の HEAD を取得し、ローカルがリモートに対して fast-forward 可能な状態 (リモート HEAD がローカル HEAD の祖先であること) を確認してから `git add` / `git commit` / `git tag` を行う。
   - 整合しない場合は早期にエラーメッセージ (「リモートが先行しています。git pull --rebase してから再実行してください」) を出力し、`sys.exit(1)` でコミット・タグを一切作らずに終了する。
2. タグ作成を push 成功後に移動する (採用)
   - 順序を `git add` → `git commit` → `git push` → `git tag` → `git push --tags` に変える。
   - これによりコミット push 失敗時はローカルタグが残らない。
3. 失敗時のロールバック処理 (不採用)
   - `git reset --hard` は破壊的であり、ユーザーの作業を破壊するリスクがあるため採用しない。
   - 代わりに、`git push --tags` 失敗時には「コミットは push 済みだがタグが未 push です。git push --tags を手動で実行してください」という復旧手順を表示する。

エラーメッセージでは「何が残ったか」「どう戻すか」をユーザーに明示することを優先する。

## 完了条件

- `canary.py` の `git_operations` が `git fetch` による事前検証を行い、fast-forward 不可能な場合はコミット・タグを作らずにエラー終了すること。
- タグ作成が `git push` 成功後に実行されること。
- 各ステップ失敗時に「何が残ったか」「どう復旧するか」のエラーメッセージが表示されること。
- `git push` 失敗の代表的なケース (リモートが先行している状態) の再現手順を PR 本文に記載すること。
- dry-run 経路の挙動は変えない。
