# scikit-build-core 導入と ubuntu-24.04 x86_64 ネイティブビルド完結

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-scikit-build-core-native-deps

## 目的

build backend を setuptools から scikit-build-core に切替え、 ubuntu-24.04 x86_64 host で `uv build --wheel` 一発で wheel を生成し、 install 後の最小 pytest が通る状態にする。 WebRTC / Sora C++ SDK / Boost / OpenH264 / LLVM (clang バイナリ + libcxx + libcxxabi ヘッダ) の取得を `run.py` / `buildbase.py` から CMake configure 時取得に移し、 `run.py build` を経由せず scikit-build-core 経路だけで完結させる。

## 設計の前提（プロジェクト全体の新方針）

- ビルド環境は **ubuntu-24.04 x86_64 host のみ** に集約する
- Linux arm64 (`ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` / `ubuntu-22.04_armv8_jetson` / `raspberry-pi-os_armv8`) は ubuntu-24.04 x86_64 host からの **sysroot クロスコンパイル** に統一し、 arm64 native runner (`ubuntu-22.04-arm` / `ubuntu-24.04-arm`) は廃止する
- macOS (arm64) / Windows (x86_64) は **それぞれの OS で native build** を維持する（cross-compile しない）
- clang は **libwebrtc 同梱 clang バイナリを継続使用** する（`buildbase.py:install_llvm` の `clang/scripts/update.py` 取得を CMake 側に完全移植する）。 system `clang-19` への切替えは行わない

## スコープ

含む:

- `pyproject.toml` の build backend を scikit-build-core に切替える
- `setup.py` を削除する
- `CMakeLists.txt` の更新と `cmake/scripts/fetch_deps.cmake` 新設
- ubuntu-24.04 x86_64 host で WebRTC / Sora C++ SDK / Boost / OpenH264 / LLVM (clang + libcxx + libcxxabi) を CMake configure 時取得（ `buildbase.py:install_llvm` の `clang/scripts/update.py` 経由 clang バイナリ取得を含む）
- `src/sora.cpp:216, 223` の `BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION)` を `SORA_PYTHON_SDK_VERSION` の直接連結に書き換える（マクロ定義をクォート付き文字列リテラルに変更するため）
- ubuntu-24.04 x86_64 native での `uv build --wheel` 成功と `pytest tests/test_version.py` 完走
- CI で 0001 の経路（ ubuntu-24.04 x86_64 only ）が動くよう、他 platform job を `if: false` で一時 disable し、 `build_ubuntu` matrix から ubuntu-24.04_x86_64 以外を `exclude` する

含まない（別 issue で扱う）:

- macOS arm64 native（ 0002 ）
- Linux arm64 cross-compile (ubuntu armv8) from ubuntu-24.04 x86_64 host（ 0003 ）
- Linux arm64 cross-compile (jetson / raspberry-pi-os) from ubuntu-24.04 x86_64 host（ 0004 ）
- Windows x86_64 native（ 0005 ）
- レガシーファイル（ `buildbase.py` / `run.py` / `pypath.py` / `MANIFEST.in` / `DEPS` ）削除、 `build_pyi` job 完全削除、 `build_ubuntu_arm` job 完全削除、 `e2e_test` 復活、 `auditwheel repair --strip --only-plat` による `manylinux_2_35_x86_64` タグ付与、依存アーカイブの sha256 検証（ 0006 ）
- 開発者向け Makefile（ 0007 ）
- pytest E2E マーカー再設計（別 issue 。 0001 では `pytest tests/test_version.py` のみ）

## 現状

- `pyproject.toml` の build backend は `setuptools.build_meta`
- `run.py build` が `buildbase.py` 経由で deps を `_install/<target>/` に取得し、 `cmake` を手動実行して `.so` を `src/sora_sdk/` にコピーする
- `setup.py:32-36, 46-49` の `bdist_wheel.get_tag()` が ubuntu-24.04 x86_64 で `manylinux_2_35_x86_64` を強制する
- `CMakeLists.txt:54-59` で CACHE 宣言されているのは `TARGET_OS` / `WEBRTC_INCLUDE_DIR` / `WEBRTC_LIBRARY_DIR` / `WEBRTC_LIBRARY_NAME` / `Boost_ROOT` / `SORA_DIR` の 6 個のみ。 `OPENH264_DIR` / `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` / `SORA_PYTHON_SDK_VERSION` / `SORA_GEN_PYI` は CACHE 宣言を持たず、 `run.py` 経由の `-D` 注入で自動 CACHE 化される運用
- ubuntu ターゲット（ `TARGET_OS=ubuntu` ）では `CMakeLists.txt:132-143` の `elseif(TARGET_OS STREQUAL "ubuntu")` ブランチで `-nostdinc++ -isystem${LIBCXX_INCLUDE_DIR}` が `sora_sdk_ext` と `nanobind-static` 両方に付き、 `CMakeLists.txt:193-199` の `if (NOT TARGET_OS STREQUAL "windows")` で `${OPENH264_DIR}/include` のインクルードと `dynamic_h264_*.cpp` のコンパイルが要求される
- ubuntu-24.04 x86_64 native は `run.py:293-297` の `else` 節で **libwebrtc 同梱 clang バイナリ** （ `webrtc_info.clang_dir = ${install_dir}/llvm/clang` 、 `buildbase.py:641, 1187-1211` ）を `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` に渡す。 libcxx / libcxxabi ヘッダは `run.py:298-301` で `${install_dir}/llvm/libcxx/include` と `${webrtc}/include/third_party/libc++abi/src/include` を `-D` で渡している
- `src/sora.cpp:216` と `:223` のみが `BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION)` を使う（ `grep -rn 'BOOST_PP_STRINGIZE\|SORA_PYTHON_SDK_VERSION' src/` で確認済み）
- `.github/workflows/build.yml` の `build_ubuntu` / `build_ubuntu_arm` / `build_macos` / `build_windows` 各 job は `uv run python run.py build <target>` の直後に `uv build` を実行する 2 段構成。 `build_pyi` は ubuntu-24.04 x86_64 で `run.py build` を呼んで `src/sora_sdk/sora_sdk_ext.pyi` を生成し artifact 化、各 platform job で download / cp する経路を持つ

### 既存レイアウトと 0001 後のレイアウト対応

| 既存 (`run.py` 経路) | 0001 後 (`uv build` 経路) |
| --- | --- |
| `_install/ubuntu-24.04_x86_64/webrtc/` | `_deps/ubuntu-24.04_x86_64/webrtc/` |
| `_install/ubuntu-24.04_x86_64/sora/` | `_deps/ubuntu-24.04_x86_64/sora/` |
| `_install/ubuntu-24.04_x86_64/boost/` | `_deps/ubuntu-24.04_x86_64/boost/` |
| `_install/ubuntu-24.04_x86_64/openh264/` | `_deps/ubuntu-24.04_x86_64/openh264/` |
| `_install/ubuntu-24.04_x86_64/llvm/clang/` | `_deps/llvm/x86_64-Linux-24.04/clang/` |
| `_install/ubuntu-24.04_x86_64/llvm/libcxx/` | `_deps/llvm/x86_64-Linux-24.04/libcxx/` |

