# scikit-build-core 導入と CMake によるネイティブ deps 取得（x86_64）

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-scikit-build-core-native-deps

## 目的

ビルド backend を setuptools + 手動 cmake から scikit-build-core + nanobind + uv に移行する第一歩として、ubuntu x86_64 ネイティブ環境で `uv build --wheel` 1 コマンドで wheel が生成できる状態にする。あわせて WebRTC / Sora C++ SDK / Boost のダウンロードを `buildbase.py` / `run.py` から CMake に移す。

## 優先度根拠

High。以降の issue（クロスコンパイル、CI 切替）すべての前提となる。ここが通らないと移行全体が進まない。

## 現状

- `run.py build` が `buildbase.py` 経由で deps を `_install/<target>/` に取得し、cmake を手動実行して `.so` を `src/sora_sdk/` にコピーする
- `uv build` が `setup.py` / setuptools でコピー済み `.so` を wheel 化するだけ
- deps バージョンは `DEPS` ファイル、platform 文字列は `get_webrtc_platform()` で target 基準に決定
- nanobind は `dependency-groups.dev` にあり、build-system は setuptools

## 設計方針

- [webcodecs-py](https://github.com/shiguredo/webcodecs-py) の構成を参考にする
- `pyproject.toml` の build backend を `scikit_build_core.build` に変更する
- `deps.json` を新設し、WebRTC / Sora / Boost / OpenH264 のバージョンを定義する（既存 `DEPS` から移行）
- CMake の `ExternalProject` で WebRTC / Sora / Boost を `_deps/${SORA_PLATFORM}/` に DL + 展開する
- webcodecs-py と同様 `build-dir = "_build/{wheel_tag}"`、`wheel.packages = ["src/sora_sdk"]` とする
- バージョンは `VERSION` ファイルから dynamic metadata で読む
- この issue では **ubuntu-24.04_x86_64 ネイティブのみ** を対象とする
- LLVM / OpenH264 / multistrap rootfs は 0002 / 0003 に委ねる（0001 では libwebrtc 付属 clang が不要な範囲、または最小限の stub）

## 完了条件

- `ubuntu-24.04_x86_64` + Python 3.12 で `uv build --wheel` が成功する
- 生成された wheel に `sora_sdk_ext.*.so` と Python パッケージが含まれる
- `setup.py` を削除し、scikit-build-core が build backend になる
- WebRTC / Sora / Boost の DL が CMake 内で完結する（`run.py build` を呼ばない）
- 既存 pytest が通る

## 解決方法

- `pyproject.toml` に `[build-system]` / `[tool.scikit-build]` / `[tool.scikit-build.metadata.version]` を追加する
- `deps.json` を追加する
- `CMakeLists.txt` に `_deps/` レイアウト、`ExternalProject` による WebRTC / Sora / Boost 取得、`install(TARGETS sora_sdk_ext LIBRARY DESTINATION sora_sdk)` を実装する
- `SORA_PLATFORM` cache 変数を導入し、x86_64 ネイティブでは `ubuntu-24.04_x86_64` 等を渡す
- `run.py` の `build` サブコマンド内 cmake 実行・成果物コピーを削除する（0006 でファイル自体を削除）
- `CHANGES.md` に `[CHANGE]` を追記する
