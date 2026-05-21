# scikit-build-core 導入と ubuntu-24.04 x86_64 ネイティブビルド完結

- Priority: High
- Created: 2026-05-21
- Completed: -
- Model: Composer 2.5
- Branch: feature/change-scikit-build-core-native-deps

## 目的

build backend を `setuptools.build_meta` から `scikit_build_core.build` に切替え、 ubuntu-24.04 x86_64 host で `uv build --wheel` 一発で wheel を生成して install 後の最小 pytest が通る状態にする。 WebRTC / Sora C++ SDK / Boost / OpenH264 / LLVM (libwebrtc 同梱 clang + libcxx + libcxxabi ヘッダ) の取得を `run.py` / `buildbase.py` 経路から CMake configure 時取得 (`cmake/scripts/fetch_deps.cmake`) に移す。 取得物の構成・ヘッダコピー処理・既存ターゲット定義は維持し、 取得手段だけ移植する。

## 優先度根拠

- 後続 issue (0002 〜 0007) が本 issue の成果物 (`cmake/scripts/fetch_deps.cmake` / `_deps/` レイアウト / scikit-build-core overrides 構造) を前提に組まれている。
- 二段ビルド (`run.py build` → `uv build`) と `build_pyi` artifact 経路が CI 信頼性を下げている。
- 既存の `setup.py:bdist_wheel.get_tag` ハードコード platform tag や `run.py:268-273` 経由の `importlib.metadata.version` による C++ マクロ注入はトラブル源で、 次の依存更新前に整理しておきたい。

## スコープ

含む:

- `pyproject.toml` の build backend を `scikit_build_core.build` に切替える。
- `setup.py` を削除する。
- `CMakeLists.txt` の更新と `cmake/scripts/fetch_deps.cmake` 新設。
- WebRTC / Sora / Boost / OpenH264 / LLVM を CMake configure 時に取得する。
- `src/sora.cpp:215-216, 222-223` の `BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION)` を `SORA_PYTHON_SDK_VERSION` 直接連結に書き換える。 あわせて同 2 箇所の `Sora Unity SDK` リテラルを `Sora Python SDK` に直す。
- ubuntu-24.04 x86_64 native で `uv build --wheel` 成功 + `pytest tests/test_version.py` 完走。
- CI は ubuntu-24.04 x86_64 のみ動かす。 他 platform job と `build_pyi` / `e2e_test` / build-debug.yml / e2e-test.yml は `if: false` で一時停止する。 `build_ubuntu` matrix から `ubuntu-24.04_x86_64` 以外を `exclude` する。

含まない（別 issue で扱う）:

- macOS arm64 (0002) / Linux arm64 cross (0003 ubuntu armv8, 0004 jetson + raspberry-pi-os) / Windows (0005)。
- レガシーファイル削除、 `build_pyi` / `build_ubuntu_arm` 完全削除、 `e2e_test` 復活、 `auditwheel repair` による manylinux タグ付与、 sha256 検証 (0006)。
- Makefile (0007)。
- pytest E2E マーカー再設計（別 issue）。
- `BUILD_PROFILE=debug` 時の C++ マクロへの `+debug` 連結。 既存 `setup.py:19-21` は `setup()` の `version` 引数経由で dist-info にも +debug を入れていたが、 scikit-build-core の `metadata.version` provider は VERSION ファイル直読みで +debug を載せられない。 C++ 側だけ +debug を付けると `__version__` と User-Agent が不一致になるため、 +debug 連結自体を導入しない。 文字列レベルの debug 区別が必要なら 0006 で build-debug.yml の scikit-build-core 経路化と合わせて再設計する。
- `MANIFEST.in` の削除（参照されない状態にするのみ。 削除は 0006）。

## 現状

- build backend は `setuptools.build_meta`。 `uv run python run.py build <target>` が `_install/<target>/` に deps を取得し cmake を手動実行して `.so` を `src/sora_sdk/` にコピー、 後段 `uv build` が `setup.py:bdist_wheel.get_tag()` でハードコード platform tag (`manylinux_2_35_x86_64` 等) を付ける二段構成。
- `build_pyi` job が ubuntu-24.04 x86_64 で `.pyi` / `py.typed` を生成し artifact 化、 各 platform job が download / cp する経路。
- `CMakeLists.txt:54-59` の CACHE は 6 個。 `OPENH264_DIR` / `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` / `SORA_PYTHON_SDK_VERSION` / `SORA_GEN_PYI` は run.py 経由の `-D` 注入で自動 CACHE 化。
- `src/sora.cpp:216, :223` のみが `BOOST_PP_STRINGIZE` を使い、 解決は Boost / WebRTC の transitive include に偶発依存している。 `Sora Unity SDK` リテラルは `src/sora.cpp:215` の 1 箇所のみ（`grep -rn "Sora Unity SDK" src/` で確認）。