WebRTC / Sora / Boost / OpenH264 は target ごとに分離する（クロス対応で arm64 アーカイブと x86_64 アーカイブが混在しないように）。 LLVM は **host 単位** で分離する（クロス時もホスト側 LLVM を使うため、 0003 / 0004 で同じ LLVM ディレクトリを共有する）。

## 設計方針

### build backend と pyproject.toml

`pyproject.toml` を以下の通り変更する。

- `[build-system]` を `requires = ["scikit-build-core>=0.11.3", "nanobind==2.12.0"]` / `build-backend = "scikit_build_core.build"` に切替える。 CMake / Ninja は scikit-build-core 経由で PyPI 取得（ webcodecs-py と同方針）
- `[dependency-groups] dev` から `nanobind==2.12.0` を削除する（ `[build-system]` 側に集約してバージョンずれを防ぐ）
- `[tool.scikit-build]` に `minimum-version = "0.11.3"` / `build-dir = "_build/{wheel_tag}"` を設定する。 `{wheel_tag}` で Python ABI ごとに build dir を分離し、 `CMakeCache.txt` 内の `Python_INCLUDE_DIR` キャッシュ干渉を防ぐ。 `_deps/` は Python 非依存のため Python ABI を含めず `SORA_PYTHON_SDK_PLATFORM` 単位で共有する
- `[tool.scikit-build.cmake] version = ">=4.2"` （ `pip index versions cmake` で PyPI 4.2.x が提供されることを確認済み。 既存 `DEPS` の `CMAKE_VERSION=4.3.2` よりやや緩めて将来の PyPI 提供ずれに耐える）
- `[tool.scikit-build.ninja] version = ">=1.13"`
- `[tool.scikit-build.wheel]` に `packages = ["src/sora_sdk"]` と `exclude = ["sora_sdk_ext.pyi", "py.typed", "sora_sdk_ext.*.so", "sora_sdk_ext.*.pyd"]` 。 scikit-build-core は `packages` 内相対パスを `pathspec.GitIgnoreSpec` で照合するため、 `src/sora_sdk/` プレフィックス無しのファイル名のみで指定する。 source tree 側に残るビルド成果物が `install(FILES)` 出力と二重コピーされる問題を防ぐ
- `[tool.scikit-build.metadata.version]` に `provider = "scikit_build_core.metadata.regex"` / `input = "VERSION"` / `regex = "(?P<value>\\S+)"` を設定する。 scikit-build-core は `re.search` ベースで先頭一致するためアンカー不要。 `VERSION` は ASCII 1 行 + 改行で `\\S+` が安全に動く
- `[tool.scikit-build.cmake.define]` に `TARGET_OS = "ubuntu"` を設定する。 `CMakeLists.txt:132-143` の ubuntu ブランチと `:193-199` の OpenH264 / `dynamic_h264_*.cpp` 取り込みを有効化するため。 0002 / 0005 で macOS / windows を追加する際は `[[tool.scikit-build.overrides]]` で上書きする
- `[[tool.scikit-build.overrides]]` で `if.env.BUILD_PROFILE = "^debug$"` のとき `cmake.build-type = "Debug"` 。 scikit-build-core の `if.env.<NAME>` は `re.search` 仕様のため `^...$` でアンカー必須
- `[tool.scikit-build.wheel] install-dir` は明示せず空文字デフォルト（ platlib = site-packages 起点）にする。 CMake 側 `install(... DESTINATION sora_sdk)` で site-packages/sora_sdk/ に配置し、 `wheel.packages = ["src/sora_sdk"]` がコピーする site-packages/sora_sdk/ と同一ディレクトリにマージする。 `wheel.install-dir = "sora_sdk"` + `install(DESTINATION .)` という別解もあるが、 wheel.packages と CMake install の出力先表現を揃えて grep しやすくするため前者を採る
- `[tool.uv]` には触らない。 `uv sync` は scikit-build-core 経由でプロジェクト本体を install する（editable install への切替は 0007 ）。 `[tool.uv.pip] exclude-newer = "7 days"` は `scikit-build-core>=0.11.3` （ 2026-04 リリース）と `nanobind==2.12.0` （ 2025-12 リリース）ともに 7 日以上経過しているため緩和不要

### deps.json

リポジトリ直下に `deps.json` を新設する。

```json
{
  "webrtc": {
    "version": "m149.7827.0.0",
    "url_template": "https://github.com/shiguredo-webrtc-build/webrtc-build/releases/download/{version}/webrtc.{platform}.tar.gz",
    "strip_components": 1
  },
  "sora_cpp_sdk": {
    "version": "2026.2.0-canary.11",
    "url_template": "https://github.com/shiguredo/sora-cpp-sdk/releases/download/{version}/sora-cpp-sdk-{version}_{platform}.tar.gz",
    "strip_components": 1
  },
  "boost": {
    "version": "1.91.0",
    "url_template": "https://github.com/shiguredo/sora-cpp-sdk/releases/download/{sora_version}/boost-{version}_sora-cpp-sdk-{sora_version}_{platform}.tar.gz",
    "strip_components": 1
  },
  "openh264": {
    "version": "v2.6.0",
    "git": "https://github.com/cisco/openh264.git"
  }
}
```

- `{sora_version}` プレースホルダは boost テンプレートでのみ使う（ Boost リリースは Sora C++ SDK の release ページに同梱されるため）
- `strip_components` は 0001 実装時に実機で次のコマンドで確認し最終値を確定する（暫定 `1` ）:
  - `curl -sL <url> | tar tzf - | head -5` で WebRTC / Sora / Boost のトップディレクトリを確認
  - `curl -sL <webrtc-url> | tar tzf - | grep "include/third_party/libc++abi/src/include/__cxxabi_config.h"` で `LIBCXXABI_INCLUDE_DIR` 末尾の存在を確認
- `openh264.version` は git tag 名（ `v` プレフィックス有）を保持する。 `.github/workflows/build.yml:29` の `OPENH264_VERSION: 2.6.0` （ `v` 無し）は E2E ランタイム `.so` 用の別経路の値で 0001 では触らない（統一は 0006 ）
- 依存アーカイブの sha256 検証は 0006 で導入する

### platform 判定

`CMakeLists.txt` で `SORA_PYTHON_SDK_PLATFORM` cache 変数を導入する（ Sora C++ SDK 側 `SORA_*` 変数との衝突を避けるためプロジェクト固有 prefix ）。

- 未指定時は次の手順で算出:
  1. `file(READ /etc/os-release OS_RELEASE)`
  2. `string(REGEX MATCH "(^|\n)ID=([^\n]+)" _ "${OS_RELEASE}")` で `ID` を抽出。 `ubuntu` 以外なら `message(FATAL_ERROR "scikit-build-core migration phase 1 supports ubuntu only; got '${ID}'")`
  3. `string(REGEX MATCH "(^|\n)VERSION_ID=\"?([^\"\n]+)\"?" _ "${OS_RELEASE}")` で `VERSION_ID` を抽出（クォート有無両対応）。 `_SORA_UBUNTU_VERSION_ID` に保持
  4. `${CMAKE_HOST_SYSTEM_PROCESSOR}` から arch を取得
  5. 組み立て: `ubuntu-${_SORA_UBUNTU_VERSION_ID}_${arch}`
  6. `ubuntu-24.04_x86_64` 以外なら `message(FATAL_ERROR "scikit-build-core migration phase 1 supports ubuntu-24.04_x86_64 only; got '${SORA_PYTHON_SDK_PLATFORM}'. Other platforms will be added in subsequent migration phases (0002 macOS / 0003 ubuntu arm64 cross / 0004 jetson rpi cross / 0005 Windows).")`
