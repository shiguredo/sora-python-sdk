# Windows x86_64 ネイティブビルド対応

- Priority: High
- Created: 2026-05-21
- Updated: 2026-07-17
- Completed: 2026-07-23
- Model: Composer 2.5
- Branch: feature/change-windows-x86-64-native-build
- Polished: 2026-07-23

## 目的

0001 で ubuntu-24.04 x86_64 native 向けに実装する scikit-build-core + `cmake/scripts/fetch_deps.cmake` を Windows x86_64 でも動作させ、 Windows host 上で `uv build --wheel` 一発で Windows x86_64 用 wheel を生成できる状態にする。 0001 で `build_windows` job は build.yml から削除されるため、 scikit-build-core 経路の `build_windows` job を新設する。

## 設計の前提（プロジェクト全体の新方針からの該当部）

- ビルド環境は ubuntu-24.04 x86_64 host のみに集約するが、 macOS (arm64) と **Windows (x86_64) は例外的にそれぞれの OS で native build を維持する** （ cross-compile しない）
- Windows native は Windows x86_64 runner で native build する
- Windows は **MSVC + Windows SDK 同梱ランタイム** でビルドする。 libwebrtc 同梱 clang は使わない（既存 `CMakeLists.txt:166-182` が MSVC 静的ランタイム前提）。 libcxx / libcxxabi も使わない（ MSVC 標準 STL を使う）
- 0001 で実装される `_sora_fetch_llvm` は ubuntu / macOS 経路で必要だが、 Windows では呼ばない

## スコープ

含む:

- `cmake/scripts/fetch_deps.cmake` の `SORA_PYTHON_SDK_PLATFORM` 算出を Windows host 対応に拡張する（ `CMAKE_HOST_SYSTEM_NAME = Windows` 分岐で `windows_x86_64` を組み立てる）
- `_sora_fetch_llvm` の呼び出しを `if(NOT WIN32)` ガードで囲み、 Windows では LLVM 取得を skip する。 `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` は scikit-build-core / CMake のデフォルト探索（ MSVC ）に任せる
- `_sora_fetch_openh264` の Windows での扱いを確定する（後述の案 B: fetch 自体を skip ）。 参考として旧 `buildbase.py:1637-1647` （ 0001 で削除。 git 履歴参照）に Windows 用の `codec/api/wels/codec*.h` 手動コピー実装があった
- WebRTC / Sora / Boost アーカイブの Windows 拡張子は `.zip` （ Linux / macOS は `.tar.gz` ）。 fetch_deps.cmake の URL 組み立てに拡張子分岐を追加する（ 0001 は URL を fetch_deps.cmake 内で組み立てる方式。 deps.json は存在しない）
- `pyproject.toml` に `[[tool.scikit-build.overrides]]` で Windows の `TARGET_OS = "windows"` 上書きを追加する
- Windows native での `uv build --wheel` 成功と `pytest tests/test_version.py` 完走（ wheel タグは `cp3XY-cp3XY-win_amd64` ）
- `.github/workflows/build.yml` に scikit-build-core 経路の `build_windows` job を新設する（ 0001 で旧 job は削除済み）
- `slack_notify` の `needs:` に `build_windows` を追加する
- `SORA_GEN_PYI` を Windows では `OFF` にする（旧 `run.py:374-379` （ 0001 で削除。 git 履歴参照）の方針踏襲。 Windows では `nanobind_add_stub` の Python 実行に追加要件があるため）

含まない（別 issue で扱う）:

- macOS arm64 native （ 0002 ）
- Linux arm64 cross-compile （ 0003 / 0004 ）
- `publish_wheel` / `create-release` / e2e 復活等の CI 最終整理（ 0006 。 レガシーファイル削除は 0001 で完了済み）
- Makefile （ 0007 ）
- ローカル webrtc-build / sora-cpp-sdk ビルド経路の再設計（ 0006 。 build-debug.yml は 0001 で削除済み）
- Windows x86 (32-bit) （プロジェクトでサポート対象外）
- Windows arm64 （プロジェクトでサポート対象外）

## 現状

以下のレガシーファイル・旧 CI job への参照は 0001 で削除されるため、 実装時は git 履歴 (`git show <削除前コミット>:run.py` 等) で参照する:

- 旧 run.py は Windows native のとき特別な cmake 引数を渡さず、 `CMakeLists.txt` の MSVC 設定がそのまま効いていた（`/utf-8 /bigobj` / `MSVC_RUNTIME_LIBRARY MultiThreaded` / `_CONSOLE _WIN32_WINNT=0x0A00 NOMINMAX WIN32_LEAN_AND_MEAN HAVE_SNPRINTF` ）
- 旧 `buildbase.py:1637-1647` の Windows OpenH264 手動コピーは `codec/api/wels/codec*.h` を `${install_dir}/openh264/include/wels/` にコピーしていた
- 旧 `setup.py:bdist_wheel.get_tag()` は Windows で plat タグをカスタムせず、 デフォルトの `win_amd64` が付いていた
- 旧 `build.yml:281-319` の `build_windows` job は `windows-2025_x86_64` runner で Python 3.12 / 3.13 / 3.14 を回し、 `uv run python run.py build windows_x86_64` + `uv build` を実行する 2 段構成だった。 matrix 構成（ runner とラベル）は新設 job に引き継ぐ

