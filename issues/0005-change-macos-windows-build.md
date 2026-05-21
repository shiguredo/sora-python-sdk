# macOS / Windows native ビルド完結とローカル dev 用 CMake option

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-macos-windows-build

## 目的

0001 / 0002 / 0003 / 0004 で確立した scikit-build-core + `fetch_deps.cmake` 構成を、macOS arm64 と Windows x86_64 のネイティブビルドで完結させ、`uv build --wheel` 一発で正しい wheel タグ（macOS: `cp3XY-cp3XY-macosx_14_0_arm64`、Windows: `cp3XY-cp3XY-win_amd64`）を持つ wheel が生成できる状態にする。あわせて、ローカル開発者がリポジトリ外の Sora C++ SDK / libwebrtc-build をビルドして参照する `--local-webrtc-build-dir` / `--local-sora-cpp-sdk-dir` 相当を `cmake.define.SORA_LOCAL_WEBRTC_BUILD_DIR` / `SORA_LOCAL_SORA_CPP_SDK_DIR` cache 変数として提供する。

## 優先度根拠

High。publish 対象に macOS arm64 / Windows x86_64 が含まれており、開発者がローカル C++ SDK を参照するフローも既存で活用されている。0005 が通らないと macOS / Windows wheel の publish が止まり、Sora C++ SDK 側の開発者検証フローも止まる。

## スコープ

含む:

- macOS arm64 ネイティブビルド完結（`fetch_deps.cmake` 経由 deps 取得 → `CLANG_DIR` 経由コンパイラ設定 → `uv build --wheel` で wheel 生成）
- Windows x86_64 ネイティブビルド完結（MSVC + Windows SDK 同梱ランタイム前提。`CLANG_DIR` / `LIBCXX_INCLUDE_DIR` は使わない）
- `[[tool.scikit-build.overrides]]` で macOS arm64 / Windows x86_64 × Python 3.12 / 3.13 / 3.14 の独立 override を追加（各 6 件）
- macOS wheel タグ:
  - macos-14 runner で `macosx_14_0_arm64`、macos-15 runner で `macosx_15_0_arm64` を生成する（runner OS バージョンと wheel タグを一致させる方針。既存 CI も同じ運用）
  - `_PYTHON_HOST_PLATFORM=macosx-X.0-arm64` env を CI で設定するが、これは setuptools 由来の env で scikit-build-core が継承する保証はない（実装時に PoC 検証必須）。確実にタグを強制するには `wheel tags --remove --platform-tag macosx_X_0_arm64 dist/*.whl` を build job 末尾の CI step で実行する
  - `MACOSX_DEPLOYMENT_TARGET=X.0` env も CI で設定する（Mach-O `LC_BUILD_VERSION` を runner OS バージョンに固定するため必須。これが無いと macos-15 runner で作った wheel が `LC_BUILD_VERSION=15.0` になり 14.0 ホストでロードできない。`wheel tags` でファイル名だけ書き換えても ABI 不整合は解消しない）
- Windows wheel タグ: `cp3XY-cp3XY-win_amd64`（scikit-build-core デフォルトで生成される。`wheel tags` post-process は通常不要）
- ローカル dev 用 CMake option:
  - `SORA_LOCAL_WEBRTC_BUILD_DIR`: 指定時は `fetch_deps.cmake` の WebRTC fetch を skip し、指定パスから `include/` `lib/` `VERSIONS` を参照する
  - `SORA_LOCAL_SORA_CPP_SDK_DIR`: 同様に Sora C++ SDK fetch を skip
- `BUILD_PROFILE=debug` 時の `+debug` バージョン suffix は 0001 で実装済み。本 issue では Windows / macOS で同じ挙動が動くことを確認するだけ
- `build-debug.yml` への macOS / Windows job 追加（現状 `build-debug.yml` は ubuntu のみで macOS / Windows job は存在しないため新規追加。0001 で `if: false` した対象には含まれていない）
- `SORA_GEN_PYI` 設定:
  - macOS arm64 ネイティブ: `ON`（0001 デフォルト維持）
  - Windows x86_64: `OFF`（Windows は MSVC で nanobind_add_stub の Python 実行に追加要件があるため、既存 `run.py:376-380` の方針を踏襲）。`[[tool.scikit-build.overrides]] cmake.define.SORA_GEN_PYI = "OFF"`
