# multistrap をやめて署名検証付き sysroot に切り替える

- Priority: High
- Created: 2026-07-23
- Completed: -
- Model: Cursor Grok 4.5
- Branch: feature/change-multistrap-to-sysroot
- Polished:

## 目的

現行の `multistrap` + HTTP + `--no-auth` / CI での `/usr/sbin/multistrap` 書き換えによる insecure な rootfs 構築をやめ、webrtc-build 系の署名検証付き sysroot builder（HTTPS + `signed-by`）へ切り替える。

対象は現行の `run.py` / `buildbase.py` / `setup.py` 経路のままとする。scikit-build-core 化は前提にしない。

Ubuntu arm64（22.04 / 24.04）と Raspberry Pi OS arm64 の rootfs をまとめて置き換える。Jetson は 0043 で扱う。

## 優先度根拠

- CI が `/usr/sbin/multistrap` を `sed` で書き換え、`Acquire::AllowInsecureRepositories=true` を注入している（`.github/workflows/build.yml`）。
- `buildbase.py` の `install_rootfs()` が `multistrap --no-auth` を実行している。
- Ubuntu / Raspberry Pi OS 用 conf が HTTP の archive を参照している。
- `multistrap` 自体も Debian unstable から削除済みで、runner 更新の障害になる。
- README は Raspberry Pi OS Trixie をサポート対象としているが、現行 conf は Bookworm のままである。

## 現状

- `run.py` が `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` / `raspberry-pi-os_armv8` / `ubuntu-22.04_armv8_jetson` で `install_rootfs()` を呼ぶ。
- `buildbase.py` の `install_rootfs()` が `multistrap --no-auth` で rootfs を作り、絶対 symlink の相対化などを後処理する。
- conf は `multistrap/*.conf`。キャッシュキーは conf の MD5 のみ。
- CI の armv8 matrix は x86_64 host からの cross と、arm64 native runner の両方が存在する。

旧 0003 / 0004 は scikit-build-core（0001）前提で書かれていたため、本 issue に置き換える。

## スコープ

含む:

- webrtc-build の `sysroot_builder.py` とユニットテストの移植（リポジトリルート）。
- Ubuntu 22.04 / 24.04 arm64 用 JSON（`sysroot/`）。
- Raspberry Pi OS Trixie arm64 用 JSON と Debian / Raspberry Pi archive keyring。
- `RepositoryConfig` の optional `pin_priority`（Raspberry Pi repository を Debian より優先するため）。
- `run.py` / `buildbase.py` から `install_rootfs(multistrap)` を外し、sysroot builder を呼ぶ。
- Ubuntu / Raspberry Pi OS 用 `multistrap/*.conf` の削除。
- CI の `multistrap` install と `/usr/sbin/multistrap` 書き換えの削除。
- Raspberry Pi OS は Trixie に合わせる（Bookworm conf は残さない）。

含まない:

- Jetson（`ubuntu-22.04_armv8_jetson` / `multistrap/ubuntu-22.04_armv8_jetson.conf`）。0043 で扱う。
- scikit-build-core 化、`fetch_deps.cmake`、Makefile / debug workflow の再設計。
- auditwheel / publish / E2E の再設計（既存経路を壊さない範囲でビルドが通ればよい）。
- arm64 native build の廃止判断（別 issue）。本 issue は rootfs 取得手段の置換に限定する。

## 設計方針

### sysroot builder

webrtc-build の実装を基に `sysroot_builder.py` を追加する。

- リポジトリ URL は HTTPS のみ。全 repository に `signed_by` を必須とする。
- ホストの `/var/lib/apt` / `/etc/apt` を触らず、一時 directory に APT state を隔離する。
- `apt-get --download-only` + `dpkg-deb --extract` で rootfs を構築する。maintainer script / chroot / root 権限は使わない。
- 設定と keyring 内容の SHA-256 を manifest に残し、同一 fingerprint は再利用、不一致は `--force` 無しでは上書きしない。
- CLI は `python sysroot_builder.py --config <json> --dest <rootfs> [--force]`。CLI 専用の別ファイルは作らない。

### 現行ビルド経路への接続

- `run.py` の cross target で、multistrap conf の代わりに対応 JSON を `sysroot_builder.py` へ渡す。
- rootfs の配置先は現行どおり `install_dir/rootfs` を維持し、後続の CMake 引数（`CMAKE_SYSROOT` 等）を壊さない。
- conf MD5 による `rootfs.version` は、builder の manifest / fingerprint 再利用に置き換える。
- Jetson target の呼び出しは本 issue では触らない（0043 まで現行経路を残す）。

### Raspberry Pi OS

- suite は `trixie`。`libstdc++-14-dev` と `libcamera-dev` を含める。
- Raspberry Pi repository に `pin_priority: 990` を付け、Debian より優先する。
- distribution 名 `sora_sdk_rpi` / import 名 `sora_sdk` / `libcamerac.so` 同梱は現行どおり維持する。

## 完了条件

- Ubuntu 22.04 / 24.04 arm64 と Raspberry Pi OS arm64 の wheel が、署名検証付き sysroot から現行 `run.py` 経路で生成できる。
- 対象 target の build で `multistrap` 実行、`--no-auth`、`AllowInsecureRepositories`、`/usr/sbin/multistrap` の書き換えが残っていない。
- Ubuntu / Raspberry Pi OS 用 `multistrap/*.conf` が削除されている（Jetson conf は残ってよい）。
- `sysroot_builder.py` のユニットテストが通る（ネットワーク・mock・stub は使わない範囲）。
- 同一設定の 2 回目実行で sysroot を再生成しない。
- 0061 の insecure multistrap 問題が経路削除により解消されている。

## 解決方法

1. `sysroot_builder.py` とテスト、Ubuntu / Raspberry Pi OS 用 JSON、keyring を追加する。
2. `run.py` / `buildbase.py` の rootfs 取得を builder 呼び出しへ切り替える。
3. 対象 conf と CI の multistrap 依存・insecure patch を削除する。
4. CI で Ubuntu arm64 / Raspberry Pi OS の build が通ることを確認する。

## 関連

- 旧 0003 / 0004 を本 issue に統合して closed にする。
- 0061 は本 issue で insecure 経路を削除するため、本 issue と同時に closed にする。
- 0043（Jetson）は本 issue 完了後に、同じ builder を前提へ refresh する。