## 設計方針

### レイアウト

| 既存（`run.py` 経路） | 本 issue 後（`uv build` 経路） |
| --- | --- |
| `_install/<target>/{webrtc,sora,boost,openh264}` | `_deps/<platform>/{webrtc,sora,boost,openh264}` |
| `_install/<target>/llvm/{clang,libcxx}` | `_deps/llvm/<host_key>/{clang,libcxx}` |

`<platform>` は `SORA_PYTHON_SDK_PLATFORM` （本 issue では `ubuntu-24.04_x86_64` のみ）。 `<host_key>` は `${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}` （例 `x86_64-Linux`、 0002 で `arm64-Darwin`、 0005 で `x86_64-Windows`）。 Chromium 由来 clang バイナリは ubuntu バージョン違いで切替えないので host key に ubuntu バージョンを含めない。

### pyproject.toml

- `[build-system]` を `requires = ["scikit-build-core>=0.11.3", "nanobind==2.12.0"]` / `build-backend = "scikit_build_core.build"` に置換する。
- `[dependency-groups] dev` から `nanobind==2.12.0` を削除する（`src/` / `tests/` 内に `import nanobind` は無い）。
- `[tool.scikit-build]`: `minimum-version = "0.11.3"` / `build-dir = "_build/{wheel_tag}"`（Python ABI ごとに build-dir 分離し `CMakeCache.txt` の `Python_INCLUDE_DIR` キャッシュ干渉を防ぐ）。
- `[tool.scikit-build.cmake] version = ">=4.2"` / `[tool.scikit-build.ninja] version = ">=1.13"`。 `cmake_minimum_required(VERSION 4.1)` は変更しない（4.2 で要求を満たすので矛盾なし）。
- `[tool.scikit-build.cmake.define]`: `TARGET_OS = "ubuntu"` のみ。 fetch スクリプトの include は `CMakeLists.txt` 側で行う（後述）。
- `[tool.scikit-build.wheel] packages = ["src/sora_sdk"]` のみ。 **`wheel.exclude` は使わない**。 `wheel.exclude` は wheel build dir 全体走査でも評価されるため `*.so` 等の平坦パターンは CMake install 出力まで除外してしまう。 ローカル `src/sora_sdk/sora_sdk_ext.*.so` の混入は `.gitignore`（既に `src/sora_sdk/*.so` 等を含む）と、 packages コピー時の `target_path.is_file()` skip ガードで防ぐ。
- `install-dir` は明示せず空文字デフォルト。 CMake `install(... DESTINATION sora_sdk)` と `wheel.packages` 由来コピーが `site-packages/sora_sdk/` で同居する。
- `[tool.scikit-build.metadata.version]`: `provider = "scikit_build_core.metadata.regex"` / `input = "VERSION"` / `regex = "(?P<value>\\S+)"`。
- `[tool.uv]` / `[tool.uv.pip]` は触らない。

### deps.json

リポジトリ直下に新設する。 JSON 構造:

- `webrtc.version` / `webrtc.url_template` （`{version}` / `{platform}` プレースホルダ） / `webrtc.strip_components`。
- `sora_cpp_sdk.version` / `.url_template` / `.strip_components`。
- `boost.version` / `.url_template` （boost 用に `{sora_version}` も使う。 Boost は Sora C++ SDK の release ページに同梱されるため） / `.strip_components`。
- `openh264.version` （`v` プレフィックス付き tag 名） / `openh264.git` （リポジトリ URL）。

`strip_components` の実値、 `LIBCXXABI_INCLUDE_DIR` 末尾 `/include/__cxxabi_config.h` の所在は実装時に `curl -sL <url> | tar tzf - | head -5` で確認して確定する。 拡張子 (`.zip`) 対応は 0005、 sha256 検証は 0006 で導入する。

### fetch_deps.cmake の include 経路

`cmake/scripts/fetch_deps.cmake` を新設し、 `CMakeLists.txt` の `project()` 命令の **直前** に次を書く:

