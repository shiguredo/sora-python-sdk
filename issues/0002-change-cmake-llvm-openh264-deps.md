# fetch_deps.cmake の macOS native 拡張（libwebrtc clang 取得追加）

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-cmake-llvm-openh264-deps

## 目的

0001 で新設した `cmake/scripts/fetch_deps.cmake` を macOS arm64 ネイティブビルドで動かす最小拡張を行う。具体的には次の 3 点:

- libwebrtc 同梱 clang バイナリの取得を `_sora_fetch_llvm` に追加する（macOS arm64 は `clang_19` ではなく libwebrtc 同梱の clang / libc++ でビルドする必要があるため）
- `SORA_PYTHON_SDK_PLATFORM` 自動検出の macOS ホスト分岐を追加する
- 0001 既存呼び出し側を新シグネチャに合わせて書き換える（後方互換性は維持しない）

Windows native は対象外。Windows native のビルドは MSVC + Windows SDK 同梱の標準ライブラリで完結しており、libwebrtc 同梱 clang も OpenH264 ヘッダも不要（既存 `CMakeLists.txt` L174-190 が MSVC 静的ランタイム前提、L192-199 で Windows 以外のみ OpenH264 ヘッダ参照）。`buildbase.py:1637-1647` の Windows OpenH264 手動コピーは現状 `run.py:164-173` の `platform.build.os != "windows"` ガードで呼ばれていないデッドコードであり、本 issue では移植しない。Windows native 対応は 0005 で扱う。

ubuntu armv8 / jetson / RPi クロスコンパイル（0003 / 0004）も対象外。クロス時の libwebrtc clang は host = Linux x86_64 用バイナリを使うため、本 issue の macOS 向け clang 取得とは host_key が異なる別キャッシュになる。

## 優先度根拠

High。0005（macOS / Windows ネイティブビルド完結）の前提となるため。0002 完了がなければ 0005 で `fetch_deps.cmake` を呼んでも macOS 用 clang が取れず、CMakeLists.txt の `-isystem${LIBCXX_INCLUDE_DIR}` / `CMAKE_C_COMPILER` 設定が解決できない。

## スコープ

含む:

- `_sora_fetch_llvm` の関数シグネチャを `_sora_fetch_llvm(webrtc_install_dir dest stamp_path fetch_clang)` に拡張し、`fetch_clang=TRUE` のとき `clang/scripts/update.py` 経由で clang バイナリを取得する
- `cmake/scripts/fetch_deps.cmake` の `_sora_fetch_llvm` 既存呼び出し（0001 で `fetch_clang` 引数なし）を新シグネチャに書き換える。ubuntu native は `FALSE`、macOS native は `TRUE` を渡す
- `SORA_PYTHON_SDK_PLATFORM` 自動検出に `CMAKE_HOST_SYSTEM_NAME = Darwin` の分岐を追加し、`macos_${arch}` を組み立てる
- 出力契約 cache 変数に `CLANG_DIR` を追加する（命名は 0001 の `SORA_DIR` / `Boost_ROOT` 等と揃え `SORA_DEP_` prefix を付けない。既存 `CMakeLists.txt` 側 cache 変数を直接上書きする方針を継承）
- `LLVM_HOST_KEY` の組み立てを `Darwin` 対応に拡張する
- `_sora_fetch_llvm` stamp 形式変更による 1 回限りの強制再 fetch を 0001 → 0002 切替時の移行コストとして許容する

含まない（別 issue で扱う）:

- Windows native の `fetch_deps.cmake` 拡張（不要であることが確定したため。Windows native ビルドの諸対応は 0005）
- macOS native の `CMakeLists.txt` 反映（`CMAKE_C_COMPILER = ${CLANG_DIR}/bin/clang` 設定や `BUILD_PROFILE` 別 SDK 指定は 0005）
- CI の `build_macos` job 再有効化（0005）
- ローカル dev 用 CMake option `SORA_LOCAL_WEBRTC_BUILD_DIR` 等（0005）
- macOS native での `uv build --wheel` 実 wheel 生成と pytest 検証（0005）
- ubuntu armv8 / jetson / RPi 向けの `fetch_clang=TRUE` 呼び出し（0003 / 0004）
- OpenH264 取得経路の変更（0001 の `_sora_fetch_openh264` を macOS でもそのまま使う。macOS には `xcode-select --install` 経由で `make` が入る前提で、ubuntu と同じ `make install-headers` 経路で動く）

