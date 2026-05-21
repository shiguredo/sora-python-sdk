# scikit-build-core 導入と ubuntu-24.04 x86_64 ネイティブビルド完結

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-scikit-build-core-native-deps

## 目的

ビルド backend を setuptools から scikit-build-core + nanobind + uv に移行する第一歩として、ubuntu-24.04 x86_64 ネイティブ環境で `uv build --wheel` 一発で wheel を生成し、その wheel を install した状態で `pytest tests/test_version.py` が通る状態にする。WebRTC / Sora C++ SDK / Boost / OpenH264 と LLVM 同梱の libc++ / libc++abi ヘッダの取得を `run.py` / `buildbase.py` から CMake 側に移し、`run.py build` を呼ばずに新経路だけで完結させる。

## 優先度根拠

High。以降の issue（macOS / Windows ネイティブ、クロスコンパイル、CI 切替、Makefile）の前提となる土台のため。0001 が通らなければ移行全体が始まらない。

## スコープ

含む:

- ubuntu-24.04 x86_64 ネイティブで `uv build --wheel` 一発による wheel 生成と install 後の最小 pytest 完走
- WebRTC / Sora C++ SDK / Boost / OpenH264 / libc++ / libc++abi ヘッダの CMake configure 時取得（システム `clang-19` でビルドするため clang バイナリ取得は不要。macOS / クロス向け clang バイナリは 0002 / 0003 / 0004 で扱う）
- `pyproject.toml` の build backend を scikit-build-core に切替
- `setup.py` を削除
- `CMakeLists.txt` の更新と `cmake/scripts/fetch_deps.cmake` 新設
- `src/sora.cpp:216,223` の `BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION)` を `SORA_PYTHON_SDK_VERSION` の直接連結に書き換え（マクロ定義をクォート付き文字列リテラルに変更するため）
- `build_pyi` job を 0001 で一時 disable する（0001 完了後は scikit-build-core が wheel 内に pyi を直接同梱するため、artifact 経由のコピー経路は不要。完全削除は 0006）
- 0001 で破壊される CI 非対応 platform job を 0001 と同じ PR で `if: false` で一時 disable する（具体的な対象は「CI 影響」参照。0002〜0005 で順次有効化）

含まない（別 issue で扱う）:

- macOS / Windows ネイティブ（0002 / 0005）
- ubuntu armv8 / jetson / RPi クロスコンパイル（0003 / 0004）
- レガシーファイル（`buildbase.py` / `run.py` / `pypath.py` / `MANIFEST.in` / `DEPS`）の削除（0006）
- 開発者向け Makefile（0007）
- PyPI publish 用 `auditwheel repair --strip --only-plat` 経由の `manylinux_2_35_x86_64` タグ付与（0006）
- pytest E2E マーカー再設計（別 issue。0001 では `pytest tests/test_version.py` のみ）
- 依存アーカイブの sha256 検証導入（0006 で扱う）

## 依存 issue への影響（事実記述。各 issue 自身の polish で対応）

- 0002 は当初「ubuntu x86_64 の LLVM / OpenH264 取得を 0001 後に追加する」スコープだったが、本 issue が ubuntu x86_64 必要分を取り込んだため、0002 は「macOS と Windows 向けの clang バイナリ取得と OpenH264 ヘッダ配置」へスコープを変更する必要がある
- 0006 が前提とする「`DEPS` ファイルは 0001 で `deps.json` へ移行済み」は厳密には誤り。0001 では `DEPS` を触らないため、0001 完了から 0006 完了までの期間 `DEPS` と `deps.json` が並存し `DEPS` 側はデッドコード化する。0006 で `DEPS` 削除と同時に「`[UPDATE] Sora C++ SDK のバージョンを 2026.2.0-canary.11 に上げる` 配下のサブ箇条書きで `CMAKE_VERSION を 4.3.2 に上げる` 等を扱う方針」を再検討する必要がある
- 0001 完了時点で `MANIFEST.in` / `buildbase.py` / `run.py` / `pypath.py` は build backend からは参照されなくなる（scikit-build-core は `MANIFEST.in` を読まない）。`run.py` の `format` サブコマンド等の開発用途は残るが、ファイル本体の削除は 0006
- 0007 の `make develop` が `uv pip install -e .` を含むが、0001 で `[tool.uv] package = false` を入れない方針のため `uv sync` 単独で scikit-build-core 経由のビルド + install が走る。0007 polish 時に「`uv sync` との二重ビルドを避けるための `--no-build-isolation` 付与」など整理が必要