```cmake
list(APPEND CMAKE_PROJECT_TOP_LEVEL_INCLUDES "${CMAKE_CURRENT_LIST_DIR}/cmake/scripts/fetch_deps.cmake")
```

CMake 3.24+ の公式機能で、 最初の `project()` の中（言語有効化前）に実行される。 `${CMAKE_CURRENT_LIST_DIR}` で絶対パス化されるため scikit-build-core の build-dir に依存しない。 `pyproject.toml` から `CMAKE_PROJECT_TOP_LEVEL_INCLUDES` は渡さない（相対パス解決の保証が無いため）。

### fetch_deps.cmake の入出力契約

入力（呼び出し前に確定済み）:

- `Python_EXECUTABLE`: scikit-build-core が `_build/{wheel_tag}/CMakeInit.txt` 経由 (`CACHE PATH "" FORCE`) で渡してくる。 fetch_deps.cmake 冒頭で `if(NOT Python_EXECUTABLE) message(FATAL_ERROR ...) endif()` でガードする。 `python_hints` デフォルト true 前提（本 issue では変更しない）。
- `CMAKE_HOST_SYSTEM_PROCESSOR` / `CMAKE_HOST_SYSTEM_NAME`: `project()` 内呼び出しなので確定済み。
- `SORA_PYTHON_SDK_PLATFORM`: 未設定なら本スクリプトが `/etc/os-release` から算出する（後述）。

出力（取得成功時に `set(... CACHE PATH "" FORCE)` で確定する変数）:

| 変数 | 値（`ubuntu-24.04_x86_64` 例） |
| --- | --- |
| `SORA_DIR` | `${DEPS_ROOT}/<platform>/sora` |
| `Boost_ROOT` | `${DEPS_ROOT}/<platform>/boost` |
| `WEBRTC_INCLUDE_DIR` | `${DEPS_ROOT}/<platform>/webrtc/include` |
| `WEBRTC_LIBRARY_DIR` | `${DEPS_ROOT}/<platform>/webrtc/lib` |
| `OPENH264_DIR` | `${DEPS_ROOT}/<platform>/openh264` |
| `LIBCXX_INCLUDE_DIR` | `${DEPS_ROOT}/llvm/<host_key>/libcxx/include` |
| `LIBCXXABI_INCLUDE_DIR` | `${DEPS_ROOT}/<platform>/webrtc/include/third_party/libc++abi/src/include` |
| `_SORA_CLANG_DIR` | `${DEPS_ROOT}/llvm/<host_key>/clang` |

`DEPS_ROOT = ${CMAKE_SOURCE_DIR}/_deps`。 `_SORA_CLANG_DIR` は 0002 / 0005 が参照する想定で 0001 から出力契約に含める。

`CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` は LLVM fetch 完了後に `_SORA_CLANG_DIR/bin/clang(++)` を期待値とし、 `if(NOT CMAKE_C_COMPILER STREQUAL "<expected>")` ガード付きで `set(... CACHE FILEPATH "" FORCE)` する（同じ値を連続 FORCE すると CMake が cache invalidation エラーを出すため）。

### fetch_deps.cmake のメインスクリプト

順序:

1. `Python_EXECUTABLE` の存在ガード。
2. `SORA_PYTHON_SDK_PLATFORM` 自動検出（未設定時のみ）+ 許容リスト検証（本 issue は `ubuntu-24.04_x86_64` のみ。 ユーザが明示的に `-DSORA_PYTHON_SDK_PLATFORM=...` を渡しても許容リストでチェックしバイパスは認めない）。
3. `${DEPS_ROOT}` を `file(MAKE_DIRECTORY)`、 `file(LOCK "${DEPS_ROOT}/.fetch.lock" GUARD PROCESS TIMEOUT 1800)` で排他取得（複数 Python ABI 並列ビルド時の `_deps/<platform>/` への同時書き込み回避。 CMake 3.5+ で提供。 process 終了で自動 release）。
4. deps.json を `file(READ)` + `string(JSON GET)` で読む。 URL テンプレート展開は `{sora_version}` → `{version}` → `{platform}` の順（boost テンプレート内 `{sora_version}` に含まれる `{version}` が誤置換されるのを防ぐ）。
5. webrtc → sora → boost → openh264 → llvm の順に取得（LLVM が `webrtc/VERSIONS` を参照するため webrtc を先に確定させる）。
6. 出力契約の表の 8 変数を CACHE FORCE 設定 + `CMAKE_C/CXX_COMPILER` をガード経由で FORCE 設定。

