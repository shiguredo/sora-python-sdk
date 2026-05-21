# Windows x86_64 ネイティブビルド対応

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-windows-x86-64-native-build

## 目的

0001 で ubuntu-24.04 x86_64 native 向けに実装した scikit-build-core + `cmake/scripts/fetch_deps.cmake` を Windows x86_64 でも動作させ、 Windows host 上で `uv build --wheel` 一発で Windows x86_64 用 wheel を生成できる状態にする。 0001 で `if: false` で disable していた `build_windows` job を復活させる。

## 設計の前提（プロジェクト全体の新方針からの該当部）

- ビルド環境は ubuntu-24.04 x86_64 host のみに集約するが、 macOS (arm64) と **Windows (x86_64) は例外的にそれぞれの OS で native build を維持する** （ cross-compile しない）
- Windows native は Windows x86_64 runner で native build する
- Windows は **MSVC + Windows SDK 同梱ランタイム** でビルドする。 libwebrtc 同梱 clang は使わない（既存 `CMakeLists.txt:174-190` が MSVC 静的ランタイム前提）。 libcxx / libcxxabi も使わない（ MSVC 標準 STL を使う）
- 0001 で実装した `_sora_fetch_llvm` は ubuntu / macOS 経路で必要だが、 Windows では呼ばない

## スコープ

含む:

- `cmake/scripts/fetch_deps.cmake` の `SORA_PYTHON_SDK_PLATFORM` 算出を Windows host 対応に拡張する（ `CMAKE_HOST_SYSTEM_NAME = Windows` 分岐で `windows_x86_64` を組み立てる）
- `_sora_fetch_llvm` の呼び出しを `if(NOT WIN32)` ガードで囲み、 Windows では LLVM 取得を skip する。 `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` は scikit-build-core / CMake のデフォルト探索（ MSVC ）に任せる
- `_sora_fetch_openh264` の **Windows 経路** を新規実装する。 Windows には `make` が無いため、 `buildbase.py:1637-1647` 相当の `codec/api/wels/codec*.h` 手動コピーを CMake で実装する
- WebRTC / Sora / Boost アーカイブの Windows 拡張子は `.zip` （ Linux / macOS は `.tar.gz` ）。 `deps.json` の `url_template` に `{ext}` プレースホルダを追加するか、 Windows 専用 url_template を別キーで持つか判断する
- `pyproject.toml` に `[[tool.scikit-build.overrides]]` で Windows の `TARGET_OS = "windows"` 上書きを追加する
- Windows native での `uv build --wheel` 成功と `pytest tests/test_version.py` 完走（ wheel タグは `cp3XY-cp3XY-win_amd64` ）
- `.github/workflows/build.yml` の `build_windows` job の `if: false` を解除し、 scikit-build-core 経路で完結させる
- `slack_notify` の `needs:` に `build_windows` を戻す
- `SORA_GEN_PYI` を Windows では `OFF` にする（既存 `run.py:376-380` の方針踏襲。 Windows では `nanobind_add_stub` の Python 実行に追加要件があるため）

含まない（別 issue で扱う）:

- macOS arm64 native （ 0002 ）
- Linux arm64 cross-compile （ 0003 / 0004 ）
- レガシーファイル削除（ 0006 ）
- Makefile （ 0007 ）
- ローカル dev 用 CMake option（ `SORA_LOCAL_WEBRTC_BUILD_DIR` 等。別途新 issue で扱う）
- Windows x86 (32-bit) （プロジェクトでサポート対象外）
- Windows arm64 （プロジェクトでサポート対象外）

## 現状