## 現状

- `pyproject.toml` の build backend は `setuptools.build_meta`
- `run.py build` が `buildbase.py` 経由で deps を `_install/<target>/` に取得し、`cmake` を手動実行して `.so` を `src/sora_sdk/` にコピーする
- `setup.py` の `bdist_wheel.get_tag()` が ubuntu-24.04 x86_64 で `manylinux_2_35_x86_64` を強制する
- `CMakeLists.txt` は `find_package(Boost CONFIG)` / `find_package(WebRTC)` / `find_package(Sora)` を使い、`SORA_DIR` / `WEBRTC_INCLUDE_DIR` / `WEBRTC_LIBRARY_DIR` / `Boost_ROOT` / `OPENH264_DIR` / `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` / `SORA_PYTHON_SDK_VERSION` / `TARGET_OS` / `SORA_GEN_PYI` を `-D` で受け取る
- ubuntu ターゲットでは `-nostdinc++ -isystem${LIBCXX_INCLUDE_DIR}` と OpenH264 ヘッダ参照、`dynamic_h264_*.cpp` のコンパイルが無条件に要求される
- ubuntu-24.04 x86_64 ネイティブでは `run.py:290-291` でシステム `clang-19` を使う（libwebrtc 同梱 clang バイナリは未使用、libcxx / libcxxabi ヘッダのみが必要）
- `src/sora.cpp:216` と `src/sora.cpp:223` のみが `BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION)` を使う（`grep -rn 'BOOST_PP_STRINGIZE\|SORA_PYTHON_SDK_VERSION' src/` で確認済み。`src/sora.cpp` 冒頭に `boost/preprocessor/stringize.hpp` の直接 include は無く、`sora.h` 経由で取り込まれている）
- `.github/workflows/build.yml` の `build_ubuntu` / `build_ubuntu_arm` / `build_macos` / `build_windows` 各 job は `uv run python run.py build <target>` の直後に `uv build` を実行する 2 段構成。`build_pyi` は ubuntu-24.04 x86_64 で `run.py build` を呼んで `src/sora_sdk/sora_sdk_ext.pyi` を生成し artifact 化、各 platform job で download して `src/sora_sdk/` にコピーする経路を持つ
- `publish_wheel` / `create-release` は `needs: [build_ubuntu, build_macos, build_windows]`

## 設計方針

### build backend と pyproject.toml

- build-system を `scikit_build_core.build` に切替。`[build-system] requires` は `scikit-build-core>=0.11.3` と `nanobind==2.12.0` のみ（CMake / Ninja は scikit-build-core 経由で PyPI 取得。webcodecs-py と同方針）
- `[dependency-groups] dev` の `nanobind==2.12.0` は build-system に集約して削除（バージョンずれ防止）
- `cmake_minimum_required` は据え置く。`[tool.scikit-build.cmake] version` は実装時に `pip index versions cmake` で PyPI 提供を確認し、`CMAKE_VERSION=4.3.2`（既存 `DEPS`）を優先候補に上から `>=4.3` → `>=4.2` → `>=4.1` の順で確定する
- `[tool.scikit-build]` に `minimum-version = "0.11.3"` と `build-dir = "_build/{wheel_tag}"`
- `[tool.scikit-build.wheel]` に `packages = ["src/sora_sdk"]` と `exclude = ["sora_sdk_ext.pyi", "py.typed", "sora_sdk_ext.*.so", "sora_sdk_ext.*.pyd"]`（source tree 側に残るビルド成果物が `install(FILES)` の出力と二重コピーされる問題を防ぐ。scikit-build-core は `packages` 内相対パスを `pathspec.GitIgnoreSpec` で照合するため、`src/sora_sdk/` プレフィックス無しのファイル名のみで指定する）
- `[tool.scikit-build.metadata.version]` に `provider = "scikit_build_core.metadata.regex"` / `input = "VERSION"` / `regex = "(?P<value>\\S+)"`（scikit-build-core は `re.search` ベースで先頭一致するためアンカー不要。VERSION ファイルが ASCII 1 行 + 改行で `\\S+` が安全に動く）
- `[tool.scikit-build.cmake] build-type` のデフォルト `Release` を使い、`cmake.args` に `-DCMAKE_BUILD_TYPE` を重複指定しない
- `[[tool.scikit-build.overrides]]` で `if.env.BUILD_PROFILE = "^debug$"` のとき `cmake.build-type = "Debug"`（scikit-build-core の `if.env.<NAME>` は `re.search` 仕様のため `^...$` でアンカー必須）
- `[tool.uv]` には触らない（`uv sync` は scikit-build-core 経由でプロジェクト本体を install する。0007 で editable install へ切替予定）。既存の `[tool.uv.pip] exclude-newer = "7 days"` は build-isolation 内の依存解決にも影響しうるため、実装時に `scikit-build-core>=0.11.3` と `nanobind==2.12.0` のリリース日が 7 日以上経過していることを `uv pip index versions scikit-build-core nanobind` で確認する。7 日以内の場合は 0001 PR 内で `exclude-newer` を一時的に緩和する