### 各取得関数（散文契約）

- `_sora_fetch_archive(name url stamp_path dest_dir strip_components)` （末尾に `cmake_parse_arguments(_arg "" "SHA256" "" ${ARGN})` で `SHA256` キーワード引数の受け口を 0001 段階で用意する。 本 issue では値を渡さず、 0006 で sha256 検証導入時に値が渡される）:
  - stamp 内容が `url` と一致したら skip。
  - skip しない場合は `dest_dir` を REMOVE_RECURSE してから `${_archive_dir}/.archives/${name}.tar.gz` に `file(DOWNLOAD ... INACTIVITY_TIMEOUT 120 TIMEOUT 1800 STATUS _status)`。 status code 0 以外なら部分ファイルを `file(REMOVE)` 、 1 秒スリープでリトライ、 3 回までで FATAL_ERROR。
  - 展開は **system `tar`** で行う (`find_program(NAMES tar NO_CACHE)` + `tar -xzf <archive> --strip-components=<n> -C <dest>`)。 CMake の `cmake -E tar` は `--strip-components` を **サポートしていない** ため使えない（ubuntu 24.04 / Windows 10+ / macOS 11+ いずれも system `tar` が同梱されている前提）。 失敗時は `dest_dir` を削除して FATAL_ERROR。
  - 展開成功後に stamp を書く（親ディレクトリは事前に `file(MAKE_DIRECTORY)`）。
- `_sora_git_shallow(url ref dest)`: `dest` を REMOVE_RECURSE + MAKE_DIRECTORY 後、 `git init` → `git remote add origin` → `git fetch --depth=1 origin <ref>` → `git reset --hard FETCH_HEAD` を順に実行（3 回までリトライ）。 `git clone --depth 1 --branch <sha>` は GitHub の `uploadpack.allowReachableSHA1InWant` 設定依存で raw SHA を拒否されるため使わない。
- `_sora_fetch_openh264(version git_url dest stamp_path)`: stamp が `version` と一致したら skip。 skip しない場合は `find_program(_SORA_MAKE_EXECUTABLE make NO_CACHE)` で make を解決し（不在なら `apt-get install build-essential` を促す FATAL_ERROR）、 `_sora_git_shallow` で clone した一時 src で `make -C <src> install-headers PREFIX=<dest>` を実行、 src を削除して stamp を書く。
- `_sora_fetch_llvm(webrtc_install_dir dest_root stamp_path)`: `webrtc_install_dir/VERSIONS` から次の 6 キーを抽出する: `WEBRTC_SRC_TOOLS_URL`、 `WEBRTC_SRC_TOOLS_COMMIT`、 `WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL`、 `WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT`、 `WEBRTC_SRC_BUILDTOOLS_URL`、 `WEBRTC_SRC_BUILDTOOLS_COMMIT`。 VERSIONS は `KEY=value` / `KEY="value"` 両形式が混在するため、 `string(REPLACE "\n" ";")` でリスト化後 `foreach` + `MATCHES "^${_key}=\"?([^\"]+)\"?$"` で取り出す。 stamp は 6 値の連結。
  - skip しない場合は `dest_root/{clang,libcxx,buildtools,tools}` を REMOVE_RECURSE し、 `_sora_git_shallow` で tools / libcxx / buildtools を clone。
  - `${Python_EXECUTABLE}` で `${dest_root}/tools/clang/scripts/update.py --output-dir ${dest_root}/clang` を実行（`WORKING_DIRECTORY ${dest_root}/tools` を明示）。
  - `buildtools/third_party/libc++/__config_site` と `__assertion_handler` を `libcxx/include/` に `configure_file(... COPYONLY)` でコピー。
  - tools / buildtools を削除、 stamp を書く。

### SORA_PYTHON_SDK_PLATFORM の自動検出

`SORA_PYTHON_SDK_PLATFORM` 未設定時のみ実行する:

1. `CMAKE_HOST_SYSTEM_NAME` が `Linux` でなければ FATAL_ERROR（0002 / 0005 で許容拡張）。
2. `/etc/os-release` を `file(READ)` し、 `string(REPLACE "\n" ";")` + `foreach` で `ID` / `VERSION_ID` を抽出（`lsb_release` には依存しない）。 `ID != ubuntu` なら FATAL_ERROR。
3. `set(SORA_PYTHON_SDK_PLATFORM "ubuntu-${VERSION_ID}_${CMAKE_HOST_SYSTEM_PROCESSOR}" CACHE STRING "" FORCE)` で確定。
4. 許容リスト（本 issue は `ubuntu-24.04_x86_64` のみ）に含まれなければ FATAL_ERROR。

