# canary.py の git_operations が途中失敗時にローカルとリモートの整合が壊れる問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-canary-git-no-rollback

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
失敗パターンと残骸の関係は以下のとおり。

| 失敗ステップ        | ローカルに残る残骸                          | リモート反映 |
|---------------------|---------------------------------------------|--------------|
| `git add`           | (なし)                                      | 無し         |
| `git commit`        | staged 状態の VERSION                       | 無し         |
| `git tag`           | コミット 1 個                               | 無し         |
| `git push`          | コミット 1 個 + ローカルタグ                | 無し         |
| `git push --tags`   | コミット 1 個 + ローカルタグ + push 済 HEAD | コミットのみ |

`git push` が non-fast-forward で reject されるケースが最も問題で、ローカルに「コミット + タグ」だけが残った状態でリトライしても、リモート反映を取り込まないまま再度 push が試みられて同じ失敗を繰り返す。

## 設計方針

以下を組み合わせる。最終的などちらか / 両方の採否は実装時に決定する (本 issue では断定しない)。

1. push 可能性を事前確認してから commit / tag を行う
   - `git fetch origin` で上流の HEAD を取得し、ローカルがリモートに対して fast-forward 可能な状態 (= ローカル HEAD が remote HEAD のちょうど 1 つ進めれば追いつける状態) であることを確認してから `git add` / `git commit` / `git tag` を行う。
   - 整合しない場合は早期に `print` + `sys.exit(1)` し、コミット・タグを一切作らない。
2. タグ作成を push 成功後に移動する
   - 順序を `git add` → `git commit` → `git push` → `git tag` → `git push --tags` に変える。
   - これによりコミット push 失敗時はローカルタグが残らない。
3. 失敗時のロールバック処理を追加する
   - `git push` 失敗時はそれまでに作ったローカルタグ (`git tag -d <tag>`) と HEAD (`git reset --hard HEAD~1`) を巻き戻す。
   - ただし `git reset --hard` は破壊的なため、巻き戻し前にユーザー確認を取るか、`--auto-rollback` のような明示フラグでガードする。

実装時にはエラーメッセージで「何が残ったか」「どう戻すか」をユーザーに明示することを優先する。
ロールバックを自動化しすぎてユーザーの作業を破壊しないこと。

## 完了条件

- `canary.py` の `git_operations` が途中失敗したときに、ローカルとリモートの整合が壊れない (または、壊れた場合にユーザーが復旧できる十分な情報を表示する)。
- `git push` 失敗の代表的なケース (リモートが先行している状態) を再現するテストまたは手順を CHANGES.md / PR 本文に記載する。
- dry-run 経路の挙動は変えない。