- `run.py` は Windows native のとき特別な cmake 引数を渡さず、 `CMakeLists.txt:174-189` の MSVC 設定がそのまま効く（`/utf-8 /bigobj` / `MSVC_RUNTIME_LIBRARY MultiThreaded` / `_CONSOLE _WIN32_WINNT=0x0A00 NOMINMAX WIN32_LEAN_AND_MEAN HAVE_SNPRINTF` ）
- `buildbase.py:1637-1647` の Windows OpenH264 手動コピーは `codec/api/wels/codec*.h` を `${install_dir}/openh264/include/wels/` にコピーする
- 既存 `setup.py:bdist_wheel.get_tag()` は Windows で plat タグをカスタムせず、 デフォルトの `win_amd64` が付く
- `CMakeLists.txt:174-189` の `if(TARGET_OS STREQUAL "windows")` ブランチで MSVC 設定が有効化される
- `CMakeLists.txt:65-67` で `TARGET_OS STREQUAL "windows"` のとき `Boost_USE_STATIC_RUNTIME ON` を立てる既存実装
- `CMakeLists.txt:193-199` の `if (NOT TARGET_OS STREQUAL "windows")` で OpenH264 ヘッダ参照と `dynamic_h264_*.cpp` を取り込んでいる。 Windows は **このブランチに入らず OpenH264 を使わない**
- ただし Sora アーカイブの Windows 用は **`.zip` 形式** （ Linux / macOS の `.tar.gz` と違う）
- 既存 `build.yml:281-321` の `build_windows` job は `windows-2025_x86_64` runner で Python 3.12 / 3.13 / 3.14 を回し、 `uv run python run.py build windows_x86_64` + `uv build` を実行する 2 段構成

## 設計方針

### SORA_PYTHON_SDK_PLATFORM 算出の Windows 対応

```cmake
if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Windows")
  if(CMAKE_HOST_SYSTEM_PROCESSOR MATCHES "^(AMD64|x86_64)$")
    set(SORA_PYTHON_SDK_PLATFORM "windows_x86_64" CACHE STRING "")
  else()
    message(FATAL_ERROR
      "Windows host must be x86_64; got '${CMAKE_HOST_SYSTEM_PROCESSOR}'. "
      "Windows arm64 / x86 are not supported.")
  endif()
endif()
```

`CMAKE_HOST_SYSTEM_PROCESSOR` は Windows では `AMD64` を返す。 `deps.json` の `{platform}` プレースホルダ展開後の値（ `windows_x86_64` ）は既存 Sora C++ SDK アーカイブ命名と一致する。

許容 `SORA_PYTHON_SDK_PLATFORM` リストに `windows_x86_64` を追加する。

### deps.json の Windows アーカイブ拡張子対応

Windows のアーカイブは `.zip` 形式のため、 `deps.json` に拡張子を持たせる:

```json
{
  "webrtc": {
    "version": "m149.7827.0.0",
    "url_template": "https://github.com/shiguredo-webrtc-build/webrtc-build/releases/download/{version}/webrtc.{platform}.{ext}",
    "strip_components": 1
  },
  ...
}
```

`{ext}` は `fetch_deps.cmake` で `SORA_PYTHON_SDK_PLATFORM MATCHES "^windows_"` のとき `zip` 、 それ以外で `tar.gz` を選ぶ。

`_sora_fetch_archive` を `zip` 対応に拡張する:

- 展開コマンドは `${CMAKE_COMMAND} -E tar xzf` で zip も対応する（ CMake の `tar` モードは `-E tar` で実は zip も解凍できる。 cmake 4.x で確認済み）
- `--strip-components` は zip でも動く

### _sora_fetch_openh264 の Windows 経路

Windows では `find_program(make)` が失敗するため、 `if(WIN32)` 分岐で **`codec/api/wels/codec*.h` を直接コピー** する処理を実装する:

```cmake
function(_sora_fetch_openh264 version git_url dest stamp_path)
  # ... stamp check ...
  _sora_git_shallow("${git_url}" "${version}" "${_src}")

  if(WIN32)
    # buildbase.py:1640-1647 と同等
    file(MAKE_DIRECTORY "${dest}/include/wels")
    file(GLOB _wels_headers "${_src}/codec/api/wels/codec*.h")
    foreach(_h ${_wels_headers})
      configure_file("${_h}" "${dest}/include/wels/" COPYONLY)
    endforeach()
  else()
    # 既存 make install-headers 経路 (0001 で実装済み)
    find_program(_SORA_MAKE_EXECUTABLE make)
    if(NOT _SORA_MAKE_EXECUTABLE)
      message(FATAL_ERROR
        "OpenH264 header installation requires 'make'. "
        "On Debian/Ubuntu: run 'apt-get install build-essential'. "
        "On macOS: run 'xcode-select --install'.")
    endif()
    execute_process(
      COMMAND "${_SORA_MAKE_EXECUTABLE}" -C "${_src}" install-headers "PREFIX=${dest}"
      RESULT_VARIABLE _make_result)
    if(NOT _make_result EQUAL 0)
      message(FATAL_ERROR "Failed to install openh264 headers (make install-headers PREFIX=${dest})")
    endif()
  endif()
  # ... stamp write ...
endfunction()
```

ただし 0001 で `Windows は OpenH264 を使わない` （ `CMakeLists.txt:193-199` の `if (NOT TARGET_OS STREQUAL "windows")` ガード）と確定している。 OpenH264 取得自体を Windows で skip する判断もあり得る。 整理:

- 案 A: Windows でも `_sora_fetch_openh264` を呼ぶが、 ヘッダだけコピー（ `dynamic_h264_*.cpp` は Windows では include されないため実害なし）
- 案 B: Windows では `_sora_fetch_openh264` を完全 skip（ `_sora_fetch_archive` の openh264 呼び出しを `if(NOT WIN32)` で囲む）

案 B を採る。 Windows では OpenH264 は実体的に不要なため、 fetch 自体を skip して時間を節約する。

### _sora_fetch_llvm の Windows skip

メインスクリプトで:

```cmake
if(NOT WIN32)
  _sora_fetch_llvm("${_PLATFORM_ROOT}/webrtc" "${_LLVM_ROOT}" "${_LLVM_STAMPS_ROOT}/llvm")
  set(_SORA_CLANG_DIR "${_LLVM_ROOT}/clang" CACHE PATH "" FORCE)
endif()
```

Windows では `_SORA_CLANG_DIR` を設定しない。 `CMakeLists.txt` 側で `if(NOT WIN32 AND _SORA_CLANG_DIR)` ガードで `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` を設定するように 0001 の指示を修正する（ 0005 polish に含める）。

### TARGET_OS の Windows 上書き

`pyproject.toml` に override を追加する:

```toml
[[tool.scikit-build.overrides]]
if.platform-system = "win32"
cmake.define.TARGET_OS = "windows"
cmake.define.SORA_GEN_PYI = "OFF"
```

scikit-build-core の `if.platform-system = "win32"` は `sys.platform` ベースで Windows にマッチする。

`SORA_GEN_PYI = OFF` 設定は既存 `run.py:376-380` の方針踏襲。

### LIBCXX / LIBCXXABI ガード

Windows では libcxx / libcxxabi を使わないため、 `CMakeLists.txt` の cache 確定処理で `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` が空でも問題ないようガードする:

- `CMakeLists.txt:132-143` の ubuntu 分岐と `:111-131` の macOS 分岐は `TARGET_OS=windows` では入らないため自動的に skip される
- `fetch_deps.cmake` のメインスクリプト末尾の `set(LIBCXX_INCLUDE_DIR ... CACHE PATH "" FORCE)` を `if(NOT WIN32) ... endif()` で囲む

### Boost / OpenH264 アーカイブの Windows 命名確認

実機確認:

```
curl -sL https://github.com/shiguredo-webrtc-build/webrtc-build/releases/download/m149.7827.0.0/webrtc.windows_x86_64.zip | unzip -l | head -10
curl -sL https://github.com/shiguredo/sora-cpp-sdk/releases/download/2026.2.0-canary.11/sora-cpp-sdk-2026.2.0-canary.11_windows_x86_64.zip | unzip -l | head -10
curl -sL https://github.com/shiguredo/sora-cpp-sdk/releases/download/2026.2.0-canary.11/boost-1.91.0_sora-cpp-sdk-2026.2.0-canary.11_windows_x86_64.zip | unzip -l | head -10
```

`strip_components` 値を確定する（ Windows zip でも `1` で動くか確認）。