### deps 取得

- `deps.json` をリポジトリ直下に新設。スキーマ:

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

  Boost のリリースは Sora C++ SDK の release ページに同梱されるため `{sora_version}` プレースホルダが必要。`strip_components` は 0001 実装時に実機で次のように確認し最終値を確定する（暫定は `1`）:

  ```
  curl -sL https://github.com/shiguredo-webrtc-build/webrtc-build/releases/download/m149.7827.0.0/webrtc.ubuntu-24.04_x86_64.tar.gz | tar tzf - | head -5
  curl -sL https://github.com/shiguredo/sora-cpp-sdk/releases/download/2026.2.0-canary.11/sora-cpp-sdk-2026.2.0-canary.11_ubuntu-24.04_x86_64.tar.gz | tar tzf - | head -5
  curl -sL https://github.com/shiguredo/sora-cpp-sdk/releases/download/2026.2.0-canary.11/boost-1.91.0_sora-cpp-sdk-2026.2.0-canary.11_ubuntu-24.04_x86_64.tar.gz | tar tzf - | head -5
  ```

  `openh264.version` は git tag 名 (`v` プレフィックス有) を保持する。`.github/workflows/build.yml:29` の `OPENH264_VERSION: 2.6.0` (`v` 無) は E2E 用ランタイム `.so` のダウンロード URL に使う別経路の値で、0001 では触らない（統一は別 issue）。
