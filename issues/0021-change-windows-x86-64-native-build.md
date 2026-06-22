# Windows x86_64 ネイティブビルド対応

- Priority: High
- Created: 2026-05-21
- Polished: 2026-06-22
- Model: Kimi K2.7 Code
- Branch: feature/change-windows-x86-64-native-build

## 目的

0016 で ubuntu-24.04 x86_64 native 向けに実装した scikit-build-core + `cmake/scripts/fetch_deps.cmake` を Windows x86_64 でも動作させ、 Windows host 上で `uv build --wheel` 一発で Windows x86_64 用 wheel を生成できる状態にする。

## 設計の前提（プロジェクト全体の新方針からの該当部）

- 本 issue は 0016 / 0018 の完成形を前提とする。 0016 と 0018 は develop に取り込み済み。 0017 / 0019 / 0020 は未対応であり、 0021 はこれらが develop に取り込まれた後に rebase して取り込む。 0017 と 0019 は同一領域の代替案のため、 どちらが採用されるかは未確定であることに注意する
- ビルド環境は ubuntu-24.04 x86_64 host のみに集約するが、 macOS (arm64) と **Windows (x86_64) は例外的にそれぞれの OS で native build を維持する** （ cross-compile しない）
- Windows native は Windows x86_64 runner で native build する
- Windows は **MSVC 静的ランタイム (/MT) + Windows SDK** でビルドする。 libwebrtc 同梱 clang は使わない（既存 `CMakeLists.txt:192-208` が MSVC 静的ランタイム前提）。 libcxx / libcxxabi も使わない（ MSVC 標準 STL を使う）

## スコープ

含む:

- `cmake/scripts/fetch_deps.cmake` の `SORA_PYTHON_SDK_PLATFORM` 算出を Windows host 対応に拡張する（ `CMAKE_HOST_SYSTEM_NAME = Windows` 分岐で `windows_x86_64` を組み立てる）
- `_sora_fetch_llvm` の呼び出しを `if(NOT WIN32)` ガードで囲み、 Windows では LLVM 取得を skip する
- `_sora_fetch_openh264` の呼び出しを `if(NOT WIN32)` ガードで囲み、 Windows では OpenH264 取得を skip する
- WebRTC / Sora / Boost アーカイブの Windows 拡張子は `.zip` （ Linux / macOS は `.tar.gz` ）。 `deps.json` の `url_template` に `{ext}` プレースホルダを追加する
- `_sora_fetch_archive` を `.zip` / `.tar.gz` 両対応に拡張する
- `pyproject.toml` に `[[tool.scikit-build.overrides]]` で Windows の `TARGET_OS = "windows"` 上書きを追加する
- Windows native での `uv build --wheel` 成功と `pytest tests/test_version.py` 完走（ wheel タグは `cp3XY-cp3XY-win_amd64` ）
- `.github/workflows/build.yml` の `build_windows` job の `if: false` を解除し、 scikit-build-core 経路で完結させる
- `slack_notify` の `needs:` に `build_windows` を戻す
- `SORA_GEN_PYI` を Windows では `OFF` にする（ Windows では `nanobind_add_stub` 実行時にビルド直後の `.pyd` を import する必要があり、 ランタイム DLL / PATH の追加整備が必要なため当面 off にする。 再有効化時には `.pyd` と同じディレクトリに依存 DLL をコピーするか、 それらを含むディレクトリを `PATH` 環境変数に追加する対応が必要）

含まない（別 issue で扱う）:

- macOS arm64 native （ 0018 ）
- Linux arm64 cross-compile （ 0019 / 0020 ）
- レガシーファイル削除（ 0022 ）
- Makefile （ 0023 ）
- Windows での `.pyi` / `py.typed` 再有効化（別途新 issue で扱う）
- ローカル dev 用 CMake option（ `SORA_LOCAL_WEBRTC_BUILD_DIR` 等。別途新 issue で扱う）
- Windows x86 (32-bit) （プロジェクトでサポート対象外）
- Windows arm64 （プロジェクトでサポート対象外）