## 依存 issue への影響（事実記述。各 issue 自身の polish で対応）

- 0005 polish 時に `CHANGES.md` への `[CHANGE]` 追記（macOS / Windows native ビルド対応）を解決方法に含める必要がある。本 issue は依存層の拡張のみで CHANGES.md への単独エントリは作らない
- 0003 / 0004 のクロスコンパイル issue 側で `fetch_clang=TRUE` を呼ぶ前提となる
- 0005 で `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` を `${CLANG_DIR}/bin/clang` / `clang++` に設定する処理を追加するため、`if(CLANG_DIR)` ガードで ubuntu native（`CLANG_DIR` が空）と macOS native（`CLANG_DIR` セット済）を分岐する設計を 0005 polish で確定する必要がある

## 現状

- 0001 完了時点で `cmake/scripts/fetch_deps.cmake` には次の関数が存在する:
  - `_sora_fetch_archive(name url stamp_path dest_dir strip)`: アーカイブ取得 + tar xzf + stamp（`.tar.gz` 固定）
  - `_sora_git_shallow(url ref dest)`: git shallow clone
  - `_sora_fetch_openh264(version git_url dest)`: `make install-headers PREFIX=...` 経路（ubuntu / macOS で動く）
  - `_sora_fetch_llvm(webrtc_install_dir dest stamp_path)`: libcxx と buildtools の git shallow clone + `__config_site` / `__assertion_handler` コピー（clang バイナリ取得は含まない）
- 0001 出力契約 cache 変数（7 件、いずれも `SORA_DEP_` prefix なしで既存 CMakeLists.txt の cache 変数を直接上書き）: `SORA_DIR` / `Boost_ROOT` / `WEBRTC_INCLUDE_DIR` / `WEBRTC_LIBRARY_DIR` / `OPENH264_DIR` / `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR`
- 0001 の `SORA_PYTHON_SDK_PLATFORM` 自動検出は ubuntu のみ（`/etc/os-release` で `ID=ubuntu` チェック、それ以外は `FATAL_ERROR`）
- 0001 の `LLVM_HOST_KEY = ${CMAKE_HOST_SYSTEM_PROCESSOR}-Linux-${_SORA_UBUNTU_VERSION_ID}`（ubuntu のみ）
- 0001 の stamp 形式: `<LIBCXX_SRC_URL>.<LIBCXX_SRC_COMMIT>.<BUILDTOOLS_URL>.<BUILDTOOLS_COMMIT>` を `.` 区切り連結
- `buildbase.py:install_llvm` (L1187-1233) は次の手順で clang を取得する:
  - WebRTC `VERSIONS` から `WEBRTC_SRC_TOOLS_URL` / `WEBRTC_SRC_TOOLS_COMMIT` を取得
  - tools リポジトリを git shallow clone（`with cd("tools")` で cwd を tools に変更）
  - `python3 tools/clang/scripts/update.py --output-dir ${llvm_dir}/clang` を実行（cwd は tools リポジトリのルート）
  - clang バイナリは `${install_dir}/llvm/clang/bin/clang` に展開される（`buildbase.py:641` の `clang_dir`）
- `update.py` は Chromium 由来で、内部で Google Cloud Storage (`https://commondatastorage.googleapis.com/chromium-browser-clang/`) から clang バイナリを取得する。`update.py` 自身が `.last_update_*` 等の stamp を持つ
- `buildbase.py:get_macos_osver` (L2249-2250) は `return` 文を欠いたバグで常に `None` を返すが、`get_webrtc_platform` (L2456-2476) の macOS 分岐は `f"macos_{platform.target.arch}"` で osver を使わないため、結果として WebRTC アーカイブ命名規約 `webrtc.macos_arm64.tar.gz` と整合している
- macOS arm64 / Windows x86_64 用の Sora / Boost / WebRTC アーカイブ確認結果:
  - macOS arm64: すべて `.tar.gz`（`webrtc.macos_arm64.tar.gz` / `sora-cpp-sdk-..._macos_arm64.tar.gz` / `boost-..._macos_arm64.tar.gz`）
  - Windows x86_64: すべて `.zip`（本 issue では取得不要のため対応しない）