- `lsb_release` には依存しない（ ubuntu container でデフォルト未インストールのため）

### fetch_deps.cmake

`cmake/scripts/fetch_deps.cmake` を新設し、 `CMakeLists.txt` から `include()` で呼ぶ。

入力契約（呼び出し前に設定済み）:

- `SORA_PYTHON_SDK_PLATFORM` （例 `ubuntu-24.04_x86_64` ）
- `_SORA_UBUNTU_VERSION_ID` （例 `24.04` 。 `SORA_PYTHON_SDK_PLATFORM` 算出時に併設）
- `DEPS_ROOT` （例 `${PROJECT_ROOT}/_deps` ）
- `Python_EXECUTABLE` （ scikit-build-core が自動で設定）

出力契約: 取得成功時に以下のキャッシュ変数を `set(... CACHE PATH "" FORCE)` で確定する。 既存 CACHE 宣言を持つ `SORA_DIR` / `Boost_ROOT` / `WEBRTC_INCLUDE_DIR` / `WEBRTC_LIBRARY_DIR` は上書き、 `OPENH264_DIR` / `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` / `_SORA_CLANG_DIR` は新規 CACHE 作成。

| 変数 | 値（ `SORA_PYTHON_SDK_PLATFORM = ubuntu-24.04_x86_64` 例） |
| --- | --- |
| `SORA_DIR` | `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/sora` |
| `Boost_ROOT` | `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/boost` |
| `WEBRTC_INCLUDE_DIR` | `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/webrtc/include` |
| `WEBRTC_LIBRARY_DIR` | `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/webrtc/lib` |
| `OPENH264_DIR` | `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/openh264` |
| `LIBCXX_INCLUDE_DIR` | `${DEPS_ROOT}/llvm/${LLVM_HOST_KEY}/libcxx/include` |
| `LIBCXXABI_INCLUDE_DIR` | `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/webrtc/include/third_party/libc++abi/src/include` |
| `_SORA_CLANG_DIR` | `${DEPS_ROOT}/llvm/${LLVM_HOST_KEY}/clang` （ host 側 clang バイナリのインストール先、 `CMakeLists.txt` から `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` を指定するときに使う） |

`LLVM_HOST_KEY = ${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}-${_SORA_UBUNTU_VERSION_ID}` （例 `x86_64-Linux-24.04` ）。 0003 / 0004 のクロスコンパイル時もホスト側 LLVM を共有するため host 単位でキャッシュし、 glibc 互換性のため ubuntu バージョンも host キーに含める。

`LIBCXXABI_INCLUDE_DIR` の末尾 `/include` について: `buildbase.py:643-645` の `get_webrtc_info` は `libcxxabi_dir` を `<webrtc>/include/third_party/libc++abi/src` までに留めており、 `run.py:300` で `os.path.join(webrtc_info.libcxxabi_dir, 'include')` として末尾 `/include` を付与して `-DLIBCXXABI_INCLUDE_DIR` に渡している。 `fetch_deps.cmake` 側は二段組を持たないので最終値を直接 `…/include` まで含めて CACHE する。 `…/libc++abi/src/include/__cxxabi_config.h` の所在を直接示す。

### fetch_deps.cmake のヘルパ関数

