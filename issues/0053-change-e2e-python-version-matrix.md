# release E2E を全対応 Python バージョンで実行する

- Priority: Medium
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: -
- Model: GPT-5
- Branch: feature/change-e2e-python-version-matrix
- Polished: 2026-07-17

## 目的

0067 で復活する E2E workflow を、通常の branch build では Python 3.13 だけ、release tag と明示的な手動実行では `requires-python` が宣言する Python 3.12 / 3.13 / 3.14 の全てで実行する。

通常開発の実行時間を維持しつつ、公開する全 CPython ABI の wheel を release gate で検証する。

## 優先度根拠

- build / import smoke だけでは signaling、media、hardware 経路の ABI ごとの差を検出できない。
- 0067 により Python 3.13 の release gate は先に復旧するため、本 issue 単体が release 再開を妨げるわけではなく Medium とする。

## 前提

- 0001 〜 0005、0051、0052、0067 の完了後に実装する。
- 本 issue は 0067 の generic E2E matrix だけを拡張する。Jetson は 0045 / 0073、publish と GitHub Release は 0066 / 0072 の責務とする。
- comment out 済み schedule は復活させない。

## 現状

現行 `.github/workflows/e2e-test.yml` は Python 3.12 / 3.14 をコメントアウトし、3.13 だけを実行する。schedule も無効であり、「schedule 時には全部でテストする」という到達不能な TODO が残っている。

0067 は backend 移行後の E2E と release gate を安全に復活させるため、意図的に Python 3.13 だけを有効にする。本 issue はその安定した artifact / gate 契約を保ったまま、release 時の全 ABI 検証を追加する。

## 設計方針

### 実行モード

`.github/workflows/e2e-test.yml` の reusable workflow input に `full_python_matrix` boolean を追加し、既定値を `false` とする。`workflow_dispatch` にも同名 input を追加する。

- 通常の develop / feature branch push と通常の手動実行: Python 3.13。
- release tag からの build workflow caller: `full_python_matrix: true`。
- maintainer が全 ABI を確認する手動実行: `full_python_matrix: true`。

workflow 内の GitHub-hosted preparation job が input を基に JSON matrix を生成する。`false` は `['3.13']`、`true` は `['3.12', '3.13', '3.14']` だけを返す。任意のバージョン文字列を input として受け取らない。

0066 の tag release path は build workflow から E2E reusable workflow を呼ぶときに `full_python_matrix: true` を必ず渡す。`prepare_release` は全 matrix を含む `e2e_test` caller job の success を待ち、一部 ABI の failure / cancelled / skipped を許可しない。

### platform と artifact

platform matrix は 0067 の generic E2E 対象を維持する。Jetson を追加せず、各 entry は `<wheel_platform>_python-<version>` の wheel artifact を厳密に 1 件取得する。

Python version ごとに filename の CPython ABI tag と interpreter version を検証する。3.12 entry が cp313 wheel を選ぶような fallback、別 version artifact の再利用、0 件 / 複数件から先頭を選ぶ処理は認めない。

### 結果集約

0067 の `e2e_test` caller job と `ci_result` を単一の release gate として維持する。matrix の fail-fast は `false` として全 failure を観測するが、1 entry でも成功以外なら caller job と release gate は失敗する。

通常 branch build の 3.13 gate と release tag の全 version gate を job summary に明示し、実行した Python version / platform / artifact digest を残す。

### テスト

workflow fixture test で次を固定する。

- 通常 input が Python 3.13 だけを返す。
- full input が 3.12 / 3.13 / 3.14 を重複なく返す。
- release tag caller が `full_python_matrix: true` を渡す。
- schedule が無効で、任意 version input が存在しない。
- Jetson entry が generic matrix に混入しない。

mock / stub は使わず、実際に生成した各 wheel artifact を対応する CPython で install して E2E を実行する。

## 完了条件

- 通常の branch build は Python 3.13 の generic E2E だけを実行する。
- release tag は Python 3.12 / 3.13 / 3.14 の全 generic E2E を実行し、全 entry の success が 0066 の publish 条件になる。
- 明示的な workflow_dispatch で同じ全 version matrix を実行できる。
- 各 E2E entry が同じ Python version の wheel artifact を厳密に 1 件使用する。
- `requires-python` の対応 version と full matrix の固定集合が一致することを fixture test で検証する。
- 到達不能な schedule TODO とコメントアウト済み version entry が残らない。
- Jetson の build / E2E / release 契約を変更しない。

## 解決方法

1. E2E reusable workflow と workflow_dispatch に boolean input を追加する。
2. 固定 Python version matrix を生成する preparation job を追加する。
3. 0066 の release tag caller を full matrix に接続する。
4. artifact / ABI 検証と結果集約を全 version に拡張する。
5. workflow fixture test を追加する。
6. `CHANGES.md` の `## develop` に次を追加する。

```
- [CHANGE] release E2E を全対応 Python バージョンで実行する
  - @voluntas
```

## ロールバック

本 issue を revert する場合は Python 3.13 の 0067 gate へ戻す。全 ABI を検証せずに release を継続する判断は自動化せず、3.12 / 3.14 の公開を一時停止して forward fix する。
