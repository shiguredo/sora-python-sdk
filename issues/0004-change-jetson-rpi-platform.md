# jetson / Raspberry Pi OS 向けビルドと sora_sdk_rpi パッケージ

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-jetson-rpi-platform

## 目的

jetson と raspberry-pi-os 向けの x86_64 クロスビルド、および RPi 専用パッケージ `sora_sdk_rpi` の wheel 生成を scikit-build-core 構成で再現する。

## 優先度根拠

High。publish / release 対象に `raspberry-pi-os_armv8` が含まれており、jetson は `Platform` クラスで x86_64 クロスが必須とされている。

## 現状

- jetson: `run.py` L333–352 — Python 3.10 固定 `NB_SUFFIX`、sysroot、libwebrtc clang
- raspberry-pi-os: `run.py` L353–373 + L421–424 — クロス設定 + `libcamerac.so` を `src/sora_sdk/` にコピー
- CI は RPi 向けに `pyproject.toml` の name を `sora_sdk_rpi` に sed 書き換えしている
- `setup.py` は jetson で `manylinux_2_17_aarch64.manylinux2014_aarch64`、RPi で `manylinux_2_35_aarch64` と `libcamerac.so` を package_data に含める

## 設計方針

- `cmake/toolchains/jetson-aarch64-cross.cmake` と `cmake/toolchains/raspberry-pi-os-aarch64-cross.cmake` を新設する
- multistrap conf は既存 `multistrap/*.conf` をそのまま利用する
- `libcamerac.so` は CMake `install(FILES ... DESTINATION sora_sdk)` で wheel に同梱する
- `sora_sdk_rpi` パッケージ名は `[tool.scikit-build.overrides]` + 環境変数で切り替え、CI の sed を廃止する
- RPi 向け `SORA_PYTHON_SDK_VERSION` は `sora-sdk-rpi` の metadata から取得する（現 `run.py` L267–271 相当）

## 完了条件

- `SORA_SDK_TARGET=ubuntu-22.04_armv8_jetson` で wheel が生成される
- `SORA_SDK_TARGET=raspberry-pi-os_armv8` で `sora_sdk_rpi` 名の wheel が生成される
- RPi wheel に `libcamerac.so` が含まれる
- jetson wheel タグが `manylinux_2_17_aarch64.manylinux2014_aarch64` になる
- 関連 E2E テストが通る

## 解決方法

- jetson / RPi 用 toolchain ファイルを追加する
- `pyproject.toml` overrides でパッケージ名 / wheel.plat / SORA_PLATFORM を設定する
- `CMakeLists.txt` に RPi 向け `install(FILES libcamerac.so ...)` を追加する
- CI の `sora_sdk_rpi` sed step を削除する