## 設計方針

### `_sora_fetch_llvm` への clang 取得追加

- シグネチャを 4 引数に拡張: `_sora_fetch_llvm(webrtc_install_dir dest stamp_path fetch_clang)`
- WebRTC `${webrtc_install_dir}/VERSIONS` から `WEBRTC_SRC_TOOLS_URL` / `WEBRTC_SRC_TOOLS_COMMIT` を `file(READ)` + `string(REGEX MATCH)` で抽出する。これは `fetch_clang` の値に関わらず常に行う（stamp に書く `tools=<URL>@<COMMIT>` を埋めるため）
- `fetch_clang=TRUE` のとき:
  - `_sora_git_shallow("${tools_url}" "${tools_commit}" "${dest}/tools")` で tools リポジトリ取得
  - `execute_process(COMMAND "${Python_EXECUTABLE}" "${dest}/tools/clang/scripts/update.py" --output-dir "${dest}/clang" WORKING_DIRECTORY "${dest}/tools" RESULT_VARIABLE _r)` で clang バイナリ取得（`WORKING_DIRECTORY` を tools に明示し、`buildbase.py:1203` の `with cd("tools")` 挙動と等価にする）
  - `_r` が 0 以外なら `message(FATAL_ERROR "Failed to fetch libwebrtc clang via clang/scripts/update.py; check network and Python environment")` で停止
  - 取得後 `${dest}/clang/bin/clang` の存在を `if(NOT EXISTS ...)` でガードチェック（`update.py` が正常終了しても出力先がずれるケースを fail fast で検知）
- `fetch_clang=FALSE` のとき: 0001 の既存挙動（libcxx / buildtools のみ）。`${dest}/clang/` は作成・削除しない（既存ディレクトリがあっても放置）

### stamp 形式変更とその影響

- 新形式: `libcxx=<LIBCXX_SRC_URL>@<LIBCXX_SRC_COMMIT>|buildtools=<BUILDTOOLS_URL>@<BUILDTOOLS_COMMIT>|tools=<TOOLS_URL>@<TOOLS_COMMIT>|clang=<TRUE/FALSE>`（区切り文字を `|` にして URL 中の `.` との混同を避ける。stamp は CMake `file(WRITE)` で書き、比較は `file(READ)` + `STREQUAL` で行う。シェル経由のパース・展開は一切行わない）
- `fetch_clang=FALSE` のときも `tools=<実 URL>@<実 commit>|clang=FALSE` を書く（後で `fetch_clang=TRUE` に切り替えたとき stamp 不一致で再 fetch されるため、`tools` 値は実値が必要）
- 0001 → 0002 切替時に既存 stamp（旧形式）は必ず不一致になり、ubuntu native でも libcxx / buildtools が 1 回だけ再 clone される。これは regression ではなく新 stamp 形式への 1 回限りの移行コストであり、2 回目以降は stamp ヒットで再 fetch されない。完了条件にもこの 1 回再 fetch を明示する

### `SORA_PYTHON_SDK_PLATFORM` 自動検出の macOS 対応

- `CMAKE_HOST_SYSTEM_NAME` で分岐:
  - `Linux`: 0001 の既存ロジック維持（`/etc/os-release` で `ID=ubuntu` のみ受け入れ）
  - `Darwin`: `CMAKE_HOST_SYSTEM_PROCESSOR`（macOS arm64 ホストでは `arm64`、Intel mac では `x86_64`）から arch 取得。組み立て `macos_${arch}`。macOS バージョンは含めない（既存 WebRTC アーカイブ命名規約 `webrtc.macos_arm64.tar.gz` と整合させるため。`get_macos_osver` バグの結果論的副作用と一致しているが、根拠は命名規約側にある）
  - その他（`Windows` 等）: `FATAL_ERROR("scikit-build-core migration phase 2 supports ubuntu-24.04_x86_64 and macos_arm64 / macos_x86_64; got '${CMAKE_HOST_SYSTEM_NAME}'")`