現存する CMakeLists.txt:

- `CMakeLists.txt:166-182` の `elseif(TARGET_OS STREQUAL "windows")` ブランチで MSVC 設定が有効化される
- `CMakeLists.txt:65-67` で `TARGET_OS STREQUAL "windows"` のとき `Boost_USE_STATIC_RUNTIME ON` を立てる既存実装
- `CMakeLists.txt:185-191` の `if (NOT TARGET_OS STREQUAL "windows")` で OpenH264 ヘッダ参照と `dynamic_h264_*.cpp` を取り込んでいる。 Windows は **このブランチに入らず OpenH264 を使わない**
- ただし Sora アーカイブの Windows 用は **`.zip` 形式** （ Linux / macOS の `.tar.gz` と違う）

## 設計方針

### SORA_PYTHON_SDK_PLATFORM 算出の Windows 対応

```cmake
if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Windows")
  if(CMAKE_HOST_SYSTEM_PROCESSOR MATCHES "^(AMD64|x86_64)$")
    set(SORA_PYTHON_SDK_PLATFORM "windows_x86_64" CACHE STRING "" FORCE)
  else()
    message(FATAL_ERROR
      "Windows host must be x86_64; got '${CMAKE_HOST_SYSTEM_PROCESSOR}'. "
      "Windows arm64 / x86 are not supported.")
  endif()
endif()
```

`CMAKE_HOST_SYSTEM_PROCESSOR` は Windows では `AMD64` を返す。 platform 文字列 `windows_x86_64` は既存 Sora C++ SDK アーカイブ命名と一致する。

許容 `SORA_PYTHON_SDK_PLATFORM` リストに `windows_x86_64` を追加する。

### fetch_deps.cmake の URL 組み立ての Windows アーカイブ拡張子対応

Windows のアーカイブは `.zip` 形式のため、 fetch_deps.cmake の URL 組み立て（ 0001 で `DEPS` の値から組み立てる方式）に拡張子分岐を追加する:

- `SORA_PYTHON_SDK_PLATFORM MATCHES "^windows_"` のとき拡張子 `zip` 、 それ以外で `tar.gz` を選ぶ。 `DEPS` 自体の変更は不要
- `_sora_fetch_archive` の変更は保存ファイル名の拡張子可変化（ 0001 の `.archives/${name}.tar.gz` 固定を改める）のみ。 展開は 0001 の `file(ARCHIVE_EXTRACT)` + 単一トップディレクトリの動的判定がそのまま zip に効くため変更不要

### _sora_fetch_openh264 の Windows での扱い

Windows では `find_program(make)` が失敗するため、 `if(WIN32)` 分岐で **`codec/api/wels/codec*.h` を直接コピー** する実装（案 A ）も可能:

```cmake
function(_sora_fetch_openh264 version git_url dest stamp_path)
  # ... stamp check ...
  _sora_git_shallow("${git_url}" "${version}" "${_src}")

  if(WIN32)
    # 旧 buildbase.py:1642-1647 と同等 (git 履歴参照)
    file(MAKE_DIRECTORY "${dest}/include/wels")
    file(GLOB _wels_headers "${_src}/codec/api/wels/codec*.h")
    foreach(_h ${_wels_headers})
      configure_file("${_h}" "${dest}/include/wels/" COPYONLY)
    endforeach()
  else()
    # 既存 make install-headers 経路 (0001 で実装される)
    find_program(_SORA_MAKE_EXECUTABLE make NO_CACHE)
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

ただし Windows は OpenH264 を使わない（ `CMakeLists.txt:185-191` の `if (NOT TARGET_OS STREQUAL "windows")` ガード）。 整理:

- 案 A: Windows でも `_sora_fetch_openh264` を呼ぶが、 ヘッダだけコピー（ `dynamic_h264_*.cpp` は Windows では include されないため実害なし）
- 案 B: Windows では `_sora_fetch_openh264` の呼び出しを `if(NOT WIN32)` で囲んで完全 skip

案 B を採る。 Windows では OpenH264 は実体的に不要なため、 fetch 自体を skip して時間を節約する。

### _sora_fetch_llvm の Windows skip と出力契約のガード

メインスクリプトで（パス・変数名は 0001 のレイアウト `_deps/llvm/<host_key>/` に従う）:

```cmake
if(NOT WIN32)
  _sora_fetch_llvm("${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/webrtc" "${DEPS_ROOT}/llvm/${_host_key}" "${DEPS_ROOT}/llvm/${_host_key}/.stamps/llvm")
  set(_SORA_CLANG_DIR "${DEPS_ROOT}/llvm/${_host_key}/clang" CACHE PATH "" FORCE)