```cmake
# _sora_git_shallow(<url> <ref> <dest>)
# git shallow clone のみ。stamp 書き込みは呼び出し側。
#
# buildbase.py:413-420 git_clone_shallow と同等の実装にする
# (git init + git fetch --depth=1 origin <hash> + git reset --hard FETCH_HEAD)。
# `git clone --depth 1 --branch <commit-sha>` は raw commit SHA を --branch に渡せず
# GitHub の uploadpack.allowReachableSHA1InWant 設定に依存して reject されるケースがあるため使わない。
function(_sora_git_shallow url ref dest)
  file(MAKE_DIRECTORY "${dest}")
  set(_attempt 0)
  set(_max_attempts 3)
  while(_attempt LESS _max_attempts)
    math(EXPR _attempt "${_attempt} + 1")
    execute_process(
      COMMAND git init
      WORKING_DIRECTORY "${dest}"
      RESULT_VARIABLE _r1)
    if(NOT _r1 EQUAL 0)
      continue()
    endif()
    execute_process(
      COMMAND git remote add origin "${url}"
      WORKING_DIRECTORY "${dest}"
      RESULT_VARIABLE _r2)
    execute_process(
      COMMAND git fetch --depth 1 origin "${ref}"
      WORKING_DIRECTORY "${dest}"
      RESULT_VARIABLE _r3)
    if(_r3 EQUAL 0)
      execute_process(
        COMMAND git reset --hard FETCH_HEAD
        WORKING_DIRECTORY "${dest}"
        RESULT_VARIABLE _r4)
      if(_r4 EQUAL 0)
        return()
      endif()
    endif()
    file(REMOVE_RECURSE "${dest}")
    file(MAKE_DIRECTORY "${dest}")
    execute_process(COMMAND ${CMAKE_COMMAND} -E sleep 2)
  endwhile()
  message(FATAL_ERROR
    "Failed to git fetch ${url} at ${ref} after ${_max_attempts} retries. "
    "Check network connectivity or HTTPS_PROXY environment variable.")
endfunction()

# _sora_fetch_archive(<name> <url> <stamp_path> <dest_dir> <strip_components>)
# ダウンロード + tar xzf + stamp 書き込み。
# name はログメッセージ用と一時アーカイブファイル名用。
# stamp 書き込みは展開成功後に行う(buildbase.py:251-270 versioned デコレータと同順序)。
function(_sora_fetch_archive name url stamp_path dest_dir strip_components)
  # stamp ヒット判定
  if(EXISTS "${stamp_path}")
    file(READ "${stamp_path}" _existing_stamp)
    string(STRIP "${_existing_stamp}" _existing_stamp)
    if("${_existing_stamp}" STREQUAL "${url}")
      message(STATUS "Sora deps: ${name} cache hit (${url})")
      return()
    endif()
  endif()

  message(STATUS "Sora deps: fetching ${name} from ${url}")
  file(REMOVE_RECURSE "${dest_dir}")
  file(MAKE_DIRECTORY "${dest_dir}")
  get_filename_component(_archive_dir "${stamp_path}" DIRECTORY)
  file(MAKE_DIRECTORY "${_archive_dir}/.archives")
  set(_archive "${_archive_dir}/.archives/${name}.tar.gz")

  set(_attempt 0)
  set(_max_attempts 3)
  set(_success FALSE)
  while(_attempt LESS _max_attempts)
    math(EXPR _attempt "${_attempt} + 1")
    file(REMOVE "${_archive}")
    file(DOWNLOAD "${url}" "${_archive}"
      TLS_VERIFY ON
      SHOW_PROGRESS
      INACTIVITY_TIMEOUT 120
      STATUS _dl_status)
    list(GET _dl_status 0 _dl_code)
    if(_dl_code EQUAL 0)
      set(_success TRUE)
      break()
    endif()
    list(GET _dl_status 1 _dl_msg)
    message(WARNING "Sora deps: download ${name} failed (${_dl_code}: ${_dl_msg}), retrying")
    execute_process(COMMAND ${CMAKE_COMMAND} -E sleep 2)
  endwhile()
  if(NOT _success)
    message(FATAL_ERROR
      "Failed to download ${name} from ${url} after ${_max_attempts} retries. "
      "Check network connectivity or HTTPS_PROXY environment variable.")
  endif()

  # file(ARCHIVE_EXTRACT) には strip 機能が無いため tar コマンドを使う
  execute_process(
    COMMAND ${CMAKE_COMMAND} -E tar xzf "${_archive}" --strip-components=${strip_components}
    WORKING_DIRECTORY "${dest_dir}"
    RESULT_VARIABLE _extract_result)
  if(NOT _extract_result EQUAL 0)
    file(REMOVE_RECURSE "${dest_dir}")
    message(FATAL_ERROR "Failed to extract ${name} archive: ${_archive}")
  endif()

  # stamp は展開成功後に書き込む
  get_filename_component(_stamp_parent "${stamp_path}" DIRECTORY)
  file(MAKE_DIRECTORY "${_stamp_parent}")
  file(WRITE "${stamp_path}" "${url}")
endfunction()

# _sora_fetch_openh264(<version> <git_url> <dest> <stamp_path>)
function(_sora_fetch_openh264 version git_url dest stamp_path)
  if(EXISTS "${stamp_path}")
    file(READ "${stamp_path}" _existing_stamp)
    string(STRIP "${_existing_stamp}" _existing_stamp)
    if("${_existing_stamp}" STREQUAL "${version}")
      message(STATUS "Sora deps: openh264 cache hit (${version})")
      return()
    endif()
  endif()

  # 実 fetch 時のみ make の存在を確認する。キャッシュヒット時は make 不在環境でも止めない
  find_program(_SORA_MAKE_EXECUTABLE make)
  if(NOT _SORA_MAKE_EXECUTABLE)
    message(FATAL_ERROR
      "OpenH264 header installation requires 'make'. "
      "On Debian/Ubuntu: run 'apt-get install build-essential'.")
  endif()

  message(STATUS "Sora deps: fetching openh264 ${version} from ${git_url}")
  file(REMOVE_RECURSE "${dest}")
  get_filename_component(_src "${dest}" DIRECTORY)
  set(_src "${_src}/.openh264-src")
  file(REMOVE_RECURSE "${_src}")
  _sora_git_shallow("${git_url}" "${version}" "${_src}")

  file(MAKE_DIRECTORY "${dest}")
  execute_process(
    COMMAND "${_SORA_MAKE_EXECUTABLE}" -C "${_src}" install-headers "PREFIX=${dest}"
    RESULT_VARIABLE _make_result)
  if(NOT _make_result EQUAL 0)
    message(FATAL_ERROR "Failed to install openh264 headers (make install-headers PREFIX=${dest})")
  endif()

  file(REMOVE_RECURSE "${_src}")
  get_filename_component(_stamp_parent "${stamp_path}" DIRECTORY)
  file(MAKE_DIRECTORY "${_stamp_parent}")
  file(WRITE "${stamp_path}" "${version}")
endfunction()

# _sora_fetch_llvm(<webrtc_install_dir> <dest_root> <stamp_path>)
# buildbase.py:1187-1233 install_llvm 完全移植版。
# - WebRTC アーカイブ内 VERSIONS ファイルから 6 つの KEY を読む
# - tools / libcxx / buildtools を shallow clone
# - tools/clang/scripts/update.py で host 用 clang バイナリを <dest_root>/clang/ に取得
# - buildtools/third_party/libc++/__config_site と __assertion_handler を libcxx/include/ にコピー
function(_sora_fetch_llvm webrtc_install_dir dest_root stamp_path)
  set(_versions_file "${webrtc_install_dir}/VERSIONS")
  if(NOT EXISTS "${_versions_file}")
    message(FATAL_ERROR "WebRTC VERSIONS file not found: ${_versions_file}")
  endif()
  file(READ "${_versions_file}" _versions_content)

  foreach(_key
      WEBRTC_SRC_TOOLS_URL WEBRTC_SRC_TOOLS_COMMIT
      WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT
      WEBRTC_SRC_BUILDTOOLS_URL WEBRTC_SRC_BUILDTOOLS_COMMIT)
    # KEY="value" / KEY=value 両対応。行頭アンカーで他 KEY の partial match を避ける。
    # buildbase.py:238-239 の `b.strip('"')` と等価
    if(_versions_content MATCHES "(^|\n)${_key}=\"?([^\"\n]+)\"?")
      set(_${_key} "${CMAKE_MATCH_2}")
    else()
      message(FATAL_ERROR "Key ${_key} not found in ${_versions_file}")
    endif()
  endforeach()

  set(_stamp_value
    "${_WEBRTC_SRC_TOOLS_URL}.${_WEBRTC_SRC_TOOLS_COMMIT}.${_WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL}.${_WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT}.${_WEBRTC_SRC_BUILDTOOLS_URL}.${_WEBRTC_SRC_BUILDTOOLS_COMMIT}")

  if(EXISTS "${stamp_path}")
    file(READ "${stamp_path}" _existing_stamp)
    string(STRIP "${_existing_stamp}" _existing_stamp)
    if("${_existing_stamp}" STREQUAL "${_stamp_value}")
      message(STATUS "Sora deps: llvm cache hit")
      return()
    endif()
  endif()

  message(STATUS "Sora deps: fetching llvm (clang + libcxx + libcxxabi headers)")
  file(REMOVE_RECURSE "${dest_root}/clang" "${dest_root}/libcxx" "${dest_root}/buildtools" "${dest_root}/tools")

  # tools: clang/scripts/update.py を保持する
  _sora_git_shallow("${_WEBRTC_SRC_TOOLS_URL}" "${_WEBRTC_SRC_TOOLS_COMMIT}" "${dest_root}/tools")

  # clang バイナリの取得 (buildbase.py:1204-1211 と同等)
  execute_process(
    COMMAND "${Python_EXECUTABLE}"
      "${dest_root}/tools/clang/scripts/update.py"
      "--output-dir" "${dest_root}/clang"
    RESULT_VARIABLE _update_result)
  if(NOT _update_result EQUAL 0)
    message(FATAL_ERROR "clang/scripts/update.py failed (output-dir=${dest_root}/clang)")
  endif()

  # libcxx: ヘッダソース
  _sora_git_shallow("${_WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL}" "${_WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT}" "${dest_root}/libcxx")

  # buildtools: __config_site / __assertion_handler を取り出すためだけに clone
  _sora_git_shallow("${_WEBRTC_SRC_BUILDTOOLS_URL}" "${_WEBRTC_SRC_BUILDTOOLS_COMMIT}" "${dest_root}/buildtools")
  # buildbase.py:1218-1219 の git reset --hard と同じ保険。
  # FETCH_HEAD が稀に commit と一致しないケースを救済する
  execute_process(
    COMMAND git reset --hard "${_WEBRTC_SRC_BUILDTOOLS_COMMIT}"
    WORKING_DIRECTORY "${dest_root}/buildtools"
    RESULT_VARIABLE _reset_result)
  if(NOT _reset_result EQUAL 0)
    message(WARNING "buildtools git reset --hard ${_WEBRTC_SRC_BUILDTOOLS_COMMIT} failed (continuing)")
  endif()

  # buildbase.py:1220-1232 と同じコピー
  configure_file(
    "${dest_root}/buildtools/third_party/libc++/__config_site"
    "${dest_root}/libcxx/include/__config_site"
    COPYONLY)
  configure_file(
    "${dest_root}/buildtools/third_party/libc++/__assertion_handler"
    "${dest_root}/libcxx/include/__assertion_handler"
    COPYONLY)

  # tools / buildtools は __config_site / __assertion_handler / clang バイナリ取得が済んだので削除して容量を節約
  file(REMOVE_RECURSE "${dest_root}/tools" "${dest_root}/buildtools")

  get_filename_component(_stamp_parent "${stamp_path}" DIRECTORY)
  file(MAKE_DIRECTORY "${_stamp_parent}")
  file(WRITE "${stamp_path}" "${_stamp_value}")
endfunction()
```

