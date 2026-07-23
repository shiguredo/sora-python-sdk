# legacy `setup.py` の削除により Ubuntu tag の silent fallback を解消する

- Priority: Medium
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: 2026-07-23
- Model: Opus 4.7
- Branch: feature/fix-setup-py-osver-silent-fallback
- Polished: 2026-07-17

## 目的

本 issue を個別実装せず、0001 で `setup.py` と custom `bdist_wheel.get_tag()` を削除し、未知 Ubuntu version が host platform tag へ silent fallback する経路を消す。

0003 の cross wheel tag は scikit-build-core override の allowlist で target / Python ABI ごとに明示し、0052 が `auditwheel repair` 後の manylinux tag と wheel metadata を検証する。

## 設計方針

- legacy `setup.py` に `if / elif / else` を追加する暫定修正は行わない。
- 本 issue の branch は作成しない。
- 0001 の実装 commit 後、別の close commit で本 issue file を `issues/closed/` へ移動する。
- 0003 は未知の `SORA_SDK_TARGET`、target と ABI の不一致、未定義 override を configure / build 前に拒否する。
- 0052 は生成 wheel filename と `.dist-info/WHEEL` の platform tag が対象 manylinux policy と一致しない場合に失敗する。
- 本 issue 独自の CHANGES entry は追加しない。

## 完了条件

- 0001 の完了条件が満たされ、`setup.py` と custom `bdist_wheel` が存在しない。
- 0003 / 0052 が未知 target と tag fallback を拒否する。
- 本 issue 単独の実装 branch / commit がない。
- 0001 の close commit で本 issue が `issues/closed/` へ移動される。

## ロールバック

0001 を revert する場合も silent fallback を持つ `setup.py` を復活させない。Linux wheel release を一時停止し、scikit-build-core / auditwheel 経路を forward fix する。