endif()
```

Windows では 0001 の出力契約のうち `OPENH264_DIR` / `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` / `_SORA_CLANG_DIR` の 4 変数を設定しない。 0001 のメインスクリプト手順 6 の該当 4 変数の CACHE FORCE 設定と、 `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` のガード付き FORCE 設定を `if(NOT WIN32)` で skip し、 Windows は CMake デフォルト探索（ MSVC ）に任せる。

### TARGET_OS の Windows 上書き

`pyproject.toml` に override を追加する:

```toml
[[tool.scikit-build.overrides]]
if.platform-system = "win32"
cmake.define.TARGET_OS = "windows"
cmake.define.SORA_GEN_PYI = "OFF"
```

scikit-build-core の `if.platform-system = "win32"` は `sys.platform` ベースで Windows にマッチする。

`SORA_GEN_PYI = OFF` 設定は旧 `run.py:374-379` （ git 履歴参照）の方針踏襲。

### LIBCXX / LIBCXXABI ガード

Windows では libcxx / libcxxabi を使わないため、 `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` が空でも問題ないようにする:

- `CMakeLists.txt:124-135` の ubuntu 分岐と `:111-123` の macOS 分岐は `TARGET_OS=windows` では入らないため自動的に skip される
- `fetch_deps.cmake` のメインスクリプト末尾の cache 確定は上記「 _sora_fetch_llvm の Windows skip 」の `if(NOT WIN32)` ガードでまとめて skip する

### Boost / OpenH264 アーカイブの Windows 命名確認

実機確認（バージョンは `DEPS` の現在値で組み立てる。 現時点では `WEBRTC_BUILD_VERSION=m150.7871.3.1` / `SORA_CPP_SDK_VERSION=2026.2.0-canary.23` / `BOOST_VERSION=1.91.0` ）:

```
curl -sLO https://github.com/shiguredo-webrtc-build/webrtc-build/releases/download/m150.7871.3.1/webrtc.windows_x86_64.zip && unzip -l webrtc.windows_x86_64.zip | head -10
curl -sLO https://github.com/shiguredo/sora-cpp-sdk/releases/download/2026.2.0-canary.23/sora-cpp-sdk-2026.2.0-canary.23_windows_x86_64.zip && unzip -l sora-cpp-sdk-2026.2.0-canary.23_windows_x86_64.zip | head -10
curl -sLO https://github.com/shiguredo/sora-cpp-sdk/releases/download/2026.2.0-canary.23/boost-1.91.0_sora-cpp-sdk-2026.2.0-canary.23_windows_x86_64.zip && unzip -l boost-1.91.0_sora-cpp-sdk-2026.2.0-canary.23_windows_x86_64.zip | head -10
```

展開後レイアウト（単一トップディレクトリか）を確認する（ 0001 の動的判定がそのまま効くことの確認）。

### CI 影響

- `build.yml` に `build_windows` job を新設する（ 0001 で旧 job は削除済みのため、 `if: false` 解除ではなく新規追加）:
  - matrix: platform は `windows-2025_x86_64` (runs_on: windows-2025) の 1 entry、 python_version は 3.12 / 3.13 / 3.14 （旧 job の構成を git 履歴から引き継ぐ）
  - steps: checkout → setup-uv → `uv sync --no-install-project` → `uv build --wheel` → `uv pip install dist/*.whl` → `uv run --no-sync pytest tests/test_version.py` → upload-artifact （ 0001 の `build_ubuntu` job 構成に準拠。 apt install step は不要）
  - `needs` は付けない（ `build_pyi` artifact 経路は 0001 で廃止済み）
- `slack_notify` job の `needs:` に `build_windows` を追加する（ 0005 マージ時点の needs リストに追加する。 0002 マージ済みなら `[build_ubuntu, build_macos, build_windows]` ）

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
- CI で新設 `build_windows` job が green になる

## 解決方法

実装せず closed にする。

scikit-build-core 化を複数回試みたが難しく、方針としてあきらめることにした。
build backend の移行は行わず、現行の setuptools / `run.py` 経路を維持する。
sysroot 化は 0074 で現行経路向けに切り直す。

## ロールバック

0005 マージ後に Windows build で問題が発覚した場合:

1. `git revert -m 1 <merge-commit>` で revert PR を作成
2. revert 後、 新設した `build_windows` job が build.yml から消え、 0005 適用前の job 構成に戻ることを確認
3. `pyproject.toml` の Windows override が消えるか確認
4. forward fix を選ぶ判断: OpenH264 / アーカイブ拡張子の単一不具合なら追加コミットで対応する