- 0001 で disable された `build_macos` / `build_windows` job 全体を再有効化する
- 0002 で追加された `verify_macos_fetch_deps` job を削除する（本 issue で `build_macos` 全体が wheel build まで含めて動くため不要）
- `CHANGES.md` の 0001 `[CHANGE]` エントリに macOS / Windows / クロス対応の追記を行う

含まない（別 issue で扱う）:

- PyPI publish 用 `auditwheel repair --strip --only-plat` 経由の manylinux 化（0006。macOS / Windows は manylinux 概念がないため対象外）
- `_PYTHON_HOST_PLATFORM` の Linux クロス対応（0003 / 0004 で扱い済み）
- pyi / py.typed の wheel 同梱経路（0006 で `build_pyi` 廃止後の代替）
- `auditwheel show` での実シンボル検証（0006）
- ローカル `run.py build` 互換性維持（0006 で `run.py` 削除）

## 依存 issue への影響（事実記述）

- 0001 / 0002 / 0003 / 0004 完了状態を前提とする
- 0001 polish 済み内容で `TARGET_OS` cache 変数を全 override に明示する必要がある（0004 で同様の指摘があった）。0001 の overrides 例には `cmake.define.TARGET_OS` が無いため、本 issue で macOS / Windows override に追加するついでに 0001 polish 担当に「ubuntu-24.04 x86_64 ネイティブ override にも `cmake.define.TARGET_OS = "ubuntu"` を追加する」を申し送る
- 0006 polish 時に「macOS / Windows wheel の `auditwheel show` 相当の検証手順は不要（manylinux 概念がない）」を解決方法に明記する必要がある

## 現状

- `run.py:320-332` macOS arm64 クロス相当の cmake 引数生成（libwebrtc 同梱 clang / `-isystem ${LIBCXX_INCLUDE_DIR}` / `xcrun --sdk macosx --show-sdk-path` 経由 sysroot）
- Windows は `run.py` で特別な cmake 引数を渡さず、`CMakeLists.txt:174-189` の MSVC 設定がそのまま効く
- `setup.py:bdist_wheel.get_tag()` は macOS / Windows で plat タグをカスタムしない（デフォルトの packaging.tags 経路）
- 既存 CI:
  - `build_macos` matrix: `macos-14` / `macos-15` × Python 3.12 / 3.13 / 3.14。`_PYTHON_HOST_PLATFORM=macosx-X.0-arm64` / `ARCHFLAGS=-arch arm64` env を渡し、`uv run python run.py build macos_arm64` + `uv build` の 2 段階
  - `build_windows` matrix: `windows-2025` × Python 3.12 / 3.13 / 3.14。`uv run python run.py build windows_x86_64` + `uv build` の 2 段階
- `run.py:469-481` の `--local-webrtc-build-dir` / `--local-sora-cpp-sdk-dir` は `buildbase.py:build_webrtc` / `build_sora` を呼ぶ。これは別プロセスで C++ SDK 自体をビルドする経路で、本 issue の `SORA_LOCAL_*_DIR` cache 変数は「既にビルド済みのパスを参照する」のみ（local build は呼ばない）
- 0001 完了時点で `cmake_minimum_required` / `find_package(Python)` / `nanobind --cmake_dir` / `set(TARGET_OS ...)` / `option(SORA_GEN_PYI ON CACHE BOOL)` / `fetch_deps.cmake` include 済み
- 0001 で `[CHANGE] build backend を setuptools から scikit-build-core に切り替える` の develop 先頭追加済み
- 0002 完了時点で `_sora_fetch_llvm(fetch_clang=TRUE)` 経路 / `CLANG_DIR` cache 変数 / macOS ホスト判定の `SORA_PYTHON_SDK_PLATFORM = macos_arm64 / macos_x86_64` 算出ロジック / `verify_macos_fetch_deps` job 追加済み

