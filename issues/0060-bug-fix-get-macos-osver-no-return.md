# legacy `get_macos_osver()` の削除により戻り値欠落問題を解消する

- Priority: Medium
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: -
- Model: Opus 4.7
- Branch: feature/fix-get-macos-osver-no-return
- Polished: 2026-07-17

## 目的

本 issue を個別実装せず、0001 で `buildbase.py`、`run.py`、`get_macos_osver()` と全 consumer を削除して問題を解消する。

0002 の scikit-build-core macOS build は runner / matrix で platform と deployment target を明示し、host OS version を legacy helper から推測しない。

## 設計方針

- `return` だけを追加する暫定修正は行わない。
- 本 issue の branch は作成しない。
- 0001 の実装 commit 後、別の close commit で本 issue file を `issues/closed/` へ移動する。
- 0002 が `MACOSX_DEPLOYMENT_TARGET=14.0` と `CMAKE_OSX_DEPLOYMENT_TARGET=14.0` を macos-14 / macos-15 の両 runner で検証する。
- 本 issue 独自の CHANGES entry は追加しない。

## 完了条件

- 0001 の完了条件が満たされ、`get_macos_osver()` と consumer が存在しない。
- 0002 の macOS build が host version の暗黙推測に依存しない。
- 本 issue 単独の実装 branch / commit がない。
- 0001 の close commit で本 issue が `issues/closed/` へ移動される。

## ロールバック

0001 を revert する場合も戻り値欠落 helper を復活させない。macOS release を一時停止し、0002 の明示的 deployment target 経路を forward fix する。