## 現状

- `CMakeLists.txt:77-80` で `TARGET_OS STREQUAL "windows"` のとき `Boost_USE_STATIC_RUNTIME ON` を立てる既存実装がある
- `CMakeLists.txt:192-208` の `if(TARGET_OS STREQUAL "windows")` ブランチで MSVC 設定が有効化される
- `CMakeLists.txt:211-217` の `if (NOT TARGET_OS STREQUAL "windows")` で OpenH264 ヘッダ参照と `dynamic_h264_*.cpp` を取り込んでいる。 Windows は **このブランチに入らず OpenH264 を使わない**
- 既存 `build.yml:268-307` の `build_windows` job は `windows-2025` runner で Python 3.12 / 3.13 / 3.14 を回し、 `uv sync` → `uv run python run.py build windows_x86_64` → `uv build` を実行する 2 段構成
- `e2e_test` job は 0016 から `if: false` のままであり、 本 issue では復活しない

## 設計方針

### SORA_PYTHON_SDK_PLATFORM 算出の Windows 対応

`fetch_deps.cmake` の自動検出ブロックに `CMAKE_HOST_SYSTEM_NAME STREQUAL "Windows"` 分岐を追加する。 完成形の該当部:

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

`CMAKE_HOST_SYSTEM_PROCESSOR` は Windows 上の CMake 64-bit 版では通常 `AMD64` を返す。 `x86_64` を許容するのは、 一部ツールチェーンやクロスコンパイル環境で `x86_64` が返る可能性に備えるため。

許容 `SORA_PYTHON_SDK_PLATFORM` リストに `windows_x86_64` を追加し、 リスト不一致時の FATAL_ERROR メッセージも実装時点の許容 platform 全てを列挙して更新する。 issue 番号や今後の追加予告は含めない。

### deps.json の Windows アーカイブ拡張子対応

Windows のアーカイブは `.zip` 形式のため、 `deps.json` の `url_template` に `{ext}` プレースホルダを追加する。 全 entry の完成形:

```json
{
  "webrtc": {
    "version": "<webrtc-version>",
    "url_template": "https://github.com/shiguredo-webrtc-build/webrtc-build/releases/download/{version}/webrtc.{platform}.{ext}",
    "strip_components": 1
  },
  "sora_cpp_sdk": {
    "version": "<sora-version>",
    "url_template": "https://github.com/shiguredo/sora-cpp-sdk/releases/download/{version}/sora-cpp-sdk-{version}_{platform}.{ext}",
    "strip_components": 1
  },
  "boost": {
    "version": "<boost-version>",
    "url_template": "https://github.com/shiguredo/sora-cpp-sdk/releases/download/{sora_version}/boost-{version}_sora-cpp-sdk-{sora_version}_{platform}.{ext}",
    "strip_components": 1
  }
}
```

展開後の URL 例:
- Windows: `webrtc.windows_x86_64.zip`
- Linux / macOS: `webrtc.ubuntu-24.04_x86_64.tar.gz`

### `_sora_expand_url` マクロの `{ext}` 置換

`_sora_expand_url` マクロの引数に `ext` を追加し、 `{sora_version}` → `{version}` → `{platform}` → `{ext}` の順で置換する。 `{sora_version}` を最初に置換する理由は 0016 と同じく、 `{version}` の誤置換を防ぐため。

```cmake
macro(_sora_expand_url out template version sora_version platform ext)
  set(${out} "${template}")
  string(REPLACE "{sora_version}" "${sora_version}" ${out} "${${out}}")
  string(REPLACE "{version}" "${version}" ${out} "${${out}}")
  string(REPLACE "{platform}" "${platform}" ${out} "${${out}}")
  string(REPLACE "{ext}" "${ext}" ${out} "${${out}}")
endmacro()
```

### `_sora_fetch_archive` の zip / tar.gz 両対応

`_sora_fetch_archive` の先頭コメントを `tar.gz / zip アーカイブの取得 + 展開 + stamp 書き込み` に更新する。 シグネチャに `ext` を追加する。 保存アーカイブ名は `${_archive_dir}/${name}.${ext}` にする。

