# legacy `_extractzip` の削除により symlink 復元問題を解消する

- Priority: Medium
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: 2026-07-23
- Model: Opus 4.7
- Branch: feature/fix-extractzip-symlink-restore
- Polished: 2026-07-17

## 目的

本 issue を個別実装せず、0001 で `buildbase.py` と `_extractzip()` を consumer ごと削除して問題を解消する。

scikit-build-core 後の archive 展開は `cmake/scripts/fetch_deps.cmake` が一時 directory へ展開し、期待 layout の検証後に配置する。legacy Python 実装の symlink 復元処理を修正・移植しない。

## 設計方針

- 本 issue の branch は作成しない。
- 0001 の実装 commit 後、別の close commit で本 issue file を `issues/closed/` へ移動する。
- CMake 側の archive 展開で symlink が必要な release asset を実物で検証し、欠落・dangling link・build root 外を指す absolute link があれば failure にする。
- archive 更新の transaction、SHA-256、rollback は 0070 が扱う。
- 本 issue 独自の CHANGES entry は追加せず、0001 の legacy build 廃止 entry に含める。

## 完了条件

- 0001 の完了条件が満たされ、`buildbase.py` と `_extractzip()` が存在しない。
- `rg '_extractzip'` で source / workflow に consumer が残らない。
- WebRTC / Sora / Boost の実 archive 展開後に必要な symlink と代表 file が存在する。
- 本 issue 単独の実装 branch / commit がない。
- 0001 の close commit で本 issue が `issues/closed/` へ移動される。

## ロールバック

0001 を revert する場合も、壊れた `_extractzip()` を復活させない。legacy build を停止し、scikit-build-core 経路を forward fix する。
