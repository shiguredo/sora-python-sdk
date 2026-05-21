# Linux x86_64 から arm64 へのクロスコンパイル対応

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-crosscompile-aarch64-linux

## 目的

x86_64 runner 上で ubuntu armv8 向け wheel をビルドする経路を scikit-build-core + CMake toolchain で再現する。PyPI publish 対象の arm wheel はこの経路に依存するため、省略不可。

## 優先度根拠

High。`build_ubuntu` job が x86_64 runner で `ubuntu-*_armv8` をビルドしており、`publish_wheel` は `build_ubuntu_arm` ではなく `build_ubuntu` に依存している。

## 現状

- `run.py` L303–318 が x86_64→armv8 クロス用 cmake 引数（sysroot、libwebrtc clang、`-target aarch64-linux-gnu`、`NB_SUFFIX`）を設定する
- `buildbase.py` の `install_rootfs` が multistrap で `_install/<target>/rootfs/` を構築する
- `setup.py` の `bdist_wheel.get_tag()` が manylinux タグ（`manylinux_2_31_aarch64` / `manylinux_2_35_aarch64`）を上書きする
- pyi はクロス時に生成できないため、CI の `build_pyi` job が artifact を配布する
- `Platform` クラスは jetson / RPi で `build.arch == x86_64` を強制する

## 設計方針

- `run.py` L283–373 相当を `cmake/toolchains/ubuntu-aarch64-cross.cmake` に抽出する
- multistrap + symlink 修正は `cmake/scripts/install_rootfs.sh` に移植する（conf MD5 をキャッシュキーにする）
- `pyproject.toml` の `[tool.scikit-build.overrides]` で `SORA_SDK_TARGET` ごとに toolchain / `wheel.plat` / `cmake.define.TARGET_OS` を設定する
- クロス時は `SORA_GEN_PYI=OFF` とし、CI artifact から pyi を配置してから `uv build` する（現状維持）
- WebRTC / Sora / Boost は **target 基準** の platform 文字列（例: `ubuntu-24.04_armv8`）で DL する
- `NB_SUFFIX=.cpython-<ver>-aarch64-linux-gnu.so` を toolchain 側で設定する

## 完了条件

- x86_64 runner 上で `SORA_SDK_TARGET=ubuntu-24.04_armv8 uv build --wheel` が成功する
- wheel タグが `manylinux_2_35_aarch64` になる
- 拡張モジュール名が `sora_sdk_ext.cpython-3xx-aarch64-linux-gnu.so` になる
- `ubuntu-22.04_armv8` 向けは `manylinux_2_31_aarch64` になる
- CI artifact から配置した pyi / py.typed が wheel に含まれる
- `build_ubuntu` job 相当の CI が通る

## 解決方法

- `cmake/toolchains/ubuntu-aarch64-cross.cmake` を新設する
- `cmake/scripts/install_rootfs.sh` を新設する（`buildbase.py` L1075–1118 相当）
- `pyproject.toml` に ubuntu armv8 向け overrides を追加する
- `CMakeLists.txt` に rootfs 取得 target を追加し、クロス時に `add_dependencies` する
- CI `build.yml` の armv8 向け step を `uv build --wheel` のみに変更する（0006 で全面切替）