`.tar.gz` の展開は 0016 と同じく system `tar` を使い、 `tar -xzf` で展開する。 `.zip` の展開は Windows runner の `C:\Windows\System32\tar.exe`（ bsdtar / libarchive ）を使い、 `tar -xf` で展開する。 `--strip-components` は bsdtar で zip 展開時も動作する。

`find_program(NAMES tar)` だけでは Windows 上で Git for Windows 同梱の GNU tar が先に見つかり、 GNU tar は zip を展開できない。 そのため Windows では `C:/Windows/System32` を優先探索し、 見つからなければエラーとする:

```cmake
if(WIN32)
  find_program(_SORA_TAR_EXECUTABLE NAMES tar PATHS "C:/Windows/System32" NO_DEFAULT_PATH NO_CACHE)
else()
  find_program(_SORA_TAR_EXECUTABLE NAMES tar NO_CACHE)
endif()
if(NOT _SORA_TAR_EXECUTABLE)
  message(FATAL_ERROR
    "tar command is required to extract archives. "
    "On Debian/Ubuntu: it ships with the base system; "
    "on Windows 10+: it ships with the OS.")
endif()
```

展開コマンドは拡張子に応じて切り替える。 `ext` が `zip` / `tar.gz` 以外の場合は FATAL_ERROR とする:

```cmake
if(ext STREQUAL "zip")
  execute_process(
    COMMAND "${_SORA_TAR_EXECUTABLE}" -xf "${_archive}"
            "--strip-components=${strip_components}" -C "${dest_dir}"
    RESULT_VARIABLE _extract_result)
elseif(ext STREQUAL "tar.gz")
  execute_process(
    COMMAND "${_SORA_TAR_EXECUTABLE}" -xzf "${_archive}"
            "--strip-components=${strip_components}" -C "${dest_dir}"
    RESULT_VARIABLE _extract_result)
else()
  message(FATAL_ERROR "Unsupported archive extension: ${ext}")
endif()
```

### `_sora_fetch_openh264` の Windows skip

Windows では `CMakeLists.txt:211-217` の通り OpenH264 動的呼び出しを使わない。 取得しても使用されないため、 メインスクリプトの `_sora_fetch_openh264` 呼び出しを `if(NOT WIN32)` で囲み skip する。 あわせて `OPENH264_DIR` の CACHE 確定も `if(NOT WIN32)` で囲み、 無効な空ディレクトリを指さないようにする。

### `_sora_fetch_llvm` の Windows skip

メインスクリプトで:

```cmake
if(NOT WIN32)
  _sora_fetch_llvm("${_PLATFORM_ROOT}/webrtc" "${_LLVM_ROOT}" "${_LLVM_STAMPS_ROOT}/llvm")
endif()
```

`_sora_fetch_llvm` を Windows では呼ばない。 これに伴い、 以下も `if(NOT WIN32)` ガードで囲む:

- `_LLVM_HOST_KEY` の定義
- `_LLVM_ROOT` / `_LLVM_STAMPS_ROOT` 用ディレクトリの作成
- `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` / `_SORA_CLANG_DIR` の CACHE 確定
- `fetch_deps.cmake` 末尾の `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` 確定

Windows ではこれらの変数を設定せず、 CMake / scikit-build-core のデフォルト探索により MSVC を使う。

### TARGET_OS の Windows 上書き

`pyproject.toml` の macOS override （`[tool.scikit-build.metadata.version]` 直後、`[tool.pytest.ini_options]` 直前）の直後に Windows override を追加する:

```toml
# Windows では MSVC + Ninja でビルドし、 nanobind_add_stub 実行時の .pyd import で
# 追加の DLL/PATH 整備が必要なため、当面 pyi / py.typed は生成しない。
[[tool.scikit-build.overrides]]
if.platform-system = "^win32"
inherit.cmake.define = "append"
cmake.define.TARGET_OS = "windows"
cmake.define.SORA_GEN_PYI = "OFF"
```