- 取得処理は `cmake/scripts/fetch_deps.cmake` を新設し configure 時に `include()` で実行する
  - 入力契約: `SORA_PYTHON_SDK_PLATFORM`、`DEPS_ROOT`（`${PROJECT_ROOT}/_deps`）、`Python_EXECUTABLE`、`_SORA_UBUNTU_VERSION_ID`（`SORA_PYTHON_SDK_PLATFORM` 算出時に併設）を呼び出し前に設定済み
  - 出力契約: 取得成功時に以下のキャッシュ変数を `set(... CACHE PATH "" FORCE)` で確定する（既存 CACHE 宣言を上書きする）:

    | 変数 | 値（`SORA_PYTHON_SDK_PLATFORM = ubuntu-24.04_x86_64` 例） |
    |---|---|
    | `SORA_DIR`           | `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/sora` |
    | `Boost_ROOT`         | `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/boost` |
    | `WEBRTC_INCLUDE_DIR` | `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/webrtc/include` |
    | `WEBRTC_LIBRARY_DIR` | `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/webrtc/lib` |
    | `OPENH264_DIR`       | `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/openh264` |
    | `LIBCXX_INCLUDE_DIR` | `${DEPS_ROOT}/llvm/${LLVM_HOST_KEY}/libcxx/include` |
    | `LIBCXXABI_INCLUDE_DIR` | `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/webrtc/include/third_party/libc++abi/src/include` |

    `LLVM_HOST_KEY = ${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}-${_SORA_UBUNTU_VERSION_ID}`（例 `x86_64-Linux-24.04`）。glibc 互換性のため ubuntu バージョンも host キーに含める。クロス時もホスト側 LLVM を使うため `SORA_PYTHON_SDK_PLATFORM` ではなく host 単位でキャッシュする。LIBCXXABI_INCLUDE_DIR の末尾 `/include` は必須（WebRTC アーカイブ内 `…/libc++abi/src/include/__cxxabi_config.h` を指す）
  - 取得完了後に既存 `CMakeLists.txt:61-62` 相当の `list(APPEND CMAKE_PREFIX_PATH ${SORA_DIR})` / `list(APPEND CMAKE_MODULE_PATH ${SORA_DIR}/share/cmake)` を呼べるよう、`include(cmake/scripts/fetch_deps.cmake)` の挿入位置を「既存 `CMakeLists.txt:59` (`set(SORA_DIR "" CACHE PATH ...)`) の直後、L61 の `list(APPEND CMAKE_PREFIX_PATH)` の前」とする。`fetch_deps.cmake` 末尾で 7 変数すべてを以下の通り `CACHE PATH "" FORCE` で上書きすることで、既存の空文字 CACHE 宣言が上書きされて `find_package(Boost CONFIG)` / `find_package(WebRTC)` / `find_package(Sora)` がすべて新パスで解決される:

  ```cmake
  set(SORA_DIR              "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/sora"     CACHE PATH "" FORCE)
  set(Boost_ROOT            "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/boost"    CACHE PATH "" FORCE)
  set(WEBRTC_INCLUDE_DIR    "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/webrtc/include" CACHE PATH "" FORCE)
  set(WEBRTC_LIBRARY_DIR    "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/webrtc/lib"     CACHE PATH "" FORCE)
  set(OPENH264_DIR          "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/openh264"       CACHE PATH "" FORCE)
  set(LIBCXX_INCLUDE_DIR    "${DEPS_ROOT}/llvm/${LLVM_HOST_KEY}/libcxx/include"       CACHE PATH "" FORCE)
  set(LIBCXXABI_INCLUDE_DIR "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/webrtc/include/third_party/libc++abi/src/include" CACHE PATH "" FORCE)
  ```
- LLVM 取得（0001 スコープ縮小版）
  - 0001 では `clang/scripts/update.py` 経由の clang バイナリ取得は **行わない**（ubuntu-24.04 x86_64 ネイティブはシステム `clang-19` を使うため）
  - 必要なのは libc++ ヘッダと、その配下に置く `__config_site` / `__assertion_handler` のみ
  - 手順: WebRTC アーカイブ展開後、その中の `VERSIONS` ファイル（`KEY="value"` または `KEY=value` 形式、`buildbase.py:read_version_file` 同様）を `file(READ)` + `string(REGEX MATCH)` で読み、以下の KEY 値を取り出す:
    - `WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL`
    - `WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT`
    - `WEBRTC_SRC_BUILDTOOLS_URL`
    - `WEBRTC_SRC_BUILDTOOLS_COMMIT`
  - libcxx と buildtools を `_sora_git_shallow` で `--branch <commit> --depth 1` clone し、buildtools 側 `third_party/libc++/__config_site` と `__assertion_handler` を libcxx 側 `include/` 配下にコピー