### CMakeLists.txt の変更点

- 既存 `cmake_minimum_required` / `cmake_policy` / `project(sora_sdk)` / `find_package(Python)` の順序は変えない。
- `project(sora_sdk)` の直前に `list(APPEND CMAKE_PROJECT_TOP_LEVEL_INCLUDES "${CMAKE_CURRENT_LIST_DIR}/cmake/scripts/fetch_deps.cmake")` を追加。
- 既存 `:54-59` の CACHE 宣言 6 個に加えて、 `OPENH264_DIR` / `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` の CACHE PATH 宣言と、 `SORA_PYTHON_SDK_PLATFORM` の CACHE STRING 宣言を追加（`fetch_deps.cmake` から FORCE 設定される受け口）。
- `set(SORA_GEN_PYI ON CACHE BOOL "Generate .pyi stub")` を `set(TARGET_OS ...)` 直後に追加。 0003 / 0004 / 0005 は `build-dir = _build/{wheel_tag}` で fresh configure になるため `-DSORA_GEN_PYI=OFF` が後で渡されればそのまま反映される。
- `target_compile_definitions(sora_sdk_ext PRIVATE SORA_PYTHON_SDK_VERSION=${SORA_PYTHON_SDK_VERSION})` （`:106`）を `target_compile_definitions(sora_sdk_ext PRIVATE SORA_PYTHON_SDK_VERSION="${SORA_PYTHON_SDK_VERSION}")` に変更（CMake 標準のイディオム。 外側クォート無し）。
- `set_target_properties(sora_sdk_ext PROPERTIES CXX_SCAN_FOR_MODULES OFF)` と `set_target_properties(nanobind-static PROPERTIES CXX_SCAN_FOR_MODULES OFF)` を `set_target_properties(... CXX_STANDARD 20)` の直後に追加する。 CMake 3.28+ は `CXX_STANDARD 20` の対象に対して C++20 module 依存スキャン (`clang-scan-deps`) を自動有効化するが、 libwebrtc 同梱 clang バイナリには `clang-scan-deps` が含まれず、 Sora C++ SDK 側も C++20 module を使っていないため OFF にする。
- `install(TARGETS sora_sdk_ext LIBRARY DESTINATION .)` （`:204`）を `... DESTINATION sora_sdk` に変更。
- `install(FILES py.typed sora_sdk_ext.pyi DESTINATION ".")` （`:206`）を `install(FILES ${CMAKE_CURRENT_BINARY_DIR}/py.typed ${CMAKE_CURRENT_BINARY_DIR}/sora_sdk_ext.pyi DESTINATION sora_sdk)` に変更（既存 `nanobind_add_stub` (`:96-103`) は `OUTPUT_PATH` 未指定で `CMAKE_CURRENT_BINARY_DIR` 直下に書き出すため）。 `if (SORA_GEN_PYI)` ガードは維持。

### バージョン注入と src/sora.cpp

- `CMakeLists.txt` で `file(READ VERSION _RAW)` + `string(STRIP)` で `SORA_PYTHON_SDK_VERSION` を取得し、 上記 `target_compile_definitions` で C 文字列リテラルとして渡す。
- `src/sora.cpp:215-216` を `"Mozilla 5.0 (Sora Python SDK/" SORA_PYTHON_SDK_VERSION ")"` に変更（Unity → Python の文言修正含む）。
- `src/sora.cpp:222-223` を `"Sora Python SDK " SORA_PYTHON_SDK_VERSION` に変更（`BOOST_PP_STRINGIZE` を外すのみ）。
- 既存 `run.py:268-273` の `importlib.metadata.version` 経由のバージョン注入は捨てる。 `sora-sdk-rpi` パッケージ名の切替は 0004 で扱う。

### wheel と CI

- 生成 wheel の platform tag は `linux_x86_64`（scikit-build-core デフォルト）。 PyPI 公開不可だが本 issue 〜 0005 期間は PyPI publish を凍結する（`publish_wheel` / `create-release` は `tags/202*` 条件付きなので tag を打たない運用で対応。 PR description のチェックリストで管理）。 manylinux 化は 0006。
- `_PYTHON_HOST_PLATFORM` は native では不要（クロス時 0003 / 0004 で導入）。
- ルート `.gitignore` に `/_deps` を追加。