メインスクリプト（ `fetch_deps.cmake` 末尾）:

```cmake
# deps.json を読み解く
file(READ "${CMAKE_SOURCE_DIR}/deps.json" _DEPS_JSON)
string(JSON _WEBRTC_VERSION GET "${_DEPS_JSON}" webrtc version)
string(JSON _WEBRTC_URL_TEMPLATE GET "${_DEPS_JSON}" webrtc url_template)
string(JSON _WEBRTC_STRIP GET "${_DEPS_JSON}" webrtc strip_components)
string(JSON _SORA_VERSION GET "${_DEPS_JSON}" sora_cpp_sdk version)
string(JSON _SORA_URL_TEMPLATE GET "${_DEPS_JSON}" sora_cpp_sdk url_template)
string(JSON _SORA_STRIP GET "${_DEPS_JSON}" sora_cpp_sdk strip_components)
string(JSON _BOOST_VERSION GET "${_DEPS_JSON}" boost version)
string(JSON _BOOST_URL_TEMPLATE GET "${_DEPS_JSON}" boost url_template)
string(JSON _BOOST_STRIP GET "${_DEPS_JSON}" boost strip_components)
string(JSON _OPENH264_VERSION GET "${_DEPS_JSON}" openh264 version)
string(JSON _OPENH264_GIT GET "${_DEPS_JSON}" openh264 git)

# URL テンプレート展開: 長い placeholder から先に置換する。
# {sora_version} は文字列として {version} を内包するため、{version} を先に置換すると
# {sora_version} 内の {version} 部分が誤置換される(例: boost テンプレートの
# `boost-{version}_sora-cpp-sdk-{sora_version}_…` で {version} を先に展開すると
# `…sora-cpp-sdk-{1.91.0}_…` に化ける)。
macro(_sora_expand_url out template version sora_version platform)
  set(${out} "${template}")
  string(REPLACE "{sora_version}" "${sora_version}" ${out} "${${out}}")
  string(REPLACE "{version}" "${version}" ${out} "${${out}}")
  string(REPLACE "{platform}" "${platform}" ${out} "${${out}}")
endmacro()

set(_PLATFORM_ROOT "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}")
set(_STAMPS_ROOT "${_PLATFORM_ROOT}/.stamps")
set(_LLVM_HOST_KEY "${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}-${_SORA_UBUNTU_VERSION_ID}")
set(_LLVM_ROOT "${DEPS_ROOT}/llvm/${_LLVM_HOST_KEY}")
set(_LLVM_STAMPS_ROOT "${_LLVM_ROOT}/.stamps")

_sora_expand_url(_WEBRTC_URL "${_WEBRTC_URL_TEMPLATE}" "${_WEBRTC_VERSION}" "" "${SORA_PYTHON_SDK_PLATFORM}")
_sora_fetch_archive(webrtc "${_WEBRTC_URL}" "${_STAMPS_ROOT}/webrtc" "${_PLATFORM_ROOT}/webrtc" ${_WEBRTC_STRIP})

_sora_expand_url(_SORA_URL "${_SORA_URL_TEMPLATE}" "${_SORA_VERSION}" "" "${SORA_PYTHON_SDK_PLATFORM}")
_sora_fetch_archive(sora "${_SORA_URL}" "${_STAMPS_ROOT}/sora" "${_PLATFORM_ROOT}/sora" ${_SORA_STRIP})

_sora_expand_url(_BOOST_URL "${_BOOST_URL_TEMPLATE}" "${_BOOST_VERSION}" "${_SORA_VERSION}" "${SORA_PYTHON_SDK_PLATFORM}")
_sora_fetch_archive(boost "${_BOOST_URL}" "${_STAMPS_ROOT}/boost" "${_PLATFORM_ROOT}/boost" ${_BOOST_STRIP})

_sora_fetch_openh264("${_OPENH264_VERSION}" "${_OPENH264_GIT}" "${_PLATFORM_ROOT}/openh264" "${_STAMPS_ROOT}/openh264")

_sora_fetch_llvm("${_PLATFORM_ROOT}/webrtc" "${_LLVM_ROOT}" "${_LLVM_STAMPS_ROOT}/llvm")

# 7 + 1 変数を CACHE に確定
set(SORA_DIR              "${_PLATFORM_ROOT}/sora"     CACHE PATH "" FORCE)
set(Boost_ROOT            "${_PLATFORM_ROOT}/boost"    CACHE PATH "" FORCE)
set(WEBRTC_INCLUDE_DIR    "${_PLATFORM_ROOT}/webrtc/include" CACHE PATH "" FORCE)
set(WEBRTC_LIBRARY_DIR    "${_PLATFORM_ROOT}/webrtc/lib"     CACHE PATH "" FORCE)
set(OPENH264_DIR          "${_PLATFORM_ROOT}/openh264"       CACHE PATH "" FORCE)
set(LIBCXX_INCLUDE_DIR    "${_LLVM_ROOT}/libcxx/include"     CACHE PATH "" FORCE)
set(LIBCXXABI_INCLUDE_DIR "${_PLATFORM_ROOT}/webrtc/include/third_party/libc++abi/src/include" CACHE PATH "" FORCE)
set(_SORA_CLANG_DIR       "${_LLVM_ROOT}/clang"              CACHE PATH "" FORCE)
```

### バージョン注入