`inherit.cmake.define = "append"` を明示し、 base `[tool.scikit-build.cmake.define]` を置換しない。 `if.platform-system` は 0018 の macOS override と同じくアンカー付き `^win32` に統一する。

### LIBCXX / LIBCXXABI ガード

Windows では libcxx / libcxxabi を使わないため、 `fetch_deps.cmake` のメインスクリプト末尾の `set(LIBCXX_INCLUDE_DIR ... CACHE PATH "" FORCE)` / `set(LIBCXXABI_INCLUDE_DIR ...)` を `if(NOT WIN32)` で囲む。 `CMakeLists.txt:129-191` の macOS / ubuntu / jetson / raspberry-pi-os 分岐は `TARGET_OS=windows` では入らないため自動的に skip される。

### Boost / WebRTC / Sora アーカイブの Windows 命名確認

実装時に WebRTC / Sora / Boost の各 Windows zip アーカイブをダウンロードし、 トップレベルディレクトリが 1 階層のみで、`strip_components = 1` で既存 Linux / macOS と同じ構成になることを確認する。 確認コマンドの例:

```
tar -tf webrtc.windows_x86_64.zip | head -10
tar -tf sora-cpp-sdk-<version>_windows_x86_64.zip | head -10
tar -tf boost-<boost-version>_sora-cpp-sdk-<version>_windows_x86_64.zip | head -10
```

もしトップレベル構造が Linux / macOS と異なる場合は、 `deps.json` の `strip_components` を platform ごとに持たせるか、 展開後のトップレベルディレクトリを正規化する追加対応が必要になる。

### CI 影響

`build_windows` job （既存 `build.yml:268` ）の変更:

- `jobs.build_windows.if: false` を削除する
- `jobs.build_windows.needs: [build_pyi]` を完全削除する
- `actions/download-artifact` step とそれに続く 2 つの `cp` step を一括して削除する
- `uv sync` を `uv sync --no-install-project` に変更する（`uv sync` 単独だとプロジェクト本体がビルドされ、 続く `uv build --wheel` と二重ビルドになる）
- `uv run python run.py build windows_x86_64` 行を削除し、 同 step の `uv build` を `uv build --wheel` に変更する
- matrix から `target: windows_x86_64` キーを削除する。 残すキーは `name` / `runs_on` のみ（0018 の `build_macos` と同じく `target` / `os` を削って最小構成にする）
- `timeout-minutes` は Windows 初回ビルドの zip ダウンロード・展開 + MSVC ビルドを考慮し、 0018 の 15 分から 60 分に引き上げる。 数回計測後に短縮を検討する
- Ninja + MSVC ビルドを行うため、 `uv build --wheel` より前に `ilammy/msvc-dev-cmd` を使って amd64 開発者環境を有効化する

`slack_notify` job の `needs:` を `[build_ubuntu, build_macos]` から `[build_ubuntu, build_macos, build_windows]` に戻す。 `slack_notify` の `if: ${{ !cancelled() }}` は維持する。

## 完了条件

- Windows x86_64 host （ `windows-2025` runner ） + Python 3.12 / 3.13 / 3.14 で `uv build --wheel` が成功する
- 生成された wheel タグが `cp312-cp312-win_amd64` 等になる
- wheel 内に `sora_sdk/sora_sdk_ext.cp3XY-win_amd64.pyd` / Python ソースが含まれる（ `sora_sdk_ext.pyi` / `py.typed` は Windows では `SORA_GEN_PYI=OFF` のため含まれない）
- 次の手順で動作確認が成功する:
  1. `uv venv`
  2. `uv sync --no-install-project`
  3. `uv build --wheel`
  4. `uv pip install --force-reinstall dist/*.whl`
  5. `uv run --no-sync pytest tests/test_version.py` が成功する
  6. `uv run --no-sync python -c "from sora_sdk import sora_sdk_ext; print(sora_sdk_ext.__file__)"` が `site-packages\sora_sdk\sora_sdk_ext.cp3XY-win_amd64.pyd` を出力する