## 設計方針

### `SORA_PYTHON_SDK_PLATFORM` 自動検出への Windows 対応

- 0002 完了時点で `Darwin` 分岐は実装済み。本 issue で `Windows` 分岐を追加:
  - `CMAKE_HOST_SYSTEM_NAME = Windows` のとき `CMAKE_HOST_SYSTEM_PROCESSOR`（Windows runner では `AMD64`）を `_SORA_HOST_ARCH` に正規化（`AMD64` → `x86_64`）し、組み立て `windows_${_SORA_HOST_ARCH}`
  - `ARM64`（Windows on ARM）など `AMD64` 以外は `FATAL_ERROR`
  - `_SORA_HOST_ARCH` は `LLVM_HOST_KEY` 組み立てにも使う（Windows では `x86_64-Windows`）。ただし 0005 では Windows native で clang バイナリ取得は不要（MSVC 使用のため `fetch_clang=FALSE`）

### `fetch_deps.cmake` の Windows 対応

- 0001 / 0002 完了時点で `_sora_fetch_archive` は `.tar.gz` 固定。**Windows native の WebRTC / Sora / Boost archive は `.zip` 配布**のため、`deps.json` スキーマと `_sora_fetch_archive` 関数を以下のように拡張:

  ```json
  {
    "webrtc": {
      "version": "m149.7827.0.0",
      "url_template": "https://github.com/shiguredo-webrtc-build/webrtc-build/releases/download/{version}/webrtc.{platform}.{ext}",
      "strip_components": 1
    }
  }
  ```

  `{ext}` の解決は **target platform ベース**で行う（`SORA_PYTHON_SDK_PLATFORM` が `windows_*` なら `zip`、それ以外は `tar.gz`）。0003 の armv8 cross は host=Linux だが target=Linux なので `tar.gz` で正しい
- `_sora_fetch_archive` のシグネチャを 0001 の 5 引数 `(name url stamp_path dest_dir strip)` から 6 引数 `(name url stamp_path dest_dir strip archive_ext)` に拡張。0003 / 0004 で 0001 の関数を呼び出す箇所は **target が Linux であれば本 issue で第 6 引数 `tar.gz` を追加した形に書き換える必要がある**（0003 / 0004 polish 後に 0005 が 0001 / 0002 / 0003 / 0004 の呼び出し側を一括で 6 引数版に書き換える）
- 展開ロジックを zip / tar.gz で分岐:
  - tar.gz: `execute_process(COMMAND ${CMAKE_COMMAND} -E tar xzf <archive> --strip-components=<n>)`
  - zip: `execute_process(COMMAND ${CMAKE_COMMAND} -E tar xf <archive> --strip-components=<n>)`（`cmake -E tar` は zip を `xf` で展開可。`--strip-components` の zip 対応は CMake 3.18+ で実機検証が必要 - 完了条件に追加）
- stamp の `<url>` を解決済み URL で書く 0001 設計はそのまま。同じ target platform 内では `{ext}` は不変なので、stamp 不一致による意図しない再 fetch は起きない

### Windows native での OpenH264 取得 skip

- `CMakeLists.txt:192-199` は Windows 以外でのみ OpenH264 ヘッダ参照と `dynamic_h264_*.cpp` コンパイルを行う設計。Windows native では OpenH264 ヘッダ取得は完全に不要
- `fetch_deps.cmake` のメインスクリプト末尾で `_sora_fetch_openh264` 呼び出しを以下でガード:

  ```cmake
  if(NOT SORA_PYTHON_SDK_PLATFORM MATCHES "^windows_")
    _sora_fetch_openh264(...)
    set(OPENH264_DIR "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/openh264" CACHE PATH "" FORCE)
  endif()
  ```

  Windows ホスト native では `make` が無く `_sora_fetch_openh264` が configure 段階で `FATAL_ERROR` で落ちるため、このガードが無いと Windows native ビルド全体が失敗する