- `CMakeLists.txt` で `file(READ ${CMAKE_CURRENT_SOURCE_DIR}/VERSION VERSION_RAW)` + `string(STRIP "${VERSION_RAW}" SORA_PYTHON_SDK_VERSION)` で値を取得する
- `if(DEFINED ENV{BUILD_PROFILE} AND "$ENV{BUILD_PROFILE}" STREQUAL "debug")` のとき `set(SORA_PYTHON_SDK_VERSION "${SORA_PYTHON_SDK_VERSION}+debug")` で末尾連結する
- `target_compile_definitions(sora_sdk_ext PRIVATE "SORA_PYTHON_SDK_VERSION=\"${SORA_PYTHON_SDK_VERSION}\"")` のように引数全体をダブルクォートで包み内側はバックスラッシュエスケープする形に変える（ `-D` 組み立て時の引数分割を防ぎ、 `+` を含むトークンを伝播させる）
- `src/sora.cpp:216, 223` の `BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION)` を `SORA_PYTHON_SDK_VERSION` の直接連結に書き換える（マクロ展開結果が C 文字列リテラルになるため）
- `[tool.scikit-build.metadata.version]` 経由の Python 側 `__version__` には `+debug` は付かない。 C++ 側 `SORA_PYTHON_SDK_VERSION` のみが `+debug` 付きになる。 これは `setup.py:19-21` の現状挙動と同じ。 `tests/test_version.py` は `__version__` と VERSION ファイル文字列を比較するため、 `BUILD_PROFILE=debug` でも test は通る
- 既存 `run.py:268-273` の `importlib.metadata.version('sora-sdk' or 'sora-sdk-rpi')` 経由のバージョン注入は捨てる。 `sora-sdk-rpi` パッケージ名分岐は 0004 で wheel 名を切り替える際に `[[tool.scikit-build.overrides]]` または別経路で扱う（ 0001 のスコープ外）

### CMakeLists.txt の変更

- `CMakeLists.txt:54` の `set(TARGET_OS "" CACHE STRING ...)` の直後に `set(SORA_GEN_PYI ON CACHE BOOL "Generate .pyi stub")` を追加する。 既存 `run.py:376-380` は Windows native とクロスコンパイル時に `SORA_GEN_PYI=OFF` を渡しており、 0001 は ubuntu-24.04 x86_64 native のみ対応で ON が妥当。 0003 (jetson / ubuntu armv8 cross) / 0004 (rpi) / 0005 (Windows native) では `[[tool.scikit-build.overrides]]` で `cmake.define.SORA_GEN_PYI = "OFF"` を渡して上書きする
- `SORA_PYTHON_SDK_PLATFORM` cache 変数を導入し、未設定時は `/etc/os-release` から自動算出する
- `include(cmake/scripts/fetch_deps.cmake)` を `CMakeLists.txt:60` （既存空行）に挿入する。 これにより L59 の `set(SORA_DIR "" CACHE PATH ...)` と L61 の `list(APPEND CMAKE_PREFIX_PATH ${SORA_DIR})` の間で `fetch_deps.cmake` が呼ばれ、 末尾の `set(... CACHE PATH "" FORCE)` で `find_package(Boost CONFIG)` / `find_package(WebRTC)` / `find_package(Sora)` が新パスで解決される
- `include(fetch_deps.cmake)` 直後に `if(NOT CMAKE_C_COMPILER)` ガードで `set(CMAKE_C_COMPILER "${_SORA_CLANG_DIR}/bin/clang" CACHE FILEPATH "" FORCE)` / `set(CMAKE_CXX_COMPILER "${_SORA_CLANG_DIR}/bin/clang++" CACHE FILEPATH "" FORCE)` を設定する。 `project()` より後だと既に compiler が確定しているため、 `CMakeLists.txt` 冒頭（ `project()` 前）で `fetch_deps.cmake` を `include` する必要がある。 具体的な挿入順序は「解決方法」を参照
- `target_compile_definitions(sora_sdk_ext PRIVATE SORA_PYTHON_SDK_VERSION=${SORA_PYTHON_SDK_VERSION})` （ `CMakeLists.txt:106` ）を `target_compile_definitions(sora_sdk_ext PRIVATE "SORA_PYTHON_SDK_VERSION=\"${SORA_PYTHON_SDK_VERSION}\"")` に変更する
- `install(TARGETS sora_sdk_ext LIBRARY DESTINATION .)` （ `CMakeLists.txt:204` ）を `install(TARGETS sora_sdk_ext LIBRARY DESTINATION sora_sdk)` に変更する
- `install(FILES py.typed sora_sdk_ext.pyi DESTINATION ".")` （ `CMakeLists.txt:206` ）を `install(FILES ${CMAKE_CURRENT_BINARY_DIR}/py.typed ${CMAKE_CURRENT_BINARY_DIR}/sora_sdk_ext.pyi DESTINATION sora_sdk)` に変更する。 `py.typed` と `sora_sdk_ext.pyi` は `nanobind_add_stub` の `MARKER_FILE py.typed` / `OUTPUT sora_sdk_ext.pyi` 指定で `${CMAKE_CURRENT_BINARY_DIR}` 直下に生成される。 `src/sora_sdk/py.typed` は git tracked ではないため clean checkout の CI runner では存在せず、 source tree 側から install してはならない。 `if (SORA_GEN_PYI)` / `endif()` ガード自体（ L205, L207 ）は変更しない

### wheel

- 0001 で生成する wheel の platform tag は `linux_x86_64` （ scikit-build-core デフォルト）。 `manylinux_2_35_x86_64` への変換は 0006 で `auditwheel repair --strip --only-plat` を別ステップで実施する
- ルート `.gitignore` に `/_deps` を追加する（既存に `/_build` と `src/sora_sdk/*.so` 等は登録済み）

### CI 影響

`.github/workflows/build.yml` を 0001 と同じ PR で以下のように変更する。 詳細は「解決方法」を参照。

- `build_pyi` job 全体に `if: false` を追加する（ 0001 完了後は scikit-build-core が wheel 内に pyi を直接同梱するため不要。 完全削除は 0006 ）
- `build_ubuntu` job の `needs: [build_pyi]` から `build_pyi` を削除し、 `build_pyi` artifact の download と cp ステップを削除する
- `build_ubuntu` matrix から `ubuntu-22.04_x86_64` / `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` / `raspberry-pi-os_armv8` の 4 entry を `exclude:` で除外する（ `ubuntu-24.04_x86_64` のみを残す）
- `build_ubuntu_arm` / `build_macos` / `build_windows` job 全体に `if: false` を追加する（ `build_ubuntu_arm` は新方針で 0006 で完全削除予定。 `build_macos` は 0002 で、 `build_windows` は 0005 で復活）
- `e2e_test` job 全体に `if: false` を追加する。 `./.github/workflows/e2e-test.yml` 側は disable する platform の artifact 名を hardcode 参照しているため復活させると 404 で失敗する。 0006 で対応する
- `slack_notify` job の `needs:` から `build_ubuntu_arm` / `build_macos` / `build_windows` を一時的に削除する。 GitHub Actions の `if: ${{ !cancelled() }}` 仕様で skip された upstream に依存していると常時 success 扱いになり Slack 通知のシグナルが壊れるため
- `publish_wheel` / `create-release` は upstream の `build_macos` / `build_windows` が skip されることで GitHub Actions 仕様により自動的に skip される。 加えて `publish_wheel` matrix / `create-release` の `actions/download` 呼び出し列は disable 対象 platform を hardcode 参照しており、 0001 期間中に成功する `ubuntu-24.04_x86_64` の artifact を拾う entry が存在しないため、 仮に手動で needs を外しても release は不完全になる。 0001 完了から 0002 / 0003 / 0004 / 0005 完了までの期間は **タグを打たない運用** を 0001 PR description にチェックボックスとして明記する
- branch protection との整合: 必須チェックに `build_ubuntu_arm` / `build_macos` / `build_windows` / `build_pyi` / `e2e_test` の job が含まれていると 0001 マージが詰まる。 PR 作成時に `gh api repos/shiguredo/sora-python-sdk/branches/develop/protection --jq '.required_status_checks.contexts'` で確認し、 disable 対象が含まれていれば branch protection を一時的に編集して除外する。 確認結果と編集内容は PR description のチェックリストに記載する（ issue 完了条件には含めない）