- `_deps/windows_x86_64/.stamps/{webrtc,sora,boost}` の mtime が 2 回目以降の `uv build --wheel` で変化しない
- `windows-2025` runner で `C:\Windows\System32\tar.exe` が存在し、 bsdtar / libarchive ベースであることを確認する
- CI で `build_windows` job が green になる

## 解決方法

### cmake/scripts/fetch_deps.cmake

- `SORA_PYTHON_SDK_PLATFORM` 算出に Windows 分岐を追加する
- `_sora_expand_url` マクロに `ext` 引数と `{ext}` 置換を追加する
- `_sora_fetch_archive` を `.zip` / `.tar.gz` 両対応に拡張する
  - シグネチャに `ext` を追加する
  - 保存アーカイブ名を `${_archive_dir}/${name}.${ext}` にする
  - `.tar.gz` は `tar -xzf` で展開する
  - `.zip` は `C:\Windows\System32\tar.exe` を優先探索して `tar -xf` で展開する
  - `ext` が `zip` / `tar.gz` 以外なら FATAL_ERROR とする
- メインスクリプトで `WIN32` 判定により `_EXT` 変数を `"zip"` / `"tar.gz"` に決定し、 `_sora_expand_url` / `_sora_fetch_archive` の呼び出しに渡す

```cmake
if(WIN32)
  set(_EXT "zip")
else()
  set(_EXT "tar.gz")
endif()

_sora_expand_url(_WEBRTC_URL "${_WEBRTC_URL_TEMPLATE}" "${_WEBRTC_VERSION}" "" "${SORA_PYTHON_SDK_PLATFORM}" "${_EXT}")
_sora_fetch_archive(webrtc "${_WEBRTC_URL}" "${_STAMPS_ROOT}/webrtc" "${_PLATFORM_ROOT}/webrtc" ${_WEBRTC_STRIP} "${_EXT}")

_sora_expand_url(_SORA_URL "${_SORA_URL_TEMPLATE}" "${_SORA_VERSION}" "" "${SORA_PYTHON_SDK_PLATFORM}" "${_EXT}")
_sora_fetch_archive(sora "${_SORA_URL}" "${_STAMPS_ROOT}/sora" "${_PLATFORM_ROOT}/sora" ${_SORA_STRIP} "${_EXT}")

_sora_expand_url(_BOOST_URL "${_BOOST_URL_TEMPLATE}" "${_BOOST_VERSION}" "${_SORA_VERSION}" "${SORA_PYTHON_SDK_PLATFORM}" "${_EXT}")
_sora_fetch_archive(boost "${_BOOST_URL}" "${_STAMPS_ROOT}/boost" "${_PLATFORM_ROOT}/boost" ${_BOOST_STRIP} "${_EXT}")
```

- `_sora_fetch_openh264` 呼び出しを `if(NOT WIN32)` で囲み Windows では skip する。 呼び出し箇所に「Windows では `CMakeLists.txt:211-217` の通り OpenH264 動的呼び出しを無効にしているため skip」とコメントする
- `_sora_fetch_openh264` 関数コメントに「Windows では使用しない（`CMakeLists.txt` で OpenH264 動的呼び出しを無効にしているため）」と明記する
- `_sora_fetch_llvm` 呼び出しを `if(NOT WIN32)` で囲み Windows では skip する。 呼び出し箇所に「Windows では MSVC を使用するため LLVM 取得は不要」とコメントする
- `_LLVM_HOST_KEY` 定義を `if(NOT WIN32)` ブロックに移動する
- `_LLVM_ROOT` / `_LLVM_STAMPS_ROOT` 用ディレクトリ作成を `if(NOT WIN32)` で囲む
- `OPENH264_DIR` / `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` / `_SORA_CLANG_DIR` の CACHE 確定を `if(NOT WIN32)` で囲む
- 末尾の `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` 確定を `if(NOT WIN32)` で囲む
- 許容 `SORA_PYTHON_SDK_PLATFORM` リストに `windows_x86_64` を追加する