`.github/workflows/build.yml`:

- `build_pyi` / `build_ubuntu_arm` / `build_macos` / `build_windows` / `e2e_test` の各 job に `if: false`。
- `build_ubuntu` job の `needs: [build_pyi]` 削除、 `download-artifact` step と `cp sora_sdk/py.typed ...` step を削除。 既存 x86_64 用 step (`if: matrix.platform.arch == 'x86_64'`) の `uv run python run.py build ...` を削除し `uv build --wheel` のみを残す（既存 `uv build` から sdist 生成も止める）。 armv8 step / multistrap install step は matrix exclude で動かないので残置（0003 で復活）。
- `build_ubuntu` matrix に `exclude:` を追加し `name` キー一致で 4 entry 除外:
  ```yaml
  exclude:
    - platform: { name: ubuntu-22.04_x86_64 }
    - platform: { name: ubuntu-22.04_armv8 }
    - platform: { name: ubuntu-24.04_armv8 }
    - platform: { name: raspberry-pi-os_armv8 }
  ```
  GitHub Actions の exclude は指定キーがすべて一致する組み合わせを除外する。 `platform.name` のみ指定で当該 platform × python_version 3 種すべてが除外され、 残るのは `ubuntu-24.04_x86_64` × py 3.12 / 3.13 / 3.14。
- `slack_notify.needs` を `[build_ubuntu]` のみに変更（disable された job への依存を外す。 0002 / 0005 で再追加、 0006 で `build_ubuntu_arm` は削除確定）。
- `publish_wheel` / `create-release` は変更しない（tag 起動条件付き）。

`.github/workflows/build-debug.yml`: 唯一の `build_ubuntu` job に `if: false`。 ローカルで debug build を試す開発者は `uv build --wheel -C cmake.build-type=Debug` 等を直接実行する（0006 で scikit-build-core 経路へ完全移行）。

`.github/workflows/e2e-test.yml`: 独立トリガ (`push` / `schedule`) で動くため、 配下の全 job （`jobs:` 配下のすべて、 `slack_notify` 含む）に `if: false` を追加（0006 で復活）。

## 完了条件

- ubuntu-24.04_x86_64 + Python 3.12 / 3.13 / 3.14 で `uv build --wheel` が成功する（ローカル直列で 3 通り、 CI matrix の 3 並列でも green）。
- 生成 wheel タグが `cp3XY-cp3XY-linux_x86_64`、 `python -m zipfile -l dist/*.whl` 出力に `sora_sdk/sora_sdk_ext.cpython-*-linux-gnu.so` / `sora_sdk_ext.pyi` / `py.typed` / Python ソースが含まれる。 dist-info の Version が `VERSION` ファイルと一致。
- `find _build -name sora_sdk_ext.pyi` で pyi の実位置が `_build/<wheel_tag>/sora_sdk_ext.pyi` 直下。
- `ls _deps/ubuntu-24.04_x86_64/webrtc/include/third_party/libc++abi/src/include/__cxxabi_config.h` が存在する。
- ローカル `src/sora_sdk/sora_sdk_ext.cpython-*-linux-gnu.so` を残したまま `uv build --wheel` しても、 wheel 内の `.so` は CMake install 由来のみ。
- `setup.py` が削除され、 build backend が `scikit_build_core.build` に切替わっている。
- 動作確認:
  1. `uv venv`
  2. `uv sync --no-install-project`（`--no-install-project` 必須）
  3. `uv build --wheel`
  4. `uv pip install --force-reinstall dist/*.whl`
  5. `uv run --no-sync pytest tests/test_version.py` 成功
  6. `uv run --no-sync python -c "from sora_sdk import sora_sdk_ext; print(sora_sdk_ext.__file__)"` で site-packages 配下の `.so` を出力
  7. `uv run --no-sync python -c "import sora_sdk; s = sora_sdk.Sora(); print(s)"` がインスタンス生成に成功
- 同じ Python ABI で 2 回目の `uv build --wheel` を実行すると `_deps/<platform>/.stamps/*` と `_deps/llvm/<host_key>/.stamps/llvm` の mtime が変化しない。
- CI で `build_ubuntu` の `ubuntu-24.04_x86_64` × 3 Python が green、 disable した job 群が skip 表示。
- `src/sora.cpp:215` のリテラルが `Mozilla 5.0 (Sora Python SDK/...)`。