### pytest

- 0001 完了時点で通すのは `pytest tests/test_version.py` のみ
- `tests/test_version.py` は `os.path.dirname(os.path.dirname(__file__))` で `<repo>/VERSION` を参照し、 `sora_sdk.__version__` と比較する
- 加えて wheel に同梱された `sora_sdk_ext.*.so` が import / load 可能かを動作確認する（「完了条件」参照）

## 完了条件

- `ubuntu-24.04_x86_64` + Python 3.12 / 3.13 / 3.14 で `uv build --wheel` が成功する（ `uv python pin <ver> && uv venv && uv build --wheel` で個別に検証）
- 生成された wheel の中身を `python -m zipfile -l dist/*.whl` で確認すると `sora_sdk/sora_sdk_ext.cpython-*-linux-gnu.so` / `sora_sdk/sora_sdk_ext.pyi` / `sora_sdk/py.typed` / Python ソースが含まれている（ wheel タグは `cp312-cp312-linux_x86_64` 等）
- `setup.py` を削除し、 build backend が `scikit_build_core.build` に切り替わっている
- WebRTC / Sora / Boost / OpenH264 / LLVM (clang + libcxx + libcxxabi) の取得が CMake configure 内で完結する
- 次の手順で動作確認が成功する:
  1. `uv venv`
  2. `uv sync --no-install-project` （ `--no-install-project` を付けないと `uv sync` 段階で scikit-build-core によるフルビルドが走り、 `uv build --wheel` で重複ビルドになる）
  3. `uv build --wheel`
  4. `uv pip install --force-reinstall dist/*.whl`
  5. `uv run --no-sync pytest tests/test_version.py` が成功する（ `--no-sync` を付けないと `uv run` が暗黙的に `uv sync` を呼んで dist の wheel を再ビルドで上書きする）
  6. `uv run --no-sync python -c "from sora_sdk import sora_sdk_ext; print(sora_sdk_ext.__file__)"` が `site-packages/sora_sdk/sora_sdk_ext.cpython-*-linux-gnu.so` を出力する（ ImportError / undefined symbol が出ない）
  7. `uv run --no-sync python -c "import sora_sdk; print(sora_sdk.Sora)"` がクラスを返す（動的リンクの解決まで含めて成功する）
- `BUILD_PROFILE=debug uv build --wheel` でも上記が成功する。 `BUILD_PROFILE=debug uv build --wheel 2>&1 | tee /tmp/build.log` の出力に `grep -E '"SORA_PYTHON_SDK_VERSION=.*\+debug"' /tmp/build.log` で 1 行以上 hit する（ `target_compile_definitions` 由来の `-D"SORA_PYTHON_SDK_VERSION=\"X.Y.Z+debug\""` がコンパイル コマンドラインに現れる）
- `_build/` / `_deps/` が 2 回目以降の `uv build --wheel` で再 DL されない（ `_deps/<platform>/.stamps/*` と `_deps/llvm/<host_key>/.stamps/llvm` のタイムスタンプ未更新を確認）
- CI で `build_ubuntu` の `ubuntu-24.04_x86_64` entry が green になり、 0001 で disable した他 job は skip 表示される

## 解決方法

### pyproject.toml

`[build-system]` を以下に置換する。

```toml
[build-system]
requires = ["scikit-build-core>=0.11.3", "nanobind==2.12.0"]
build-backend = "scikit_build_core.build"
```

`[project]` / `[project.urls]` / 既存 `[dependency-groups]` 等は維持する。 `[dependency-groups] dev` から `nanobind==2.12.0` を削除する。

末尾に以下のセクション群を追加する。

```toml
[tool.scikit-build]
minimum-version = "0.11.3"
build-dir = "_build/{wheel_tag}"

[tool.scikit-build.cmake]
version = ">=4.2"

[tool.scikit-build.ninja]
version = ">=1.13"

[tool.scikit-build.wheel]
packages = ["src/sora_sdk"]
exclude = ["sora_sdk_ext.pyi", "py.typed", "sora_sdk_ext.*.so", "sora_sdk_ext.*.pyd"]

[tool.scikit-build.metadata.version]
provider = "scikit_build_core.metadata.regex"
input = "VERSION"
regex = "(?P<value>\\S+)"

[tool.scikit-build.cmake.define]
TARGET_OS = "ubuntu"

[[tool.scikit-build.overrides]]
if.env.BUILD_PROFILE = "^debug$"
cmake.build-type = "Debug"
```

### deps.json

リポジトリ直下に「設計方針 → deps.json」セクションの JSON を新設する。

### cmake/scripts/fetch_deps.cmake

「設計方針 → fetch_deps.cmake のヘルパ関数」と「メインスクリプト」の CMake コードを `cmake/scripts/fetch_deps.cmake` に保存する。

### CMakeLists.txt

L1 から L72 までを以下のような流れに書き換える（行番号は変更後の目安）:

1. `cmake_minimum_required(VERSION 4.1)` （既存維持）
2. `cmake_policy` 群（既存維持）
3. `SORA_PYTHON_SDK_PLATFORM` cache 変数を新規宣言し、未指定時は `/etc/os-release` から自動算出する
4. `DEPS_ROOT` を `${CMAKE_SOURCE_DIR}/_deps` に確定する
5. `set(SORA_DIR "" CACHE PATH ...)` / `set(Boost_ROOT "" CACHE PATH ...)` 等の既存 CACHE 宣言（ L54-59 ）を維持する
6. `set(SORA_GEN_PYI ON CACHE BOOL "Generate .pyi stub")` を `set(TARGET_OS ...)` （ L54 ）の直後に追加する
7. `find_package(Python ...)` 群（既存 L17-47 ）の **直後、 `project()` の前** に `include(cmake/scripts/fetch_deps.cmake)` を呼ぶ。 ただし `project()` より前で `Python_EXECUTABLE` を解決するには工夫が必要。 具体的には:
   - `project(sora_sdk)` の前に「 ubuntu-24.04 x86_64 only / `SORA_PYTHON_SDK_PLATFORM` 算出 / `fetch_deps.cmake` include 」を実行する
   - `fetch_deps.cmake` で `find_package(Python REQUIRED COMPONENTS Interpreter)` を `_sora_fetch_llvm` 直前で呼ぶ（ scikit-build-core は `Python_EXECUTABLE` を環境変数経由でも渡してくるため、 まず `if(NOT Python_EXECUTABLE) find_package(Python ...) endif()` でガードする）
   - `fetch_deps.cmake` の末尾で `set(CMAKE_C_COMPILER "${_SORA_CLANG_DIR}/bin/clang" CACHE FILEPATH "" FORCE)` / `set(CMAKE_CXX_COMPILER "${_SORA_CLANG_DIR}/bin/clang++" CACHE FILEPATH "" FORCE)` を設定する
   - その後で `project(sora_sdk)` を呼ぶ。 これで compiler が `_SORA_CLANG_DIR/bin/clang(++)` で確定する
