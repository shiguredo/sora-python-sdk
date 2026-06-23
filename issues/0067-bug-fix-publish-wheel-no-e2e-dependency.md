# publish_wheel / create-release が e2e_test を待たない CI 設定を是正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-publish-wheel-no-e2e-dependency

## 目的

`.github/workflows/build.yml` の `publish_wheel` ジョブと `create-release` ジョブは、いずれも `needs:` リストから `e2e_test` がコメントアウトされている。

- `publish_wheel.needs`: `build_ubuntu` / `build_macos` / `build_windows` のみ。
- `create-release.needs`: 同上。

これにより、`tags/202xxxx` のタグ push でリリースが発火したときに `e2e_test` の結果を **一切待たずに** PyPI publish と GitHub Release が走る。
E2E が `fail` していてもリリースが進む構造であり、リリース品質保証のゲートが事実上存在しない。

意図的に外しているのであれば CHANGES.md / README にその旨を明記すべきだが、現状はコメントアウトされたままで意図が不明である。本 issue で「待つ」か「待たないことを明示する」かを決め、CI 設定を是正する。

## 優先度根拠

Medium とする。

- PyPI に E2E 失敗の wheel が混入するリスクは現実的だが、リリースタグを切るのはメンテナの手動操作であり、通常はメンテナが E2E の状況を確認してからタグを切る運用でカバーされている。
- 一方で「CI 設定が意図せぬ抜け穴になっている」状態は事故待ちであり、放置すれば「メンテナの注意力に依存したリリースゲート」という弱い保証しか残らない。
- 即時のユーザー被害は無いが、構造的な品質保証として Medium で扱う。

## 現状

`.github/workflows/build.yml:344-351` (`publish_wheel.needs`):

```yaml
publish_wheel:
  if: contains(github.ref, 'tags/202')
  # needs:
  #   - e2e_test
  needs:
    - build_ubuntu
    - build_macos
    - build_windows
```

`.github/workflows/build.yml:406-413` (`create-release.needs`):

```yaml
create-release:
  if: contains(github.ref, 'tags/202')
  # needs:
  #   - e2e_test
  needs:
    - build_ubuntu
    - build_macos
    - build_windows
```

`e2e_test` ジョブ (`322-327` 行) は `build_ubuntu` / `build_macos` / `build_windows` を `needs:` に持ち、`./.github/workflows/e2e-test.yml` を呼び出す。
このため `e2e_test` は `publish_wheel` / `create-release` と並行して走り、結果が出る前にリリースが完了し得る。

E2E をコメントアウトに変更したコミットの根拠は CHANGES.md / コミットメッセージから明確には読み取れない (作業時に確認すること)。
推測される理由: 「E2E が flaky で、リリース時に毎回再実行するのが現実的でなかった」「タグ push 後の修正不可能性 (PyPI の wheel は上書き不可) を踏まえて、メンテナの手動確認に委ねた」。

## 設計方針

以下 (a) (b) のどちらかを選ぶ。実装時に判断する。

(a) `e2e_test` を `needs:` に戻す。

- `publish_wheel.needs` と `create-release.needs` の両方に `e2e_test` を追加する。
- E2E が flaky なら、まず E2E 自体の安定化 (issue 0015 等) を優先する。
- リリースタグを切る前にメンテナが E2E の status を確認する手間が減る。

(b) 「E2E はリリースゲートにしない」と明示する。

- CHANGES.md / README / `.github/workflows/build.yml` のコメントに「E2E は事前検証であり、リリースゲートではない。リリースタグを切る前にメンテナが E2E の status を確認する責任を負う」と明記する。
- 現状のコメントアウトを「行ごと削除」してこのコメントに置き換える (コメントアウトを残すと「いつか戻すつもり」の意図が伝わって却って混乱する)。
- リリース運用手順 (`docs/release.md` 等を作るかは別判断) に E2E 確認ステップを明文化する。

可能であれば (a) を選びたいが、E2E 安定化のコストとの兼ね合いで (b) を選ぶことも合理的。
本 issue では選択判断と、選んだ方向への CI 設定 / ドキュメント変更を扱う。

issue 0066 (publish_wheel matrix の 24.04 不在) と関連が深いため、合わせて対応するのが望ましい。

## 完了条件

- `publish_wheel` / `create-release` の `needs:` が「コメントアウトされた `e2e_test`」を含まない状態になっている。
- 採用方針 ((a) または (b)) が CHANGES.md / コミットメッセージから判別できる。
- (a) を選ぶ場合: 次回のリリースタグで `e2e_test` が事前に成功してからリリースが走ることを確認する。
- (b) を選ぶ場合: README / CHANGES.md / docs のいずれかに「E2E はリリースゲートでない」旨が明記される。