- `_SORA_UBUNTU_VERSION_ID` は Linux ホストのみ算出。macOS では空文字に設定（または unset）
- `LLVM_HOST_KEY` の組み立てを OS 分岐:
  - `Linux`: `${CMAKE_HOST_SYSTEM_PROCESSOR}-Linux-${_SORA_UBUNTU_VERSION_ID}`（0001 維持）
  - `Darwin`: `${CMAKE_HOST_SYSTEM_PROCESSOR}-Darwin`。macOS バージョンを含めない（libwebrtc 同梱 clang は macOS 13〜15 で動作する Chromium ビルドで、SDK バージョン差は wheel 側 `_PYTHON_HOST_PLATFORM` で吸収される。`_deps/llvm/arm64-Darwin/` を macos-14 / macos-15 で共用しても問題にならないことを 0005 PR で確認する）

### 出力契約への `CLANG_DIR` 追加

- 0001 の出力契約 7 変数は `SORA_DEP_` prefix を付けず既存 `CMakeLists.txt` cache 変数を直接 `set(... CACHE PATH "" FORCE)` で上書きする方針。`CLANG_DIR` も同方針で扱う:
  - `fetch_clang=TRUE` のとき: `set(CLANG_DIR "${DEPS_ROOT}/llvm/${LLVM_HOST_KEY}/clang" CACHE PATH "" FORCE)`
  - `fetch_clang=FALSE` のとき: `unset(CLANG_DIR CACHE)`（cache から削除）。ubuntu native のクリーンビルドでは no-op だが、「ubuntu native ホストで一度 macOS スコープを試した後 `CLANG_DIR` cache が残り、その後 ubuntu native に戻したケース」の safety net として `unset` を明示する。0005 で `if(CLANG_DIR)` ガードを使うことで ubuntu native ではシステムコンパイラを使う分岐を成立させる
- 既存 `CMakeLists.txt` 内に `CLANG_DIR` cache 宣言は存在しないため、`fetch_deps.cmake` 内で新規 cache 宣言として書き込む（命名衝突なし。`buildbase.py:get_webrtc_info:641` の Python 側 `clang_dir` 変数とは別名前空間で問題なし）

### 0001 既存呼び出しの書き換え

- 0001 完了時の `fetch_deps.cmake` 末尾には `_sora_fetch_llvm(${WEBRTC_INSTALL_DIR} ${LLVM_DEST} ${LLVM_STAMP})` 相当の 3 引数呼び出しがある（0001 解決方法のスケルトン）
- 関数本体を 4 引数版に書き換えても、呼び出し順序（WebRTC アーカイブ展開で `${WEBRTC_INSTALL_DIR}/VERSIONS` が生成される → `_sora_fetch_llvm` が `VERSIONS` を読む）は 0001 と不変。他のヘルパ関数（`_sora_fetch_archive` / `_sora_git_shallow` / `_sora_fetch_openh264`）への呼び出しタイミングと依存順も変更しない
- 本 issue で次のように書き換える:

  ```cmake
  if(SORA_PYTHON_SDK_PLATFORM MATCHES "^ubuntu-")
    set(_fetch_clang FALSE)
  else()
    set(_fetch_clang TRUE)
  endif()
  _sora_fetch_llvm("${WEBRTC_INSTALL_DIR}" "${LLVM_DEST}" "${LLVM_STAMP}" ${_fetch_clang})
  ```

- `_sora_fetch_openh264` は 0001 と同じシグネチャ `(version git_url dest)` で macOS / ubuntu 両対応する（`make install-headers` を使う点が共通）。Windows 対応はしないためシグネチャ拡張なし
- メインスクリプト末尾の cache 変数上書きセクションに以下を追加:

  ```cmake
  if(_fetch_clang)
    set(CLANG_DIR "${DEPS_ROOT}/llvm/${LLVM_HOST_KEY}/clang" CACHE PATH "" FORCE)
  else()
    unset(CLANG_DIR CACHE)
  endif()
  ```