### CMakeLists.txt の OS 別 compile options 整理

- 既存 `CMakeLists.txt:111-190` の OS 別 compile options は基本的に維持する
- macOS 分岐（L111-131）: 既存の `-nostdinc++ -isystem${LIBCXX_INCLUDE_DIR}` 等は変更なし。0002 で `CLANG_DIR` 経由でコンパイラが設定される（`fetch_deps.cmake` include 直後の `if(CLANG_DIR) set(CMAKE_C_COMPILER ${CLANG_DIR}/bin/clang ...) endif()` 0003 で追加済み）
- Windows 分岐（L174-189）: 既存の MSVC 設定（`MSVC_RUNTIME_LIBRARY` / `/utf-8 /bigobj` / `_WIN32_WINNT=0x0A00` / `WIN32_LEAN_AND_MEAN`）は変更なし
- macOS の `CMAKE_OSX_SYSROOT` / `CMAKE_OSX_ARCHITECTURES` / `CMAKE_OSX_DEPLOYMENT_TARGET` は **`CMakeLists.txt` の `project()` 行（既存 L2）の直前** に書く（CMake 仕様で `project()` 前にしか効かないため）:

  ```cmake
  cmake_minimum_required(VERSION 4.1)
  # project() より前に macOS 関連を設定する
  if(APPLE)
    if(NOT DEFINED CMAKE_OSX_SYSROOT)
      execute_process(
        COMMAND xcrun --sdk macosx --show-sdk-path
        OUTPUT_VARIABLE _macos_sdk
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE _r
      )
      if(_r EQUAL 0 AND _macos_sdk)
        # cache に書かない (Xcode 更新で SDK パス変更されたとき再算出するため)
        set(CMAKE_OSX_SYSROOT "${_macos_sdk}")
      endif()
    endif()
    if(NOT DEFINED CMAKE_OSX_ARCHITECTURES)
      set(CMAKE_OSX_ARCHITECTURES "arm64")
    endif()
    if(NOT DEFINED CMAKE_OSX_DEPLOYMENT_TARGET)
      # MACOSX_DEPLOYMENT_TARGET env から取る、無ければ 14.0 既定
      if(DEFINED ENV{MACOSX_DEPLOYMENT_TARGET})
        set(CMAKE_OSX_DEPLOYMENT_TARGET "$ENV{MACOSX_DEPLOYMENT_TARGET}")
      else()
        set(CMAKE_OSX_DEPLOYMENT_TARGET "14.0")
      endif()
    endif()
  endif()
  project(sora_sdk)
  ```

  `CACHE PATH "" FORCE` で書くと Xcode 更新時に古い SDK パスを参照するため、`CMAKE_OSX_SYSROOT` は cache に書かず通常変数として設定する（毎回 configure で再算出）。`CMAKE_OSX_DEPLOYMENT_TARGET` は `MACOSX_DEPLOYMENT_TARGET` env を優先し、未指定時は 14.0 既定（macos-14 runner / macos-15 runner で `MACOSX_DEPLOYMENT_TARGET=14.0` / `15.0` を env で渡せば runner OS バージョンと一致する）
- これらすべての設定は `if(APPLE)` ガード内で行うため Linux / Windows configure では無視される

### ローカル dev 用 CMake option

- `cmake/scripts/fetch_deps.cmake` の冒頭で次の cache option を宣言:

  ```cmake
  set(SORA_LOCAL_WEBRTC_BUILD_DIR "" CACHE PATH "Local libwebrtc-build directory (skip WebRTC fetch)")
  set(SORA_LOCAL_SORA_CPP_SDK_DIR "" CACHE PATH "Local Sora C++ SDK directory (skip Sora fetch)")
  ```