- ダウンロードと展開
  - アーカイブは `file(DOWNLOAD ... TLS_VERIFY ON SHOW_PROGRESS INACTIVITY_TIMEOUT 120 STATUS _st)` で取得し、`list(GET _st 0 _code)` で判定。失敗時最大 3 回リトライ
  - 展開は `execute_process(COMMAND ${CMAKE_COMMAND} -E tar xzf <archive> --strip-components=<n> WORKING_DIRECTORY <dest_dir>)`（`file(ARCHIVE_EXTRACT)` には strip 機能が無い）
  - git shallow clone は `execute_process(COMMAND git clone --depth 1 --branch <tag_or_commit> <url> <dir> RESULT_VARIABLE _r)`、失敗時最大 3 回リトライ
  - OpenH264 ヘッダ配置は **stamp ヒットで skip されない場合のみ** `find_program(MAKE_EXECUTABLE make)` を呼び、不在時に `message(FATAL_ERROR "OpenH264 のヘッダ配置には make が必要です。apt install build-essential を実行してください")` で停止。その後 `execute_process(COMMAND ${MAKE_EXECUTABLE} -C ${src} install-headers "PREFIX=${install_dir}")` を実行（`PREFIX=` をダブルクォートで包みパスの空白で分割されないようにする）。`find_program` を `_sora_fetch_openh264` 関数の冒頭ではなく実 fetch ブランチ内で呼ぶことで、再 fetch 不要時に `make` 不在環境（既に install 済みのキャッシュを使うだけのケース）でも CMake configure が止まらない
  - GitHub Actions `ubuntu-24.04` runner は `build-essential` が pre-install 済みのため CI では追加の `apt install` 不要
- キャッシュ
  - 各 install ディレクトリの 1 階層上 `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/.stamps/<dep>`（LLVM は `${DEPS_ROOT}/llvm/${LLVM_HOST_KEY}/.stamps/llvm`）に「展開済みリソースの識別文字列」を書く（install ディレクトリ内に置くと再 fetch 時の `rm -rf` で消える事故を防ぐ）
  - WebRTC / Sora / Boost の stamp は `_sora_fetch_archive` に渡された **解決済み URL** を書く（version 変更でも URL 変更でも stamp 不一致 → 再 fetch）
  - OpenH264 stamp は `openh264.version` の git tag 文字列。Cisco openh264 は release tag を後から動かさない運用のため tag で十分
  - LLVM stamp は `<LIBCXX_SRC_URL>.<LIBCXX_SRC_COMMIT>.<BUILDTOOLS_URL>.<BUILDTOOLS_COMMIT>` を `.` 区切り連結（WebRTC バージョン更新時に LLVM も再取得されるようにする）
  - 再 fetch 時は対象 install ディレクトリを `file(REMOVE_RECURSE)` してから展開。stamp ファイルの親ディレクトリは `file(MAKE_DIRECTORY)` で先に作る

### `cmake/scripts/fetch_deps.cmake` の関数構成

実装は以下のヘルパ関数を持つ:

- `function(_sora_fetch_archive name url stamp_path dest_dir strip)`: ダウンロード + tar xzf + stamp 書き込みのみを担う。SORA_DEP_* キャッシュ変数の設定は行わない
- `function(_sora_git_shallow url ref dest)`: git shallow clone のみ（stamp 書き込みは呼び出し側）
- `function(_sora_fetch_openh264 version git_url dest)`: `_sora_git_shallow` + `find_program(make)` + `make install-headers PREFIX=...` + stamp 書き込み
- `function(_sora_fetch_llvm webrtc_install_dir dest stamp_path)`: `webrtc_install_dir` は WebRTC アーカイブを展開した install ディレクトリ（例 `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/webrtc`）。直下の `VERSIONS` ファイルを `file(READ)` で読み、libcxx / buildtools を `_sora_git_shallow` で取得し `__config_site` / `__assertion_handler` をコピー、stamp 書き込み
- メインスクリプト末尾で `set(SORA_DIR ... CACHE PATH "" FORCE)` 等 7 変数を上書き設定

deps.json は `file(READ ...)` + `string(JSON GET ...)` で解析。URL テンプレート展開は `string(REPLACE)` を `{version}` → `{sora_version}` → `{platform}` の順で呼ぶ（`{sora_version}` のような複合プレースホルダを先に置換すると、置換後の値に `{version}` 等が含まれて二重置換する事故を防ぐ）。

### platform 文字列