0016 から存在する `cmake_parse_arguments(_arg "" "SHA256" "" ${ARGN})` は `ext` 追加後も末尾に維持し、 0021 では `_arg_SHA256` に値を渡さない。 0022 では `ext` 引数の後ろに `SHA256 "<hash>"` を渡す。

### deps.json

webrtc / sora_cpp_sdk / boost 全 entry の `url_template` に `{ext}` プレースホルダを追加する。

### pyproject.toml

`[tool.scikit-build.metadata.version]` 直後、`[tool.pytest.ini_options]` 直前の macOS override の直後に Windows override を追加する。 `CMakeLists.txt` では `set(SORA_GEN_PYI ON CACHE BOOL "Generate .pyi stub")`（FORCE なし）なので、 scikit-build-core からの `-DSORA_GEN_PYI=OFF` で cache 初期値が上書きされる。

### CMakeLists.txt

- 既存 `:192-208` の Windows ブランチは変更不要
- 既存 `:211-217` の OpenH264 ガードは変更不要
- `install(TARGETS sora_sdk_ext ...)` を以下のように変更する。 Windows では `.pyd` は CMake 的に `RUNTIME` 扱いとなるため `RUNTIME DESTINATION` も指定する。 Linux / macOS では `.so` / `.dylib` は `LIBRARY` 扱いなので `RUNTIME DESTINATION` の追加は影響しない:

```cmake
install(TARGETS sora_sdk_ext
  LIBRARY DESTINATION sora_sdk
  RUNTIME DESTINATION sora_sdk
)
```

### .github/workflows/build.yml

- `jobs.build_windows.if: false` を削除する
- `jobs.build_windows.needs: [build_pyi]` を完全削除する
- `actions/download-artifact` / `cp` ステップを一括して削除する
- `uv sync` を `uv sync --no-install-project` に変更する
- `uv run python run.py build windows_x86_64` 行を削除し、 `uv build` を `uv build --wheel` に変更する
- matrix から `target: windows_x86_64` キーを削除する
- `timeout-minutes` を 60 に変更する
- Ninja + MSVC ビルドを行うため、 `uv build --wheel` より前に `ilammy/msvc-dev-cmd` step を追加し amd64 開発者環境を有効化する
- `jobs.slack_notify.needs` を `[build_ubuntu, build_macos]` から `[build_ubuntu, build_macos, build_windows]` に戻す

変更後の `build_windows` job 概略:

```yaml
  build_windows:
    strategy:
      fail-fast: false
      matrix:
        platform:
          - name: windows-2025_x86_64
            runs_on: windows-2025
        python_version:
          - "3.12"
          - "3.13"
          - "3.14"
    runs-on: ${{ matrix.platform.runs_on }}
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
      - uses: astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b # v8.1.0
        with:
          enable-cache: false
          python-version: ${{ matrix.python_version }}
      # Ninja + MSVC ビルドを行うため、uv build --wheel 前に amd64 開発者環境を有効化する
      - uses: ilammy/msvc-dev-cmd@0b201ec74fa43914dc39ae48a89fd1d8cb592756 # v1.13.0
        with:
          arch: amd64
      - run: uv sync --no-install-project
      - run: uv build --wheel
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: ${{ matrix.platform.name }}_python-${{ matrix.python_version }}
          path: "dist/"
```

### CHANGES.md

`## develop` セクション内の最新の `[CHANGE]` エントリの直後に追加:

```
- [CHANGE] Windows x86_64 向け wheel のビルドを scikit-build-core 経路で復活させる
  - @voluntas
```

## ロールバック

0021 マージ後に Windows build で問題が発覚した場合:

1. `git revert -m 1 <merge-commit>` で revert PR を作成
2. revert 後、 `build_windows` job が再び `if: false` に戻り skip されることを確認
3. `pyproject.toml` の Windows override が消えるか確認
4. forward fix を選ぶ判断: OpenH264 / アーカイブ拡張子の単一不具合なら追加コミットで対応する