- WebRTC fetch ロジックを `if(SORA_LOCAL_WEBRTC_BUILD_DIR)` で分岐。ディレクトリ構造は `buildbase.py:648-672` `get_webrtc_info` の `local_webrtc_build_dir` 分岐を CMake に逐語移植:

  ```cmake
  if(SORA_LOCAL_WEBRTC_BUILD_DIR)
    # BUILD_PROFILE=debug 時は configuration=debug、それ以外は release
    set(_configuration "release")
    if(DEFINED ENV{BUILD_PROFILE} AND $ENV{BUILD_PROFILE} STREQUAL "debug")
      set(_configuration "debug")
    endif()
    set(_webrtc_src "${SORA_LOCAL_WEBRTC_BUILD_DIR}/_source/${SORA_PYTHON_SDK_PLATFORM}/webrtc/src")
    set(_webrtc_build "${SORA_LOCAL_WEBRTC_BUILD_DIR}/_build/${SORA_PYTHON_SDK_PLATFORM}/${_configuration}/webrtc")
    set(WEBRTC_INCLUDE_DIR "${_webrtc_src}" CACHE PATH "" FORCE)
    set(WEBRTC_LIBRARY_DIR "${_webrtc_build}" CACHE PATH "" FORCE)
    set(LIBCXX_INCLUDE_DIR "${_webrtc_src}/third_party/libc++/src/include" CACHE PATH "" FORCE)
    set(LIBCXXABI_INCLUDE_DIR "${_webrtc_src}/third_party/libc++abi/src/include" CACHE PATH "" FORCE)
    set(CLANG_DIR "${_webrtc_src}/third_party/llvm-build/Release+Asserts" CACHE PATH "" FORCE)
    # VERSIONS ファイルは ${SORA_LOCAL_WEBRTC_BUILD_DIR}/VERSION (大文字単数) を読む
  else()
    _sora_fetch_archive(webrtc ...)
    _sora_fetch_llvm(...)
  endif()
  ```

- Sora C++ SDK ローカル経路は `buildbase.py:1061-1071` `get_sora_info` の `local_sora_cpp_sdk_dir` 分岐を移植:

  ```cmake
  if(SORA_LOCAL_SORA_CPP_SDK_DIR)
    set(SORA_DIR   "${SORA_LOCAL_SORA_CPP_SDK_DIR}/_install/${SORA_PYTHON_SDK_PLATFORM}/${_configuration}/sora"  CACHE PATH "" FORCE)
    set(Boost_ROOT "${SORA_LOCAL_SORA_CPP_SDK_DIR}/_install/${SORA_PYTHON_SDK_PLATFORM}/${_configuration}/boost" CACHE PATH "" FORCE)
  else()
    _sora_fetch_archive(sora_cpp_sdk ...)
    _sora_fetch_archive(boost ...)
  endif()
  ```

- ローカル dev 経路の使用例: `uv build --wheel -Ccmake.define.SORA_LOCAL_SORA_CPP_SDK_DIR=/path/to/sora-cpp-sdk -Ccmake.define.SORA_LOCAL_WEBRTC_BUILD_DIR=/path/to/webrtc-build`（uv の build flag passthrough）
- ローカル経路を選んだ時点で `_sora_fetch_llvm` / `_sora_fetch_archive` は呼ばないため、clang バイナリも libcxx も local build 内のものを使う

### pyproject.toml overrides

- macOS arm64 / Windows x86_64 × Python 3.12 / 3.13 / 3.14 の 6 件 override を追加。macOS は macos-14 / macos-15 を含めると 12 件になるが、`wheel.tags` 経路が動かなければ CI step で `wheel tags` post-process する方針なので、override では macOS バージョン非依存に絞る:

  ```toml
  [[tool.scikit-build.overrides]]
  if.env.SORA_SDK_TARGET = "^macos_arm64$"
  cmake.define.SORA_PYTHON_SDK_PLATFORM = "macos_arm64"
  cmake.define.TARGET_OS = "macos"
  cmake.define.SORA_GEN_PYI = "ON"

  [[tool.scikit-build.overrides]]
  if.env.SORA_SDK_TARGET = "^windows_x86_64$"
  cmake.define.SORA_PYTHON_SDK_PLATFORM = "windows_x86_64"
  cmake.define.TARGET_OS = "windows"
  cmake.define.SORA_GEN_PYI = "OFF"
  ```

  toolchain ファイルは macOS / Windows native では不要（toolchain なしで動く）