- `SORA_PYTHON_SDK_PLATFORM` cache 変数を新設する（Sora C++ SDK 側 `SORA_*` 変数との衝突を回避するためプロジェクト固有 prefix）
- 未指定時は CMake 内で次の手順で算出:
  1. `file(READ /etc/os-release OS_RELEASE)`
  2. `string(REGEX MATCH "(^|\n)ID=([^\n]+)" _ ${OS_RELEASE})` で `ID` を抽出。`ubuntu` 以外なら `FATAL_ERROR("scikit-build-core migration phase 1 supports ubuntu only; got '${ID}'")`
  3. `string(REGEX MATCH "(^|\n)VERSION_ID=\"?([^\"\n]+)\"?" _ ${OS_RELEASE})` で `VERSION_ID` を抽出（クォート有無両対応・行頭アンカー）し `_SORA_UBUNTU_VERSION_ID` に保持
  4. `${CMAKE_HOST_SYSTEM_PROCESSOR}` から arch を取得
  5. 組み立て: `ubuntu-${_SORA_UBUNTU_VERSION_ID}_${arch}`
  6. `ubuntu-24.04_x86_64` 以外なら `FATAL_ERROR("scikit-build-core migration phase 1 supports ubuntu-24.04_x86_64 only; got '${SORA_PYTHON_SDK_PLATFORM}'. Other platforms will be added in subsequent migration phases.")`
- `lsb_release` には依存しない（ubuntu container でデフォルト未インストールのため）

### バージョン注入

- 既存 `src/sora.cpp:216` と `src/sora.cpp:223` の `BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION)` 経由 stringify を **`SORA_PYTHON_SDK_VERSION` の直接連結** に書き換える（CMake から渡す値を文字列リテラル `"2026.1.0.dev7"` に変更し、C++ 側で stringify 不要にする）
- `CMakeLists.txt` 側で `file(READ ${CMAKE_CURRENT_SOURCE_DIR}/VERSION VERSION_RAW)` + `string(STRIP ${VERSION_RAW} SORA_PYTHON_SDK_VERSION)` で値を取得し、`if(DEFINED ENV{BUILD_PROFILE} AND $ENV{BUILD_PROFILE} STREQUAL "debug")` のとき `+debug` を末尾連結
- `target_compile_definitions(sora_sdk_ext PRIVATE "SORA_PYTHON_SDK_VERSION=\"${SORA_PYTHON_SDK_VERSION}\"")` のように引数全体をダブルクォートで包み内側はバックスラッシュエスケープする形に変える（`-D` 組み立て時の引数分割を防ぎ、`+` を含むトークンを伝播させる）
- `[tool.scikit-build.metadata.version]` 経由の Python 側 `__version__` には `+debug` は付かない。C++ 側 `SORA_PYTHON_SDK_VERSION` のみが `+debug` 付きになる。これは `setup.py:19-21` の現状挙動と同じ。`tests/test_version.py` は `__version__` と VERSION ファイル文字列を比較するため、`BUILD_PROFILE=debug` でも test は通る

### wheel

- 0001 で生成する wheel の platform tag は `linux_x86_64`（scikit-build-core デフォルト）。`manylinux_2_35_x86_64` への変換は 0006 で `auditwheel repair --strip --only-plat` を別ステップで実施
- `SORA_GEN_PYI` は `CMakeLists.txt` の `set(TARGET_OS "" CACHE STRING ...)`（既存 L54）の直後に `set(SORA_GEN_PYI ON CACHE BOOL "Generate .pyi stub")` で宣言する（`option(...)` は既存 cache を上書きしないため、0003 / 0005 で `cmake.define.SORA_GEN_PYI = "OFF"` を override で渡せるよう `set CACHE BOOL` を使う）
- ルート `.gitignore` に `/_deps` を追加（既存に `/_build` と `src/sora_sdk/*.so` 等は登録済みのため追加不要）

### CI 影響

- 0001 で build backend を切り替えると CI の `uv build` ステップは全 job で scikit-build-core 経由になり、ubuntu-24.04 x86_64 以外の platform は `CMakeLists.txt` の `FATAL_ERROR` で落ちる
- 0001 と同じ PR で `.github/workflows/build.yml` を以下の通り変更する:
  - `build_pyi` job 全体に `if: false` を追加（0001 完了後は scikit-build-core が wheel 内に pyi を直接同梱するため不要。完全削除は 0006）
  - 各 platform job の `needs: [build_pyi]` から `build_pyi` を削除し、`build_pyi` artifact の download / cp ステップも削除する（残すと skip された upstream を待ち続けたり download-artifact が 404 で失敗する）
  - `build_ubuntu` matrix から `ubuntu-22.04_x86_64` / `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` entry を `exclude:` で除外する
  - `build_ubuntu_arm` / `build_macos` / `build_windows` job 全体に `if: false` を追加
  - `e2e_test` 全体に `if: false` を追加（matrix 内で disable された platform の artifact を hardcode 参照しているため、現状では復活させるのが困難）。0002〜0005 で復活させる
  - `publish_wheel` / `create-release` は `needs: [build_ubuntu, build_macos, build_windows]` で skip されるため、0001 完了から 0002〜0005 完了までの期間は **タグを打たない運用** を 0001 PR description にチェックボックスとして明記する