### `update.py` 失敗時のエラーハンドリングとネットワーク前提

- `update.py` は `https://commondatastorage.googleapis.com/chromium-browser-clang/` から clang バイナリを取得する。CI / 開発者環境に対する外部依存
- `execute_process` の `RESULT_VARIABLE` で失敗判定。`update.py` 自身がリトライしないため、CMake 側のリトライは行わず 1 回で fail fast する（ネットワーク不調時はユーザーが `_deps/llvm/${LLVM_HOST_KEY}/` を消して再 configure する運用）
- `.gclient` 不在で `target_os` 自動検出は空になる（クロスランタイム取得スキップ）。本 issue は wheel ビルド時の libwebrtc 利用のみが目的で、cross runtime は不要なため意図通り

## 完了条件

- `macos_arm64` ホスト（macos-15 GitHub Actions runner で検証）で `cmake -DPython_EXECUTABLE=$(which python3) -P cmake/scripts/_verify_fetch_deps.cmake` を実行すると以下が生成される:
  - `_deps/llvm/arm64-Darwin/clang/bin/clang`（ファイル存在 + 実行権限）
  - `_deps/llvm/arm64-Darwin/libcxx/include/__config_site`
  - `_deps/llvm/arm64-Darwin/libcxx/include/__assertion_handler`
  - `_deps/macos_arm64/openh264/include/wels/codec_api.h`（macOS の `xcode-select --install` 経由 `make` で `make install-headers PREFIX=` が成功し、`include/wels/` 配下にヘッダがコピーされたことを確認）
  - `_deps/macos_arm64/webrtc/include/...`、`_deps/macos_arm64/sora/share/cmake/...`、`_deps/macos_arm64/boost/include/...`
- `ubuntu-24.04_x86_64` ホストで 0001 経路を実行すると `_deps/llvm/x86_64-Linux-24.04/clang/` が **生成されない**（`fetch_clang=FALSE` で stamp `clang=FALSE`、`CLANG_DIR` cache 変数も unset）
- 0001 → 0002 切替時に `.stamps/llvm` 不一致で libcxx / buildtools が 1 回だけ再 clone され、2 回目以降の configure では stamp ヒットで再 fetch されない
- `cmake/scripts/_verify_fetch_deps.cmake` の skeleton（macOS 限定検証用。ubuntu native で誤って実行された場合の意味不明エラーを防ぐためホストガードを冒頭に置く）:

  ```cmake
  cmake_minimum_required(VERSION 3.19)
  # macOS 限定の検証スクリプト
  if(NOT CMAKE_HOST_SYSTEM_NAME STREQUAL "Darwin")
    message(FATAL_ERROR "_verify_fetch_deps.cmake is intended for macOS hosts only; got ${CMAKE_HOST_SYSTEM_NAME}")
  endif()
  # cmake -P スクリプトモード前提。Python_EXECUTABLE は外側から -D で渡せる
  if(NOT DEFINED Python_EXECUTABLE)
    find_program(Python_EXECUTABLE NAMES python3 python REQUIRED)
  endif()
  # cmake -P 実行時 CMAKE_CURRENT_SOURCE_DIR はスクリプト所在地 (cmake/scripts/) になる
  # PROJECT_ROOT をリポジトリルートに固定
  get_filename_component(PROJECT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
  set(DEPS_ROOT "${PROJECT_ROOT}/_deps")
  include("${CMAKE_CURRENT_LIST_DIR}/fetch_deps.cmake")
  # 取得後の必須パスを存在チェック（Boost_ROOT は CamelCase、CMake 変数名は大文字小文字を区別する）
  foreach(_p
      "${CLANG_DIR}/bin/clang"
      "${LIBCXX_INCLUDE_DIR}/__config_site"
      "${LIBCXX_INCLUDE_DIR}/__assertion_handler"
      "${OPENH264_DIR}/include/wels/codec_api.h"
      "${WEBRTC_INCLUDE_DIR}"
      "${SORA_DIR}/share/cmake"
      "${Boost_ROOT}/include")
    if(NOT EXISTS "${_p}")
      message(FATAL_ERROR "verify failed: missing ${_p}")
    endif()
    message(STATUS "verify ok: ${_p}")
  endforeach()
  ```

  `cmake -P` 単独実行で `find_package(Python)` が走らないため `Python_EXECUTABLE` を外部から `-D` で渡すか、scriptlet 内 `find_program(Python_EXECUTABLE NAMES python3 python REQUIRED)` でフォールバックする