- ubuntu native も `cmake.define.TARGET_OS = "ubuntu"` を 0001 polish で追加する必要がある（本 issue 範囲外、申し送り）

### wheel タグ強制

- macOS / Windows native の wheel タグは scikit-build-core デフォルトで以下になる:
  - macOS: `cp3XY-cp3XY-macosx_X_Y_arm64`（ホスト Python の sysconfig 由来）
  - Windows: `cp3XY-cp3XY-win_amd64`
- `_PYTHON_HOST_PLATFORM=macosx-14.0-arm64` env を CI で設定すると wheel タグの platform 部分が `macosx_14_0_arm64` に固定される（macos-15 runner でビルドしても macOS 14 互換タグになる）
- 既存 CI は `_PYTHON_HOST_PLATFORM` を runner OS バージョン分（`macosx-14.0-arm64` / `macosx-15.0-arm64`）使い分けている。0005 もこれを踏襲
- Windows は `_PYTHON_HOST_PLATFORM` 不要（デフォルト `win_amd64` で正しい）
- `wheel.tags` 設定キーが scikit-build-core で機能しない場合は `wheel tags --remove --platform-tag macosx_14_0_arm64 dist/*.whl` を CI step で実行する

### CI 再有効化

- 0001 で `build_macos` / `build_windows` job 全体に `if: false` を追加した状態を本 issue で解除する
- 0002 で追加された `verify_macos_fetch_deps` job を削除する（`build_macos` 全体が wheel build まで動くため不要）
- `build_macos` matrix の各 entry で:
  - `uv run python run.py build macos_arm64` step を削除
  - `uv build --wheel` step を残し、env `SORA_SDK_TARGET=macos_arm64` / `_PYTHON_HOST_PLATFORM=macosx-X.0-arm64` を渡す
  - `needs: [build_pyi]` は 0001 で削除済み
- `build_windows` matrix も同様に `uv build --wheel` step に集約

### `BUILD_PROFILE=debug` 動作確認

- 0001 で実装した `BUILD_PROFILE=debug` 連動の `+debug` バージョン suffix と `cmake.build-type = "Debug"` override が macOS / Windows でも動くことを `.github/workflows/build-debug.yml` で確認する
- `build-debug.yml` の macOS / Windows job も再有効化する

## 完了条件

- macos-15 GitHub Actions runner（arm64）で以下が成功する:
  - `SORA_SDK_TARGET=macos_arm64 _PYTHON_HOST_PLATFORM=macosx-15.0-arm64 uv build --wheel`（Python 3.12 / 3.13 / 3.14 それぞれ）
  - 生成 wheel ファイル名: `sora_sdk-<version>-cp3XY-cp3XY-macosx_15_0_arm64.whl`
- macos-14 GitHub Actions runner で `_PYTHON_HOST_PLATFORM=macosx-14.0-arm64` 版も同様に成功
- windows-2025 GitHub Actions runner で:
  - `SORA_SDK_TARGET=windows_x86_64 uv build --wheel`（Python 3.12 / 3.13 / 3.14 それぞれ）
  - 生成 wheel ファイル名: `sora_sdk-<version>-cp3XY-cp3XY-win_amd64.whl`
- macOS / Windows ともに wheel 内 `sora_sdk/sora_sdk_ext.*.so` または `.pyd` が含まれる。macOS のみ `sora_sdk_ext.pyi` / `py.typed` 含む（Windows は SORA_GEN_PYI=OFF）
- `BUILD_PROFILE=debug uv build --wheel` で wheel 内 `SORA_PYTHON_SDK_VERSION` C++ マクロに `+debug` 含まれることを確認
- `cmake.define.SORA_LOCAL_SORA_CPP_SDK_DIR=/path/to/sora-cpp-sdk` 指定時に `fetch_deps.cmake` が Sora C++ SDK の fetch を skip し、ローカルパス経由で `find_package(Sora)` が成立する
- 0001 / 0002 / 0003 / 0004 経路に regression なし
- CI `build_macos` / `build_windows` 全 matrix entry が green。`verify_macos_fetch_deps` job は削除済み
- `build-debug.yml` の macOS / Windows job も green