## 解決方法

各セクションは「設計方針」の決定に従い最小差分で適用する。 個別ファイル:

- **pyproject.toml**: `[build-system]` 置換、 末尾に `[tool.scikit-build]` 系セクション追記、 `[dependency-groups] dev` から `nanobind==2.12.0` のみ削除。
- **deps.json**: 「設計方針 → deps.json」の構造で新設。
- **cmake/scripts/fetch_deps.cmake**: 「設計方針 → fetch_deps.cmake の入出力契約 / メインスクリプト / 各取得関数 / SORA_PYTHON_SDK_PLATFORM 自動検出」を満たすよう新設。
- **CMakeLists.txt**: 「設計方針 → CMakeLists.txt の変更点」の差分適用。
- **src/sora.cpp**: `:215-216` と `:222-223` の 2 箇所を「設計方針 → バージョン注入と src/sora.cpp」の通り書き換える。
- **setup.py**: 削除。
- **MANIFEST.in**: 触らない（参照されない状態で残す。 削除は 0006）。 本 issue 〜 0006 期間は `uv build --sdist` を実行しない運用とする。
- **.gitignore**: 末尾 `/smallproj` 行の直前に `/_deps` を追加。
- **.github/workflows/{build,build-debug,e2e-test}.yml**: 「設計方針 → wheel と CI」の指示に従い `if: false` / `needs` 削減 / matrix exclude / step 削除 / x86_64 step を `uv build --wheel` 化。

### CHANGES.md

`## develop` セクションの整理:

- 既存 `[UPDATE] wheel を ~=0.46 に上げる` / `[UPDATE] setuptools を ~=82.0 に上げる` の 2 エントリは削除する（`[build-system] requires` から両者が消えるため）。
- 既存 `[UPDATE] Sora C++ SDK のバージョンを 2026.2.0-canary.11 に上げる` 配下のサブ箇条はすべて触らない（`[UPDATE] CMAKE_VERSION を 4.3.2 に上げる` サブ箇条の削除は 0006）。
- 追加（`[CHANGE] → [FIX]` の順）:

```
- [CHANGE] build backend を setuptools から scikit-build-core に切り替える
  - @voluntas
- [FIX] User-Agent と sora_client の文字列を `Sora Unity SDK` から `Sora Python SDK` に直す
  - @voluntas
```

移行期間中の CI 一時 disable や `setup.py` 削除等の実装詳細はリリースノートに含めない。

## ロールバック

revert は `fetch_deps.cmake` の根本設計（`CMAKE_PROJECT_TOP_LEVEL_INCLUDES` 経路 / `file(LOCK)` 設計 / wheel.packages と CMake install の同居挙動 / ABI ごと build-dir 分離）に起因する不具合で追加コミットでは修正できない場合に選ぶ。 個別関数や設定値レベル（リトライ条件 / VERSIONS 抽出 regex / stamp 一致判定 / `.gitignore` 追加項目）は revert ではなく追加コミットで前進させる。

手順: `git revert -m 1 <merge-commit>` で revert PR を作成し、 disable した job 群（`build_pyi` / `build_ubuntu_arm` / `build_macos` / `build_windows` / `e2e_test` / build-debug.yml / e2e-test.yml）が active に戻って green になることを CI で確認する。 `_deps/` キャッシュは残留しても無害。

## 参照（一次資料）

実装時に挙動の根拠が必要なら次を参照する:

- `scikit_build_core/cmake.py:163-176, 230-241` — `init_cache` の `CMakeInit.txt` 書き出しと `-D` 引数構築。
- `scikit_build_core/builder/builder.py:275-294` — `python_hints` 経由の `Python_EXECUTABLE` / `PYTHON_EXECUTABLE` / `Python3_EXECUTABLE` 注入。
- `scikit_build_core/build/_pathutil.py:67` — `packages_to_file_mapping` の `target_path.is_file()` skip ガード。
- `scikit_build_core/build/_wheelfile.py:151-186` — wheel build dir 全走査時の `wheel.exclude` 適用。
- `scikit_build_core/build/_file_processor.py:34-108` — `each_unignored_file` の `.gitignore` 評価。
- `nanobind/cmake/nanobind-config.cmake:620-732` — `nanobind_add_stub` の `add_custom_command(OUTPUT ... WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})`。