- 0002 PR では `.github/workflows/build.yml` の `build_macos` job 全体を `if: false` から戻す代わりに、本 issue 専用の `verify_macos_fetch_deps` job（`runs-on: macos-15`、`needs:` 無し）を追加し、`cmake -DPython_EXECUTABLE=$(which python3) -P cmake/scripts/_verify_fetch_deps.cmake` の 1 ステップだけを実行する。`build_macos` 全体の復活は 0005 の責務
- ホスト範囲: macOS arm64 のみ実機検証する。macOS x86_64（Intel mac）は `SORA_PYTHON_SDK_PLATFORM` 算出ロジックが分岐に対応するが、GitHub Actions の Intel mac runner（`macos-13`）が image 提供終了しつつあるため実機検証は行わない。将来 macOS x86_64 検証が必要になった場合は別 issue で扱う

## 解決方法

- `cmake/scripts/fetch_deps.cmake`
  - `_sora_fetch_llvm` のシグネチャを 4 引数 `(webrtc_install_dir dest stamp_path fetch_clang)` に変更
  - `fetch_clang=TRUE` 分岐に WebRTC `VERSIONS` から `WEBRTC_SRC_TOOLS_URL` / `WEBRTC_SRC_TOOLS_COMMIT` 抽出、`_sora_git_shallow` で tools 取得、`execute_process(... WORKING_DIRECTORY "${dest}/tools")` で `update.py` を呼ぶ処理を追加
  - 取得後 `if(NOT EXISTS "${dest}/clang/bin/clang") message(FATAL_ERROR "...") endif()` で出力チェック
  - stamp 形式を `libcxx=...@...|buildtools=...@...|tools=...@...|clang=<bool>` に変更
  - `SORA_PYTHON_SDK_PLATFORM` 自動検出を `CMAKE_HOST_SYSTEM_NAME` 分岐に拡張し `Darwin` 判定を追加
  - `LLVM_HOST_KEY` の組み立てを `Linux` / `Darwin` で分岐
  - メインスクリプト末尾の `_sora_fetch_llvm` 呼び出しを `if(...) set(_fetch_clang FALSE) else() set(_fetch_clang TRUE) endif()` + 4 引数呼び出しに書き換え
  - cache 変数上書きセクションに `if(_fetch_clang) set(CLANG_DIR ... CACHE PATH "" FORCE) else() unset(CLANG_DIR CACHE) endif()` を追加
- `CMakeLists.txt` の本 issue 範囲での変更は無し（macOS 向け compile options 変更や `CLANG_DIR` 参照は 0005）
- `tests/` への追加は無し（0001 の `pytest tests/test_version.py` で十分。本 issue は依存取得層の拡張のみ）
- `CHANGES.md` 単独エントリは追加しない。0005 polish 時に `[CHANGE] macOS / Windows 向けに scikit-build-core 経由のビルドを追加する` 相当のエントリを 0005 で書く方針が必要。本 issue PR では 0005 issue ファイルには触らない（CLAUDE.md「1 issue 1 ブランチ / 1 issue 1 コミット」原則に従う）。0005 polish 担当者は本 issue の「依存 issue への影響」セクションを参照し、CHANGES.md エントリ追加と `if(CLANG_DIR)` ガード設計を 0005 の解決方法に含めること
- 検証 CI: 0002 PR では `.github/workflows/build.yml` に `verify_macos_fetch_deps` job（`runs-on: macos-15`、`needs:` 無し、`uv run` も使わず `cmake -DPython_EXECUTABLE=$(which python3) -P cmake/scripts/_verify_fetch_deps.cmake` の 1 ステップのみ）を追加する。0001 で `build_macos` job 全体に追加した `if: false` は本 issue では戻さない（wheel build までは 0005 で復活させる）。本検証 job は 0005 で `build_macos` 復活時に削除する