## 解決方法

- `cmake/scripts/fetch_deps.cmake`
  - `SORA_PYTHON_SDK_PLATFORM` 自動検出に Windows 分岐（`CMAKE_HOST_SYSTEM_NAME = Windows`、`AMD64` → `x86_64` 正規化）を追加
  - `_SORA_HOST_ARCH` 中間変数を導入し、`SORA_PYTHON_SDK_PLATFORM` / `LLVM_HOST_KEY` の両方で使う
  - `_sora_fetch_archive` のシグネチャを 6 引数 `(name url stamp_path dest_dir strip archive_ext)` に拡張。`archive_ext` が `zip` のとき `${CMAKE_COMMAND} -E tar xf` を使う
  - `deps.json` のスキーマに `ext_per_os` フィールドを追加（または `url_template` 内 `{ext}` を OS 別に解決する）
  - WebRTC / Sora / Boost の URL テンプレート展開時に `{ext}` を `${CMAKE_HOST_SYSTEM_NAME}` 別に決定（Linux/Darwin = tar.gz、Windows = zip）
  - 冒頭に `set(SORA_LOCAL_WEBRTC_BUILD_DIR "" CACHE PATH "...")` / `SORA_LOCAL_SORA_CPP_SDK_DIR` を宣言
  - WebRTC fetch / Sora fetch を `if(SORA_LOCAL_*_DIR)` で分岐し、ローカルパス参照経路を追加
- `CMakeLists.txt`
  - macOS 分岐の前に `xcrun --sdk macosx --show-sdk-path` 経由 `CMAKE_OSX_SYSROOT` 設定と `CMAKE_OSX_ARCHITECTURES = arm64` 設定を追加
- `pyproject.toml`
  - `[[tool.scikit-build.overrides]]` を 2 件追加（macos_arm64 / windows_x86_64）
- `.github/workflows/build.yml`
  - `build_macos` job 全体から `if: false` を削除
  - `build_windows` job 全体から `if: false` を削除
  - 0002 で追加された `verify_macos_fetch_deps` job を削除
  - `build_macos` / `build_windows` の `uv run python run.py build ...` step を削除し、`uv build --wheel` のみ残す
  - env に `SORA_SDK_TARGET` / `_PYTHON_HOST_PLATFORM` 設定（既存 env をそのまま流用）
  - wheel タグが期待通りでない場合の `wheel tags` post-process step を CI に追加（実装時に scikit-build-core 仕様確認後、必要なら追加）
- `.github/workflows/build-debug.yml`
  - macOS / Windows job を **新規追加**（現状 `build-debug.yml` は ubuntu のみ）。各 job で `BUILD_PROFILE=debug` env 付きで `uv build --wheel` を実行
  - 既存 `build-debug.yml:169` の `uv run python run.py build` ステップは 0006 で `run.py` 削除されるため、本 issue で `uv build --wheel` に置換する必要があるか確認（または 0006 までは現状維持）
- `CHANGES.md`
  - 0001 で追加した `[CHANGE] build backend を setuptools から scikit-build-core に切り替える` エントリの直下にサブ箇条書きで以下を追加（または CHANGE エントリ本文を「scikit-build-core 経路で全 platform (ubuntu / macOS / Windows / armv8 cross / jetson / RPi) の wheel ビルドを完結させる」に書き換える）:

  ```
    - macOS arm64 / Windows x86_64 / ubuntu armv8 / jetson / RPi 全 platform 対応
    - @voluntas
  ```

  既存 `[UPDATE] setuptools / wheel` エントリは 0001 で削除済み
- `tests/` 変更なし
- 1 ステップ目に実装する検証: `uv build --wheel` で生成された macOS wheel に対して `wheel show dist/*.whl` で実際の tag を確認し、`wheel.tags` override が効くか / `wheel tags` post-process が必要か判定する
