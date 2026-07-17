# CI の build dependency を target / host 単位で cache する

- Priority: Medium
- Created: 2026-07-17
- Updated: 2026-07-17
- Completed: -
- Model: GPT-5
- Branch: feature/refactor-cache-build-dependencies
- Polished: 2026-07-17

## 目的

scikit-build-core 移行後の CI が各 job で `_deps/` を再取得・再展開する重複を減らすため、target dependency と host toolchain を分離して `actions/cache` へ保存する。

cache hit 後も `fetch_deps.cmake` の archive / stamp 検証と `sysroot_builder.py` の manifest fingerprint 検証を必ず通し、cache を dependency 検証の代替にしない。

## 優先度根拠

- cache が無くても build の正しさは変わらないため High ではない。
- WebRTC / Sora / Boost / LLVM と sysroot の取得は容量と時間が大きく、Python 3 ABI と複数 target の job で毎回繰り返す CI cost が高いため Medium とする。

## 前提

- 0001 〜 0005 と 0070 の完了後に実装する。
- 0001 の `_deps/<platform>` と `_deps/llvm/<host-key>` layout を変更しない。
- dependency の取得・検証・再利用判定は `fetch_deps.cmake` / `sysroot_builder.py` が引き続き単一の責務を持つ。本 issue は取得処理そのものを変更しない。

## 現状

0001 の local build は stamp により同じ checkout 内の再取得を避けるが、GitHub Actions の job 間・workflow run 間では workspace を共有しない。Python 3.12 / 3.13 / 3.14 の各 job が同じ target dependency を取得し、Linux / macOS job は同じ host 用 LLVM も target ごとに取得する。

一方で `_deps/<platform>` と `_deps/llvm/<host-key>` は独立している。両方を `_deps` 全体として cache すると、target と host の invalidation 単位が混ざり、同じ path を複数 cache が包含する危険がある。

## 設計方針

### cache の分割

次の 2 種だけを保存する。

| cache | path | 単位 |
| --- | --- | --- |
| target dependency | `_deps/<dependency-platform>` | archive platform |
| host LLVM | `_deps/llvm/<host-key>` | build host |

`_deps` 全体、`_build`、`dist`、uv cache、debug workflow の local checkout / local build は対象にしない。target path と LLVM path は包含関係を持たせない。

matrix に cache 用の値を明示する。

- dependency platform: `ubuntu-24.04_x86_64` / `macos_arm64` / `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` / `raspberry-pi-os_armv8` / `windows_x86_64`。
- host key: Ubuntu / Raspberry Pi OS は `x86_64-Linux`、macOS は `arm64-Darwin`。Windows は LLVM を取得しないため `none`。
- macos-15 / macos-26 は同じ `macos_arm64` dependency と `arm64-Darwin` LLVM を共有する。

### key

prefix restore は使用せず、完全一致 key だけを restore する。

target dependency key は次を含む。

- schema version。
- dependency platform。
- `DEPS` の hash。
- `cmake/scripts/fetch_deps.cmake` の hash。
- sysroot を使わない target は固定値 `no-sysroot`。
- Ubuntu arm64 は `sysroot_builder.py`、該当 JSON、runner の Ubuntu archive keyring file の SHA-256。
- Raspberry Pi OS は `sysroot_builder.py`、該当 JSON、JSON が参照する vendored Debian / Raspberry Pi keyring の SHA-256。

system / vendored keyring の digest は cache restore より前に計算する。file が無い、hash command が失敗する、step output が空の場合は cache key を組み立てず job を失敗させる。

LLVM key は schema version、host key、`DEPS`、`fetch_deps.cmake` の hash を含む。LLVM version は WebRTC archive 内の metadata から決まるため、`DEPS` にある WebRTC version / SHA-256 の変更で key が変わる。

### restore 後の検証

cache hit / miss にかかわらず通常どおり `uv build --wheel` を実行する。`fetch_deps.cmake` は URL / SHA-256 / stamp / archive を、`sysroot_builder.py` は builder / JSON / keyring を含む manifest fingerprint を再検証する。

次の状態は cache hit として採用せず、通常処理で再生成または明示的失敗にする。

- archive / stamp の欠落・不一致。
- sysroot manifest の欠落・fingerprint 不一致。
- target path 内に別 platform の ELF がある。
- LLVM path の clang executable / libc++ header が欠けている。

sysroot builder の fingerprint 不一致を cache step が削除・上書きして隠さない。0003 / 0004 の通常 build と同じく、由来不明の既存 rootfs は `--force` 無しで拒否する。

### workflow

既存 workflow で使用中の commit SHA 固定済み `actions/cache` を再利用し、本 issue では action version を更新しない。

- target cache restore は dependency fetch より前、sysroot keyring hash の計算後に置く。
- LLVM cache restore は host key 確定後、dependency fetch より前に置く。Windows では step 自体を skip する。
- `build_pyi` が存在する時点では `ubuntu-24.04_x86_64` / `x86_64-Linux` の同じ key を使う。
- 同じ key を使う matrix job が並列に終了した場合、最初に保存された immutable cache を採用する。他 job の cache save 競合は failure にしない。

### 検証

同じ commit で cache 無効の 1 回目と cache 有効の 2 回目を実行し、次を job summary に記録する。

- target / LLVM の key と `cache-hit` output。
- 2 回目に WebRTC / Sora / Boost / LLVM archive の network download が発生していないこと。
- sysroot target の 2 回目に APT download / deb 展開が発生せず、manifest と代表 header の mtime が変わらないこと。
- wheel filename と SHA-256。cache の有無で wheel の内容が変わる場合は failure とする。

mock / stub は使わず、通常の dependency と sysroot を使う CI run で確認する。

## 完了条件

- target dependency と host LLVM が重複しない path / key で cache される。
- Windows では LLVM cache step が実行されない。
- 同一入力の 2 回目 run で全対象 cache が hit し、dependency archive と sysroot package を再取得しない。
- `DEPS` / fetch script / builder / 対象 JSON / keyring の各入力変更で対応 cache key だけが変わる。
- cache 内の archive、stamp、sysroot manifest、LLVM 代表 file を破損させた場合に検証が失敗し、壊れた成果物から wheel を生成しない。
- cache hit / miss の両方で全 platform / Python matrix の wheel build が green になる。

## 解決方法

1. build matrix に dependency platform / host key / sysroot 種別を追加する。
2. cache restore 前の keyring digest step を追加する。
3. target dependency と LLVM の `actions/cache` step を追加する。
4. cache hit / miss、入力変更、破損 cache の integration test を行う。

## 変更履歴

CI の内部性能だけを変更し、SDK の機能・公開 API・対応 platform・生成 wheel の仕様は変えないため `CHANGES.md` には記載しない。

## ロールバック

cache step だけを revert しても dependency fetch の正しさは維持される。本 issue の squash commit を `git revert <squash-commit>` し、cache miss 状態で全 build が green になることを確認する。GitHub 上に残った旧 cache は key schema version を上げて参照不能にし、手動削除を必須にしない。