8. `list(APPEND CMAKE_PREFIX_PATH ${SORA_DIR})` / `list(APPEND CMAKE_MODULE_PATH ${SORA_DIR}/share/cmake)` （既存 L61-62 ）を維持する
9. `file(READ ${CMAKE_CURRENT_SOURCE_DIR}/VERSION VERSION_RAW)` + `string(STRIP "${VERSION_RAW}" SORA_PYTHON_SDK_VERSION)` を追加する。 `if(DEFINED ENV{BUILD_PROFILE} AND "$ENV{BUILD_PROFILE}" STREQUAL "debug") set(SORA_PYTHON_SDK_VERSION "${SORA_PYTHON_SDK_VERSION}+debug") endif()` で `+debug` 連結
10. `find_package(Boost CONFIG)` / `find_package(WebRTC)` / `find_package(Sora)` / `find_package(nanobind CONFIG)` （既存 L69-72 ）を維持する
11. `nanobind_add_module` / `nanobind_add_stub` （既存 L78-104 ）を維持する
12. `target_compile_definitions(sora_sdk_ext PRIVATE SORA_PYTHON_SDK_VERSION=${SORA_PYTHON_SDK_VERSION})` （ L106 ）を `target_compile_definitions(sora_sdk_ext PRIVATE "SORA_PYTHON_SDK_VERSION=\"${SORA_PYTHON_SDK_VERSION}\"")` に変更する
13. `set_target_properties` / `if(TARGET_OS ...)` 群（既存 L108-190 ）を維持する
14. OpenH264 / dynamic_h264 部分（既存 L193-199 ）を維持する
15. `target_link_libraries` （既存 L201-202 ）を維持する
16. `install(TARGETS sora_sdk_ext LIBRARY DESTINATION .)` （ L204 ）を `install(TARGETS sora_sdk_ext LIBRARY DESTINATION sora_sdk)` に変更する
17. `if (SORA_GEN_PYI)` （ L205 ）と `endif()` （ L207 ）は維持する。 中の `install(FILES py.typed sora_sdk_ext.pyi DESTINATION ".")` （ L206 ）を `install(FILES ${CMAKE_CURRENT_BINARY_DIR}/py.typed ${CMAKE_CURRENT_BINARY_DIR}/sora_sdk_ext.pyi DESTINATION sora_sdk)` に変更する

`cmake_policy(SET CMP0190 OLD)` （ L15 ）も既存維持する。

### src/sora.cpp

L210-225 周辺を以下のように変更する。

変更前（ L211-217 ）:

```cpp
  if (user_agent) {
    config.user_agent = std::optional<std::string>(*user_agent);
  } else {
    // 無指定時はデフォルトの User-Agent を設定する
    config.user_agent = std::optional<std::string>(
        "Mozilla 5.0 (Sora Unity SDK/" BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION) ")");
  }
```

変更後:

```cpp
  if (user_agent) {
    config.user_agent = std::optional<std::string>(*user_agent);
  } else {
    // 無指定時はデフォルトの User-Agent を設定する
    config.user_agent = std::optional<std::string>(
        "Mozilla 5.0 (Sora Unity SDK/" SORA_PYTHON_SDK_VERSION ")");
  }
```

変更前（ L222-223 ）:

```cpp
  config.sora_client =
      "Sora Python SDK " BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION);
```

変更後:

```cpp
  config.sora_client =
      "Sora Python SDK " SORA_PYTHON_SDK_VERSION;
```

`src/sora.cpp` 冒頭に `boost/preprocessor/stringize.hpp` の直接 include は無く `sora.h` 経由で取り込まれているため、 include 文の変更は不要。

### .github/workflows/build.yml

- `build_pyi` job （ L53 ）の `jobs.build_pyi` 直下に `if: false` を追加する
- `build_ubuntu` job （ L84 ）の `needs: [build_pyi]` （ L118 ）から `build_pyi` を削除する（ `needs:` 行を完全削除）
- `build_ubuntu` job の matrix に `exclude:` ブロックを追加して以下 4 entry を除外する:
  - `{ platform: { name: ubuntu-22.04_x86_64 } }`
  - `{ platform: { name: ubuntu-22.04_armv8 } }`
  - `{ platform: { name: ubuntu-24.04_armv8 } }`
  - `{ platform: { name: raspberry-pi-os_armv8 } }`
- `build_ubuntu` job の `download-artifact name: sora_sdk_${python_version}` ステップ（ L123-126 ）と `cp sora_sdk/py.typed src/sora_sdk/py.typed` + `cp sora_sdk/sora_sdk_ext.pyi src/sora_sdk/sora_sdk_ext.pyi` ステップ（ L127-129 ）を削除する
- `build_ubuntu` job の `uv run python run.py build ${{ matrix.platform.target }}` 行（ L155 / L161 ）を削除し、 `uv build` だけを残す
- `build_ubuntu_arm` job （ L172 ） / `build_macos` job （ L230 ） / `build_windows` job （ L281 ）の各 `jobs.<name>` 直下に `if: false` を追加する
- `e2e_test` job （ L322 ）の `jobs.e2e_test` 直下に `if: false` を追加する
- `slack_notify` job （ L329 ）の `needs: [build_ubuntu, build_ubuntu_arm, build_macos, build_windows]` から `build_ubuntu_arm` / `build_macos` / `build_windows` を削除し、 `needs: [build_ubuntu]` のみにする
- `publish_wheel` / `create-release` は触らない（ upstream skip で自動的に skip される）

### .gitignore

ルート `.gitignore` に `/_deps` を追加する。

### setup.py

リポジトリ直下から削除する。

### 触らないファイル

- `run.py` / `buildbase.py` / `pypath.py` / `MANIFEST.in` / `DEPS` は触らない（削除は 0006 ）
- これらは scikit-build-core 経路（ `uv build` ） からは参照されない。 `run.py format` 等の開発用途は残る

### CHANGES.md

`## develop` セクション **先頭** に以下を追加する（既存規約 CHANGE → ADD → UPDATE → FIX 順）:

```
- [CHANGE] build backend を setuptools から scikit-build-core に切り替える
  - @voluntas
```

既存 `[UPDATE] setuptools を ~=82.0 に上げる` / `[UPDATE] wheel を ~=0.46 に上げる` エントリの削除は 0006 で `[build-system] requires` から setuptools / wheel が完全に消えるタイミングでまとめて扱う（ 0001 単独では `[CHANGE]` を追加するに留める）。

移行期間中の CI 一時 disable や `setup.py` 削除等の実装詳細はリリースノートに含めない。

## ロールバック

0001 マージ後に develop 上で不具合が発覚した場合の手順:

1. `git revert -m 1 <merge-commit>` で revert PR を作成する
2. revert PR の CI 確認ポイント:
   - `build_pyi` job が復活して green になる
   - `build_ubuntu_arm` / `build_macos` / `build_windows` / `e2e_test` の `if: false` が解除される
   - `build_ubuntu` matrix の `exclude:` が削除される
3. revert 後、 `git show HEAD~1 -- setup.py` で `setup.py` の内容が完全復元されているか確認する
4. forward fix を選ぶ判断基準: CI green の disable 対象が 1 platform のみで、 `setup.py` を残す必要が無いことが確認できる場合は revert ではなく追加の修正コミットで対応する