### CI 影響

- `build_windows` job （既存 `build.yml:281` ）の `jobs.build_windows.if: false` を削除する
- `build_windows` job の `needs: [build_pyi]` を完全削除する
- `build_windows` job の `download-artifact` / `cp` 系ステップを削除する
- `uv run python run.py build windows_x86_64` 行を削除し、 `uv build` のみを残す
- `slack_notify` job の `needs:` に `build_windows` を戻す

## 完了条件

- Windows x86_64 host （ `windows-2025_x86_64` runner ） + Python 3.12 / 3.13 / 3.14 で `uv build --wheel` が成功する
- 生成された wheel タグが `cp312-cp312-win_amd64` 等になる
- wheel 内に `sora_sdk/sora_sdk_ext.cp3XY-win_amd64.pyd` / Python ソースが含まれる（ pyi は Windows では OFF のため含まれない）
- 次の手順で動作確認が成功する:
  1. `uv venv`
  2. `uv sync --no-install-project`
  3. `uv build --wheel`
  4. `uv pip install --force-reinstall dist/*.whl`
  5. `uv run --no-sync pytest tests/test_version.py` が成功する
  6. `uv run --no-sync python -c "from sora_sdk import sora_sdk_ext; print(sora_sdk_ext.__file__)"` が `site-packages\sora_sdk\sora_sdk_ext.cp3XY-win_amd64.pyd` を出力する
- `_deps/windows_x86_64/{webrtc,sora,boost}` が 2 回目以降の `uv build --wheel` で再 DL されない（ openh264 / llvm は Windows では取得しないため対象外）
- CI で `build_windows` job が green になる

## 解決方法

### cmake/scripts/fetch_deps.cmake

- `SORA_PYTHON_SDK_PLATFORM` 算出に Windows 分岐追加
- `_sora_fetch_archive` を `.zip` 対応に拡張（拡張子と展開コマンド）
- `_sora_fetch_openh264` の Windows 経路追加（または `if(NOT WIN32)` で skip）
- `_sora_fetch_llvm` 呼び出しを `if(NOT WIN32)` ガード
- `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` の cache 確定を `if(NOT WIN32)` ガード
- 許容 `SORA_PYTHON_SDK_PLATFORM` リストに `windows_x86_64` 追加

### deps.json

`url_template` に `{ext}` プレースホルダを追加し、 `fetch_deps.cmake` 側で `tar.gz` / `zip` を選択する。

### pyproject.toml

Windows override を末尾に追加:

```toml
[[tool.scikit-build.overrides]]
if.platform-system = "win32"
cmake.define.TARGET_OS = "windows"
cmake.define.SORA_GEN_PYI = "OFF"
```

### CMakeLists.txt

- `if(NOT WIN32 AND _SORA_CLANG_DIR) set(CMAKE_C_COMPILER "${_SORA_CLANG_DIR}/bin/clang" ...) endif()` ガード調整
- 既存 `:174-189` の Windows ブランチは変更不要

### .github/workflows/build.yml

- `jobs.build_windows.if: false` を削除
- `jobs.build_windows.needs: [build_pyi]` を完全削除
- `actions/download-artifact` / `cp` ステップを削除
- `uv run python run.py build windows_x86_64` 行を削除し `uv build` のみ残す
- `jobs.slack_notify.needs` を `[build_ubuntu, build_macos]` から `[build_ubuntu, build_macos, build_windows]` に戻す

### CHANGES.md

`## develop` の `[CHANGE]` グループに追加:

```
- [CHANGE] Windows x86_64 ネイティブビルドを scikit-build-core 経路に移行する
  - @voluntas
```

## ロールバック

0005 マージ後に Windows build で問題が発覚した場合:

1. `git revert -m 1 <merge-commit>` で revert PR を作成
2. revert 後、 `build_windows` job が再び `if: false` に戻り skip されることを確認
3. `pyproject.toml` の Windows override が消えるか確認
4. forward fix を選ぶ判断: OpenH264 / アーカイブ拡張子の単一不具合なら追加コミットで対応する