- branch protection 確認: PR 作成前に `gh api repos/shiguredo/sora-python-sdk/branches/develop/protection --jq '.required_status_checks.contexts'` で必須チェックに含まれる job 名を確認し、disable 対象が含まれる場合は branch protection 側で一時的に除外する（手順は PR description に明記）

### pytest

- 0001 完了時点で通すのは `pytest tests/test_version.py` のみ
- `tests/conftest.py:8` の `import jwt` が collect 時に必要なため、pytest 実行前に `uv sync` で dev グループ（`pyjwt` 含む）を入れておく
- `tests/test_version.py` は `os.path.dirname(os.path.dirname(__file__))` で `<repo>/VERSION` を参照する（cwd 非依存）。リポジトリの checkout 先で `pytest tests/test_version.py` を実行すれば動く
- E2E マーカー導入や `tests/conftest.py` の変更は別 issue

## 完了条件

- `ubuntu-24.04_x86_64` + Python 3.12 / 3.13 / 3.14 で `uv build --wheel` が成功する（Python バージョンごとに `uv python pin <ver> && uv venv && uv build --wheel` で個別に検証）
- 生成された wheel に `sora_sdk/sora_sdk_ext.*.so`、`sora_sdk/sora_sdk_ext.pyi`、`sora_sdk/py.typed`、Python パッケージが含まれる（wheel タグは `cp312-cp312-linux_x86_64` 等）
- `setup.py` を削除し、build backend が `scikit_build_core.build` に切り替わる
- WebRTC / Sora / Boost / OpenH264 / libcxx / libcxxabi の取得が CMake configure 内で完結する
- 手順「`uv venv` → `uv sync --no-install-project` → `uv build --wheel` → `uv pip install --force-reinstall dist/*.whl` → `uv run --no-sync pytest tests/test_version.py`」が成功する（`--no-install-project` を付けないと `uv sync` 段階で scikit-build-core によるフルビルドが走り、`uv build --wheel` で重複ビルドになる）
- `BUILD_PROFILE=debug uv build --wheel` でも上記が成功し、生成 wheel の C++ 側 `SORA_PYTHON_SDK_VERSION` に `+debug` が含まれることを `ninja -v` ログ等で確認できる
- `_build/` / `_deps/` が 2 回目以降の `uv build --wheel` で再 DL されない（`_deps/` 配下のタイムスタンプ未更新を確認）
- 0001 で disable した CI job 以外（`build_ubuntu` の 24.04 x86_64 entry）が CI で green になる

## 解決方法

- `pyproject.toml`
  - `[build-system]` を `requires = ["scikit-build-core>=0.11.3", "nanobind==2.12.0"]` / `build-backend = "scikit_build_core.build"`
  - `[tool.scikit-build]` に `minimum-version = "0.11.3"` / `build-dir = "_build/{wheel_tag}"`
  - `[tool.scikit-build.cmake]` に `version = ">=4.3"`（PyPI 提供状況に応じて降格）
  - `[tool.scikit-build.ninja]` に `version = ">=1.13"`
  - `[tool.scikit-build.wheel]` に `packages = ["src/sora_sdk"]` と `exclude = ["src/sora_sdk/sora_sdk_ext.pyi", "src/sora_sdk/py.typed", "src/sora_sdk/sora_sdk_ext.*.so", "src/sora_sdk/sora_sdk_ext.*.pyd"]`
  - `[tool.scikit-build.metadata.version]` に `provider = "scikit_build_core.metadata.regex"` / `input = "VERSION"` / `regex = "(?P<value>\\S+)"`
  - `[[tool.scikit-build.overrides]]` で `if.env.BUILD_PROFILE = "^debug$"` のとき `cmake.build-type = "Debug"`
  - `[dependency-groups] dev` から `nanobind==2.12.0` を削除
