# macOS / Windows 向けビルドとローカル dev 用 CMake option

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-macos-windows-build

## 目的

macOS arm64 と Windows x86_64 向け wheel ビルドを scikit-build-core 構成に移行し、ローカル開発用の `--local-webrtc-build-dir` / `--local-sora-cpp-sdk-dir` 相当を CMake option として提供する。

## 優先度根拠

High。publish 対象に macOS / Windows が含まれており、開発者がローカル C++ SDK を参照するフローも既存で使われている。

## 現状

- macOS: `run.py` L320–332 — libwebrtc clang、xcrun sysroot、`-nostdinc++`（CMakeLists.txt）
- Windows: CMakeLists.txt 側で MSVC 静的ランタイム等を設定、`run.py` は cmake 引数最小
- `setup.py` は macOS / Windows で plat タグをカスタムしない（デフォルト）
- `run.py` は `--local-webrtc-build-dir` / `--local-sora-cpp-sdk-dir` で `build_webrtc` / `build_sora` を呼ぶ
- macOS CI は `_PYTHON_HOST_PLATFORM` / `ARCHFLAGS` を env で渡す

## 設計方針

- macOS は scikit-build-core が `_PYTHON_HOST_PLATFORM` / `ARCHFLAGS` を wheel 名に反映する（現 CI 維持）
- Windows は CMakeLists.txt の既存 MSVC 設定を scikit-build-core 経由でも有効にする
- ローカル dev 用に CMake option を追加する:
  - `SORA_LOCAL_WEBRTC_BUILD_DIR`
  - `SORA_LOCAL_SORA_CPP_SDK_DIR`
- pyi 生成: macOS ネイティブでは `SORA_GEN_PYI=ON`、Windows では OFF（現状維持 + CI artifact）
- `BUILD_PROFILE=debug` 時の `+debug` バージョン suffix を scikit-build-core overrides で対応する

## 完了条件

- macOS arm64 で `uv build --wheel` が成功する
- Windows x86_64 で `uv build --wheel` が成功する
- `--local-sora-cpp-sdk-dir` 指定時にローカル Sora C++ SDK がリンクされる
- debug ビルドでバージョンに `+debug` が付く
- 既存 pytest / CI matrix（macOS / Windows）が通る

## 解決方法

- macOS / Windows 向け `pyproject.toml` overrides を追加する
- `CMakeLists.txt` に local dev option とパス解決を追加する
- `build-debug.yml` の `BUILD_PROFILE=debug` を scikit-build-core 側に接続する
- CI の macOS / Windows job を `uv build --wheel` のみに変更する