- `deps.json` を新設（設計方針のスキーマに従う）
- `CMakeLists.txt`
  - `set(SORA_GEN_PYI ON CACHE BOOL "Generate .pyi stub")` を既存 `set(TARGET_OS "" CACHE STRING ...)` の直後に追加
  - `SORA_PYTHON_SDK_PLATFORM` cache 変数を導入し、未設定時は `/etc/os-release` から自動算出（`ID=ubuntu` チェック含む）
  - `include(cmake/scripts/fetch_deps.cmake)` を `set(SORA_DIR "" CACHE PATH ...)`（既存 L59）の直後、`list(APPEND CMAKE_PREFIX_PATH)`（既存 L61）の前に挿入。これで fetch 後に `find_package` が新パスで解決される
  - `file(READ ... VERSION_RAW)` + `string(STRIP)` で `SORA_PYTHON_SDK_VERSION` を解決し、`BUILD_PROFILE=debug` で `+debug` 連結
  - L106 の `target_compile_definitions(sora_sdk_ext PRIVATE SORA_PYTHON_SDK_VERSION=${SORA_PYTHON_SDK_VERSION})` を `target_compile_definitions(sora_sdk_ext PRIVATE "SORA_PYTHON_SDK_VERSION=\"${SORA_PYTHON_SDK_VERSION}\"")` に変更
  - L204 の `install(TARGETS sora_sdk_ext LIBRARY DESTINATION .)` を `install(TARGETS sora_sdk_ext LIBRARY DESTINATION sora_sdk)` に変更
  - L205-207 の `install(FILES py.typed sora_sdk_ext.pyi DESTINATION ".")` を `install(FILES ${CMAKE_CURRENT_BINARY_DIR}/py.typed ${CMAKE_CURRENT_BINARY_DIR}/sora_sdk_ext.pyi DESTINATION sora_sdk)` に変更（パスを絶対化。`py.typed` は `nanobind_add_stub` の `MARKER_FILE py.typed` 指定で `${CMAKE_CURRENT_BINARY_DIR}/py.typed` に生成される。`src/sora_sdk/py.typed` は git tracked ではないため clean checkout の CI runner では存在せず、source tree 側から install してはならない）
- `cmake/scripts/fetch_deps.cmake` を新設（設計方針の関数構成に従う）
- `src/sora.cpp`
  - L216 を `"Mozilla 5.0 (Sora Unity SDK/" SORA_PYTHON_SDK_VERSION ")"` に変更
  - L223 を `"Sora Python SDK " SORA_PYTHON_SDK_VERSION` に変更
- ルート `.gitignore` に `/_deps` を追加
- `setup.py` を削除（本 issue で完了）
- `run.py` / `buildbase.py` / `pypath.py` / `MANIFEST.in` / `DEPS` は触らない（削除は 0006）
- `.github/workflows/build.yml`
  - `build_pyi` job 全体に `if: false` を追加（または job ごと削除）
  - 各 platform job の「`build_pyi` artifact ダウンロード」「`cp src/sora_sdk/py.typed sora_sdk/` 等」のステップを削除
  - `build_ubuntu` matrix から `ubuntu-22.04_x86_64` / `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` を exclude
  - `build_ubuntu_arm` / `build_macos` / `build_windows` job 全体に `if: false` を追加
- `CHANGES.md`
  - `## develop` セクション **先頭** に `- [CHANGE] build backend を setuptools から scikit-build-core に切り替える` + 2 文字インデントで `- @voluntas` を追加（CHANGE → ADD → UPDATE → FIX 順）
  - 既存 `[UPDATE] setuptools を ~=82.0 に上げる` / `[UPDATE] wheel を ~=0.46 に上げる` エントリは setuptools / wheel が `[build-system] requires` から削除されることで実質意味を失うため、同時に削除する
  - 移行期間中の CI 一時 disable や `setup.py` 削除等の実装詳細はリリースノートに含めない
