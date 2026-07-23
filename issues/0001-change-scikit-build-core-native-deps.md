# scikit-build-core 導入と ubuntu-24.04 x86_64 ネイティブビルド完結

- Priority: High
- Created: 2026-05-21
- Updated: 2026-07-17
- Completed: 2026-07-23
- Model: Fable 5
- Branch: feature/change-scikit-build-core-native-deps
- Polished: 2026-07-23

## 目的

build backend を `setuptools.build_meta` から `scikit_build_core.build` に切替え、 ubuntu-24.04 x86_64 host で `uv build --wheel` 一発で wheel を生成して install 後の最小 pytest が通る状態にする。 WebRTC / Sora C++ SDK / Boost / OpenH264 / LLVM (libwebrtc 同梱 clang + libcxx + libcxxabi ヘッダ) の取得は CMake configure 時取得 (`cmake/scripts/fetch_deps.cmake`) に移し、 レガシービルドスクリプト 5 ファイルは本 issue で削除する。 バージョン管理ファイルは既存の `DEPS` を維持する。

## 優先度根拠

- 後続 issue (0002 〜 0007) が本 issue の成果物 (`cmake/scripts/fetch_deps.cmake` / `_deps/` レイアウト / pyproject.toml の `[tool.scikit-build]` 設定構造) を前提に組まれている。
- 二段ビルド (`run.py build` → `uv build`) と `build_pyi` artifact 経路が CI 信頼性を下げている。
- 既存の `setup.py:bdist_wheel.get_tag` ハードコード platform tag や run.py の `importlib.metadata.version` による C++ マクロ注入はトラブル源で、 次の依存更新前に整理しておきたい。
- レガシースクリプトを移行期間中も残すと scikit-build-core 経路との二重メンテナンスが発生する。 run.py が無ければ動かない CI job を `if: false` で温存しても削除済みファイルへの壊れた参照が残るだけなので、 削除して後続 issue で新経路の job として作り直す方が差分が明確になる。

## スコープ

含む:

- `pyproject.toml` の build backend を `scikit_build_core.build` に切替える。
- `run.py` / `buildbase.py` / `pypath.py` / `setup.py` / `MANIFEST.in` を削除する。
- 旧 Jetson build の consumer と一緒に、到達不能になる Jetson 用 multistrap conf を削除する。
- レガシー build directory の `.gitignore` entry `/_install` / `/_source` / `/_package` を削除し、scikit-build-core が使う `/_build` と新しい `/_deps` だけを残す。
- `CMakeLists.txt` の更新と `cmake/scripts/fetch_deps.cmake` 新設。
- WebRTC / Sora / Boost / OpenH264 / LLVM を CMake configure 時に取得する。 バージョンは既存 `DEPS` から読む。
- `DEPS` から `CMAKE_VERSION` 行を削除する (cmake は scikit-build-core が `[tool.scikit-build.cmake] version` に基づき pip 経由で解決するため不要になる)。
- `src/sora.cpp` のバージョン注入を C 文字列リテラル方式に書き直す（付随して `BOOST_PP_STRINGIZE` と dead include を除去する。 詳細は「設計方針 → バージョン注入と src/sora.cpp」）。
- 素の `uv sync` / `uv run` を実行している開発ツール (canary.py / prek.toml / scripts/) を `--no-install-project` / `--no-sync` 付きに調整する（理由は「設計方針 → 開発ツールの調整」）。
- ubuntu-24.04 x86_64 native で `uv build --wheel` 成功 + wheel install 後に `pytest tests/test_version.py` 完走 (CI にも同じ smoke テストを入れる)。
- CI 再構成 (詳細は「設計方針 → wheel と CI」): build.yml の縮小 / build-debug.yml の削除 / e2e-test.yml の全 job 一時停止 / create-release 専用 composite action の削除。

含まない（別 issue で扱う）:

- macOS arm64（0002）/ Linux arm64 cross（0003 Ubuntu armv8、0004 Raspberry Pi OS、0043 Jetson）/ Windows（0005）。
- `ubuntu-22.04_x86_64` のビルド・配布。 matrix 縮小により本 issue で停止する。 x86_64 Linux wheel の glibc ベースラインが 2.31 (22.04) から 2.39 (24.04) に上がるため、22.04 向け配布を継続するかどうかは 0066 の publish / release artifact 再構築で確定する。
- build-debug.yml 相当のローカル webrtc-build / sora-cpp-sdk ビルド経路（0006）。
- cross wheel への型情報同梱（0003 / 0004）。
- sdist 専用 build / publish（0051）、`auditwheel repair`（0052）、publish 対象と release artifact 集約（0066）、E2E 復活と release gate（0067）。
- 依存 archive の SHA-256 検証（0070）、dependency cache（0071）。
- Makefile (0007)。 `run.py format` の代替は当面 prek (ruff-format / clang-format hook 設定済み) で足りる。
- pytest E2E マーカー再設計（issue 未作成）。
- `BUILD_PROFILE=debug` 時のバージョン文字列への `+debug` 連結。 技術的には scikit-build-core の `metadata.regex` の `result` テンプレートと `[[tool.scikit-build.overrides]]` の `if.env` で dist-info に載せることは可能だが、 C++ マクロ (User-Agent) / `__version__` / dist-info の三者一致を単純に保つため導入しない。 文字列レベルの debug 区別が必要なら 0006 の debug ビルド経路再設計と合わせて検討する。

## 現状

- build backend は `setuptools.build_meta`。 `uv run python run.py build <target>` が `_install/<target>/` に deps を取得し cmake を手動実行して `.so` を `src/sora_sdk/` にコピー、 後段 `uv build` が `setup.py:bdist_wheel.get_tag()` でハードコード platform tag (`manylinux_2_35_x86_64` 等) を付ける二段構成。
- `buildbase.py` (2514 行) は run.py と setup.py だけが import しており、 `pypath.py` は run.py だけが import している。 `MANIFEST.in` はレガシースクリプト 3 ファイルと `VERSION` の計 4 行を sdist に同梱するために存在する。
- `DEPS` は `SORA_CPP_SDK_VERSION` / `WEBRTC_BUILD_VERSION` / `BOOST_VERSION` / `CMAKE_VERSION` / `OPENH264_VERSION` の KEY=value 形式。 読み手は run.py (`read_version_file`) と build-debug.yml (`source DEPS`) のみ。
- `canary.py:49` が素の `uv sync` を、 `prek.toml:36` の ty-check フックが素の `uv run ty check` を、 `scripts/pytest_memory_leak_checker.py:26` と `scripts/pytest_with_llvm.py:13` が素の `uv run pytest` を実行している。
- `build_pyi` job が ubuntu-24.04 x86_64 で `.pyi` / `py.typed` を生成し artifact 化、 各 platform job が download / cp する経路。
- `CMakeLists.txt:54-59` の CACHE は 6 個。 `OPENH264_DIR` / `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` / `SORA_PYTHON_SDK_VERSION` / `SORA_GEN_PYI` は run.py 経由の `-D` 注入で自動 CACHE 化。
- `src/sora.cpp:246, :253` が `BOOST_PP_STRINGIZE` を使い、 マクロは `src/sora.cpp:7-8` の `// Boost` コメント + `#include <boost/preprocessor/stringize.hpp>` で明示 include されている。
- `.github/workflows/build-debug.yml` は run.py の `--local-webrtc-build-dir` / `--local-sora-cpp-sdk-dir` を使い、 webrtc-build / sora-cpp-sdk をソースからビルドする唯一の経路。
- `.github/workflows/e2e-test.yml` の実トリガは `workflow_dispatch` / `workflow_call` / `push` (schedule は 12032d2 でコメントアウト済み)。 `workflow_call` の呼び出し元は本 issue で削除する build.yml の `e2e_test` job。
- `.github/actions/` のうち `download` は create-release 専用、 `download-whl` は e2e-test.yml が参照している。 `download-openh264` はローカル composite への参照がリポジトリ内に無い (e2e-test.yml は `shiguredo/github-actions` の remote 版を使用) が、 元から dead な残骸でありビルド移行とは無関係のため本 issue では触らない。
- pyproject の `[dependency-groups] dev` に `nanobind==2.13.0` が入っている（`src/` / `tests/` 内に `import nanobind` は無く、 ビルド時にしか使われない）。

## 設計方針

### レイアウト

| 既存（`run.py` 経路） | 本 issue 後（`uv build` 経路） |
| --- | --- |
| `_install/<target>/{webrtc,sora,boost,openh264}` | `_deps/<platform>/{webrtc,sora,boost,openh264}` |
| （アーカイブは `_source/<target>/` 配下） | `_deps/<platform>/.archives/<name>.tar.gz` （ダウンロード置き場） |
| （展開は `_source/` 内で実施） | `_deps/<platform>/.extract/<name>` （展開・git clone 用一時ディレクトリ。 `file(RENAME)` が同一ファイルシステム内でのみ動くため `_deps` 配下に置く） |
| `_install/<target>/*.version` | `_deps/<platform>/.stamps/<name>` （取得済み判定 stamp） |
| `_install/<target>/llvm/{clang,libcxx}` | `_deps/llvm/<host_key>/{clang,libcxx}` + `_deps/llvm/<host_key>/.stamps/llvm` |

`DEPS_ROOT = ${CMAKE_SOURCE_DIR}/_deps`。 `<platform>` は `SORA_PYTHON_SDK_PLATFORM` （本 issue では `ubuntu-24.04_x86_64` のみ）。 `<host_key>` は `${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}` （例 `x86_64-Linux`、 0002 で `arm64-Darwin`）。 Chromium 由来 clang バイナリは ubuntu バージョン違いで切替えないので host key に ubuntu バージョンを含めない。

### レガシーファイルの削除と移植元の参照

- 削除対象はスコープのレガシービルドスクリプト 5 ファイルと、旧 Jetson 用 multistrap conf 。 `canary.py` / `prek.toml` / `scripts/` は削除せず「開発ツールの調整」の変更のみ行う。
- 削除コミットの位置は「解決方法」のコミット順序に従う（実装が終わるまで削除しないため、実装中は `buildbase.py` の該当関数を移植元として直接参照できる）。移植元の関数と行番号は「参照（一次資料）」に列挙する。削除後に参照する場合は削除前 commit の git 履歴を参照する。
- build-debug.yml の `--local-webrtc-build-dir` / `--local-sora-cpp-sdk-dir` 相当の機能は本 issue で一旦失われる（再設計は 0006）。

### pyproject.toml

- `[build-system]` を `requires = ["scikit-build-core>=0.11,<0.12", "nanobind==2.13.0"]` / `build-backend = "scikit_build_core.build"` に置換する。本設計が依存する内部挙動（ wheel.packages コピー / wheel.exclude 全走査 / CMakeInit.txt 注入）を「参照（一次資料）」に記録する。
- `[dependency-groups] dev` から `nanobind==2.13.0` を削除する（ build-system 側へ移動。 `uv lock` で uv.lock を更新する）。
- `[tool.scikit-build]`: `minimum-version = "0.11.3"`（本設計が依存する `metadata.regex` / `build-dir` テンプレート / `wheel.packages` が揃っている版） / `build-dir = "_build/{wheel_tag}"`（Python ABI ごとに build-dir 分離し `CMakeCache.txt` の `Python_INCLUDE_DIR` キャッシュ干渉を防ぐ）。
- `[tool.scikit-build.cmake] version = ">=4.1,<5"`（ `cmake_minimum_required(VERSION 4.1)` と一致させる）/ `[tool.scikit-build.ninja] version = ">=1.13,<2"`。
- `[tool.scikit-build.cmake.define]`: `TARGET_OS = "ubuntu"` のみ。 fetch スクリプトの include は `CMakeLists.txt` 側で行う（後述）。
- `[tool.scikit-build.wheel] packages = ["src/sora_sdk"]` のみ。 **`wheel.exclude` は使わない**。 `wheel.exclude` は wheel build dir 全体走査でも評価されるため `*.so` 等の平坦パターンは CMake install 出力まで除外してしまう。 ローカル `src/sora_sdk/sora_sdk_ext.*.so` の混入は `.gitignore`（既に `src/sora_sdk/*.so` 等を含む）と、 packages コピー時の `target_path.is_file()` skip ガードで防ぐ。
- `install-dir` は明示せず空文字デフォルト。 CMake `install(... DESTINATION sora_sdk)` と `wheel.packages` 由来コピーが `site-packages/sora_sdk/` で同居する。
- `[tool.scikit-build.metadata.version]`: `provider = "scikit_build_core.metadata.regex"` / `input = "VERSION"` / `regex = "(?P<value>\\S+)"`。
- ビルドは常に `uv build --wheel` を使う。 フラグ無しの `uv build` は sdist を作ってそこから wheel をビルドするため、 sdist 未設計の本 issue 段階では使わない。

### DEPS

- 依存バージョンの単一情報源として既存 `DEPS` (KEY=value 形式) を維持する（旧計画の deps.json 新設は廃止）。 fetch_deps.cmake が `file(READ)` + 行分割 + `MATCHES` で直接パースする。 `KEY=value` / `KEY="value"` 両形式（クォート除去込み）を扱えるパーサにし、 後述の webrtc `VERSIONS` パーサ・ `/etc/os-release` パーサと共通化する。 shell から `source DEPS` できる形式が保たれるため、 0006 で build-debug 相当を再構築する際もそのまま使える。
- `CMAKE_VERSION` 行は削除する。 残すキーは `SORA_CPP_SDK_VERSION` / `WEBRTC_BUILD_VERSION` / `BOOST_VERSION` / `OPENH264_VERSION` の 4 つ。
- ダウンロード URL は fetch_deps.cmake 冒頭で次のパターンで組み立てる（移植元 buildbase.py の URL と同一。 URL 中の platform 部は 3 つとも `SORA_PYTHON_SDK_PLATFORM` をそのまま使う。 旧 buildbase の `get_webrtc_platform` / `package_name` は ubuntu では同値）:
  - webrtc: `https://github.com/shiguredo-webrtc-build/webrtc-build/releases/download/${WEBRTC_BUILD_VERSION}/webrtc.${SORA_PYTHON_SDK_PLATFORM}.tar.gz`
  - sora: `https://github.com/shiguredo/sora-cpp-sdk/releases/download/${SORA_CPP_SDK_VERSION}/sora-cpp-sdk-${SORA_CPP_SDK_VERSION}_${SORA_PYTHON_SDK_PLATFORM}.tar.gz`
  - boost: `https://github.com/shiguredo/sora-cpp-sdk/releases/download/${SORA_CPP_SDK_VERSION}/boost-${BOOST_VERSION}_sora-cpp-sdk-${SORA_CPP_SDK_VERSION}_${SORA_PYTHON_SDK_PLATFORM}.tar.gz`
  - openh264: git リポジトリ `https://github.com/cisco/openh264.git` の ref `${OPENH264_VERSION}` （ DEPS の値は `v2.6.0` のように v プレフィックス込みなのでそのまま使う）
- 実装時に `curl -sL <url> | tar tzf - | head -5` で URL の実在と、 展開後に `dest_dir` 直下へ `include` / `lib` 等が来る想定レイアウトを確認する。
- `.zip` 拡張子対応は 0005 で扱う。

### fetch_deps.cmake の include 経路

`cmake/scripts/fetch_deps.cmake` を新設し、 `CMakeLists.txt` の `project()` 命令の **直前** に次を書く:

```cmake
list(APPEND CMAKE_PROJECT_TOP_LEVEL_INCLUDES "${CMAKE_CURRENT_LIST_DIR}/cmake/scripts/fetch_deps.cmake")
```

CMake 3.24+ の公式機能で、 最初の `project()` の中（言語有効化前）に実行される。 `${CMAKE_CURRENT_LIST_DIR}` で絶対パス化されるため scikit-build-core の build-dir に依存しない。 `pyproject.toml` から `CMAKE_PROJECT_TOP_LEVEL_INCLUDES` は渡さない（相対パス解決の保証が無いため）。

公式ドキュメントは toolchain 詳細の指定には `CMAKE_TOOLCHAIN_FILE` を推奨しているが、 コンパイラパス（ libwebrtc 同梱 clang ）は依存取得が終わるまで確定しないため、 本設計では取得完了後に cache 変数を FORCE 設定する方式を採る。 toolchain file は 0003 のクロスコンパイル設定で導入する。

### fetch_deps.cmake の入出力契約

入力（呼び出し前に確定済み）:

- `Python_EXECUTABLE`: scikit-build-core が `_build/{wheel_tag}/CMakeInit.txt` 経由 (`CACHE PATH "" FORCE`) で `Python_EXECUTABLE` / `PYTHON_EXECUTABLE` / `Python3_EXECUTABLE` を注入してくる（ 0.11.3 時点では無条件注入）。 fetch_deps.cmake 冒頭で `if(NOT Python_EXECUTABLE) message(FATAL_ERROR ...) endif()` でガードする。
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

各値は現行 run.py が `-D` 注入している値と同一（ `LIBCXXABI_INCLUDE_DIR` の webrtc アーカイブ内パスを含む）。 `_SORA_CLANG_DIR` は 0002 (macOS native) と 0003 / 0004 (cross はホスト側 clang を流用) が参照する想定で 0001 から出力契約に含める（ 0005 の Windows は MSVC を使うため参照しない）。

`CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` は LLVM fetch 完了後に `_SORA_CLANG_DIR/bin/clang(++)` を期待値とし、 `if(NOT CMAKE_C_COMPILER STREQUAL "<expected>")` ガード付きで `set(... CACHE FILEPATH "" FORCE)` する（既に期待値なら再設定しない冪等化）。

### fetch_deps.cmake のメインスクリプト

順序:

1. `Python_EXECUTABLE` の存在ガード。
2. `SORA_PYTHON_SDK_PLATFORM` 自動検出（未設定時のみ）+ 許容リスト検証（本 issue は `ubuntu-24.04_x86_64` のみ。 検証は明示指定時も含め **常に** 実行し、 バイパスは認めない）。
3. `${DEPS_ROOT}` を `file(MAKE_DIRECTORY)`、 `file(LOCK "${DEPS_ROOT}/.fetch.lock" GUARD PROCESS TIMEOUT 3600)` で排他取得（複数 Python ABI 並列ビルド時の `_deps/<platform>/` への同時書き込み回避。 CMake 3.2+ で提供。 process 終了で自動 release。 TIMEOUT は先行プロセスが LLVM の clang バイナリ取得込みでフル fetch する時間を待ち切れる値とし、 超過時は FATAL_ERROR で再実行を促す）。
4. `DEPS` を KEY=value としてパースし、 4 キーの存在を検証（欠けていたら FATAL_ERROR）。 依存ごとのダウンロード URL を組み立てる。
5. webrtc → sora → boost → openh264 → llvm の順に取得（LLVM が `webrtc/VERSIONS` を参照するため webrtc を先に確定させる）。 stamp / アーカイブ / 一時ディレクトリの置き場は「レイアウト」の表に従う。
6. 出力契約の表の 8 変数を CACHE FORCE 設定 + `CMAKE_C/CXX_COMPILER` をガード経由で FORCE 設定。

### 各取得関数（散文契約）

全関数に共通する契約: 外部コマンド (`git` / `make` / `update.py`) は `execute_process(... RESULT_VARIABLE ...)` （または `COMMAND_ERROR_IS_FATAL ANY` ）で失敗を検出し、 失敗時は部分成果物（ dest / 一時ディレクトリ）を削除して FATAL_ERROR する。 skip しないと判定した時点でまず旧 stamp を `file(REMOVE)` し（取得失敗時に旧 stamp が残って空の dest を指すのを防ぐ）、 stamp は **全手順の成功後にのみ** 書く。 stamp の親ディレクトリは事前に `file(MAKE_DIRECTORY)`。

- `_sora_fetch_archive(name url stamp_path dest_dir)` （末尾に `cmake_parse_arguments(_arg "" "SHA256" "" ${ARGN})` で `SHA256` キーワード引数の受け口を 0001 段階で用意する。 本 issue では値を渡さず、0070 で SHA-256 検証導入時に値が渡される）:
  - stamp 内容が `url` と一致したら skip。
  - `.archives/` 配下に `file(DOWNLOAD ... INACTIVITY_TIMEOUT 120 STATUS _status)` でダウンロード（転送が停止した場合のみタイムアウト。 全体 TIMEOUT は設けない）。 status code 0 以外なら部分ファイルを `file(REMOVE)` 、 1 秒スリープでリトライ、 3 回までで FATAL_ERROR。
  - 展開: `.extract/<name>` を REMOVE_RECURSE + MAKE_DIRECTORY してから `file(ARCHIVE_EXTRACT INPUT ... DESTINATION ...)` で展開する。 展開後、 `.extract/<name>` 直下を `file(GLOB)` し、 エントリが 1 個かつ `IS_DIRECTORY` ならそれを、 そうでなければ `.extract/<name>` 自体を `file(RENAME)` で `dest_dir` へ移動する（旧 `buildbase.py:353` の `extract()` と同じ動的判定。 `cmake -E tar` に `--strip-components` 相当は存在しないためこの方式を採る。 `file(ARCHIVE_EXTRACT)` は zip も扱えるため 0005 にもそのまま効く）。 `dest_dir` の親は事前に MAKE_DIRECTORY し、 成功時も残った一時ディレクトリを REMOVE_RECURSE する。
- `_sora_git_shallow(url ref dest)`: `dest` を REMOVE_RECURSE + MAKE_DIRECTORY 後、 `git init` → `git remote add origin` → `git fetch --depth=1 origin <ref>` → `git reset --hard FETCH_HEAD` を順に実行。 失敗したらリトライ前に `dest` を作り直し、 3 回失敗で FATAL_ERROR。 `git clone --depth 1 --branch <sha>` はサーバ側の `uploadpack.allowReachableSHA1InWant` 設定に依存して raw SHA を拒否されうるため使わない（ chromium.googlesource.com / GitHub とも設定依存）。
- `_sora_fetch_openh264(version git_url dest stamp_path)`: stamp が `version` と一致したら skip。 skip しない場合は `find_program(_SORA_MAKE_EXECUTABLE make NO_CACHE)` で make を解決し（不在なら `apt-get install build-essential` を促す FATAL_ERROR）、 `.extract/openh264` に `_sora_git_shallow` で clone して `make -C <src> install-headers PREFIX=<dest>` を実行、 src を削除して stamp を書く。
- `_sora_fetch_llvm(webrtc_install_dir dest_root stamp_path)`: `webrtc_install_dir/VERSIONS` から次の 6 キーを抽出する: `WEBRTC_SRC_TOOLS_URL`、 `WEBRTC_SRC_TOOLS_COMMIT`、 `WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL`、 `WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT`、 `WEBRTC_SRC_BUILDTOOLS_URL`、 `WEBRTC_SRC_BUILDTOOLS_COMMIT`。 VERSIONS は `KEY=value` / `KEY="value"` 両形式が混在するため、 `string(REPLACE "\n" ";")` でリスト化後 `foreach` + `MATCHES "^${_key}=\"?([^\"]+)\"?$"` で取り出す（ `DEPS` のパーサと共通化する）。 stamp は 6 値の連結。
  - skip しない場合は `dest_root/{clang,libcxx,buildtools,tools}` を REMOVE_RECURSE し、 `_sora_git_shallow` で tools / libcxx / buildtools を clone。
  - `${Python_EXECUTABLE}` で `${dest_root}/tools/clang/scripts/update.py --output-dir ${dest_root}/clang` を実行（`WORKING_DIRECTORY ${dest_root}/tools` を明示。 clang バイナリの取得は update.py 内部のダウンロードで行われるため、 失敗検出は共通契約に従う）。
  - `buildtools/third_party/libc++/__config_site` と `__assertion_handler` を `libcxx/include/` に `configure_file(... COPYONLY)` でコピー。
  - tools / buildtools を削除、 stamp を書く。

### SORA_PYTHON_SDK_PLATFORM の自動検出

手順 1〜3 は `SORA_PYTHON_SDK_PLATFORM` 未設定時のみ、 手順 4 は明示指定時も含め常に実行する:

1. `CMAKE_HOST_SYSTEM_NAME` が `Linux` でなければ FATAL_ERROR（0002 / 0005 で許容拡張）。
2. `/etc/os-release` を `file(READ)` し、 KEY=value パーサ（ `KEY="value"` のクォート除去込み。 `VERSIONS` / `DEPS` と共通）で `ID` / `VERSION_ID` を抽出（`lsb_release` には依存しない）。 `ID != ubuntu` なら FATAL_ERROR。
3. `set(SORA_PYTHON_SDK_PLATFORM "ubuntu-${VERSION_ID}_${CMAKE_HOST_SYSTEM_PROCESSOR}" CACHE STRING "" FORCE)` で確定。
4. 許容リスト（本 issue は `ubuntu-24.04_x86_64` のみ）に含まれなければ FATAL_ERROR（メインスクリプト手順 2 の「バイパスは認めない」を担保）。

### CMakeLists.txt の変更点

- 既存 `cmake_minimum_required` / `project(sora_sdk)` / `cmake_policy` / `find_package(Python)` の順序は変えない。
- `project(sora_sdk)` の直前に `list(APPEND CMAKE_PROJECT_TOP_LEVEL_INCLUDES "${CMAKE_CURRENT_LIST_DIR}/cmake/scripts/fetch_deps.cmake")` を追加。
- 既存 `:54-59` の CACHE 宣言 6 個に加えて、 `OPENH264_DIR` / `LIBCXX_INCLUDE_DIR` / `LIBCXXABI_INCLUDE_DIR` の CACHE PATH 宣言と、 `SORA_PYTHON_SDK_PLATFORM` の CACHE STRING 宣言を追加（`fetch_deps.cmake` から FORCE 設定される受け口）。
- `set(SORA_GEN_PYI ON CACHE BOOL "Generate .pyi stub")` を `set(TARGET_OS ...)` 直後に追加。 0003 / 0004 / 0005 は `build-dir = _build/{wheel_tag}` で fresh configure になるため `-DSORA_GEN_PYI=OFF` が後で渡されればそのまま反映される。
- `file(READ VERSION _RAW)` + `string(STRIP)` で `SORA_PYTHON_SDK_VERSION` を設定する処理を `target_compile_definitions` より前に追加する（ run.py の `-D` 注入の置き換え）。
- `target_compile_definitions(sora_sdk_ext PRIVATE SORA_PYTHON_SDK_VERSION=${SORA_PYTHON_SDK_VERSION})` （`:106`）を `target_compile_definitions(sora_sdk_ext PRIVATE SORA_PYTHON_SDK_VERSION="${SORA_PYTHON_SDK_VERSION}")` に変更（CMake 標準のイディオム。 外側クォート無し）。
- `install(TARGETS sora_sdk_ext LIBRARY DESTINATION .)` （`:196`）を `... DESTINATION sora_sdk` に変更。
- `install(FILES py.typed sora_sdk_ext.pyi DESTINATION ".")` （`:198`）を `install(FILES ${CMAKE_CURRENT_BINARY_DIR}/py.typed ${CMAKE_CURRENT_BINARY_DIR}/sora_sdk_ext.pyi DESTINATION sora_sdk)` に変更（既存 `nanobind_add_stub` (`:95-104`) は `OUTPUT_PATH` 未指定で `CMAKE_CURRENT_BINARY_DIR` 直下に書き出すため）。 `if (SORA_GEN_PYI)` ガードは維持。
- 既存 `:49-52` の `execute_process(COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir ...)` による nanobind 検出は変更不要。 build isolation 環境では build-system requires の `nanobind==2.13.0` が `Python_EXECUTABLE` の環境に入るため引き続き成立する（ dev group から nanobind を消してよい根拠）。 `uv build` を経由しない手動 cmake configure は venv に nanobind が無いため失敗するようになるが、 想定外経路として許容する。

### バージョン注入と src/sora.cpp

- `CMakeLists.txt` が `VERSION` ファイル直読みで `SORA_PYTHON_SDK_VERSION` を C 文字列リテラルとして渡す（「 CMakeLists.txt の変更点」参照）。
- `src/sora.cpp:246` を `"Mozilla 5.0 (Sora Python SDK/" SORA_PYTHON_SDK_VERSION ")"` に、 `:253` を `"Sora Python SDK " SORA_PYTHON_SDK_VERSION` に変更（ `BOOST_PP_STRINGIZE` を外すのみ。 文言は既に修正済み）。
- dead include になる `src/sora.cpp:7-8` （ `// Boost` コメントと `#include <boost/preprocessor/stringize.hpp>` ）の 2 行を削除する。
- run.py の `importlib.metadata.version` 経由のバージョン注入は run.py ごと削除する。 `sora-sdk-rpi` パッケージ名の切替は 0004 で扱う。

### 開発ツールの調整

backend 切替後、 素の `uv sync` / `uv run` は project 本体を scikit-build-core でビルドして venv に install する（ fetch_deps 込みのフルビルド。 macOS 開発機では platform 自動検出の FATAL_ERROR で即失敗する）。 さらに venv への project install は wheel 検証 (`uv pip install dist/*.whl` → `uv run --no-sync pytest`) を上書きして衝突する。 このため次の 4 箇所を調整する:

- `canary.py:49` の `subprocess.run(["uv", "sync"], ...)` を `["uv", "sync", "--no-install-project"]` に変更し、 `:46` の dry-run メッセージも追従させる。 他の処理（ commit / tag / push ）は変更しない（ 0062 と競合させない）。
- `prek.toml:36` の ty-check フックの entry を `uv run --no-sync ty check` に変更する。
- `scripts/pytest_memory_leak_checker.py:26` を `["uv", "run", "--no-sync", "pytest"]` に変更する。
- `scripts/pytest_with_llvm.py:13` の lldb 起動引数を `["run", "--no-sync", "pytest", ...]` に変更する。

canary.py の tag push は継続してよい。 `publish_wheel` / `create-release` job を本 issue で削除するため、 tag を push しても publish / release は発生しない（dev 版の PyPI 配布と GitHub Release は 0066 の再構築まで停止する。正式リリースも同様）。

### wheel と CI

- 生成 wheel の platform tag は `linux_x86_64`（scikit-build-core デフォルト）。 PyPI 公開不可のタグだが、 publish 系 job を削除するため問題にならない。
- `_PYTHON_HOST_PLATFORM` は native / cross のどちらでも使用しない。 cross wheel tag は 0003 / 0004 の `wheel.tags` override を単一情報源とする。
- ルート `.gitignore` に `/_deps` を追加する。`/_build` は scikit-build-core の build-dir として維持し、レガシー経路専用だった `/_install` / `/_source` / `/_package` は削除する。ignore entry の削除は開発者の local directory 自体を削除しない。

`.github/workflows/build.yml`:

- `get_sdk_version` job は触らない（未使用 job の削除は 0050 で扱う）。
- 次の job を削除する: `build_pyi` / `build_ubuntu_arm` / `build_macos` / `build_windows` / `e2e_test` / `publish_wheel` / `create-release`。0002 〜 0005、0066、0067 が責務ごとに新経路の job を新設する。
- `build_ubuntu` job:
  - matrix の `platform` を `ubuntu-24.04_x86_64` (runs_on: ubuntu-24.04) の 1 entry に、 `python_version` は 3.12 / 3.13 / 3.14 を維持。 `timeout-minutes: 15` は維持（取得物・ビルド量は旧経路と同じ）。
  - `needs: [build_pyi]` / `download-artifact` step / `cp sora_sdk/py.typed ...` step / `sora_sdk_rpi` sed step / multistrap install step / armv8 用 build step を削除。
  - steps を checkout → `sudo apt-get update && sudo apt-get -y install libx11-dev` → setup-uv → `uv sync --no-install-project` → `uv build --wheel` → `uv pip install dist/*.whl` → `uv run --no-sync pytest tests/test_version.py` → upload-artifact に再構成する。
  - upload-artifact の name は `${{ matrix.platform.name }}_python-${{ matrix.python_version }}` を維持する（0067 の E2E 復活で `download-whl` action が `{platform}_python-{version}` 命名を前提とするため）。
- workflow レベル env の `TEST_SIGNALING_URLS` / `TEST_CHANNEL_ID_PREFIX` / `TEST_SECRET_KEY` / `TEST_API_URL` / `OPENH264_VERSION` を削除する（ reusable workflow には env が継承されないため、 もともと build.yml 内に参照が無い dead env。 e2e-test.yml は自前の env を持っている）。
- `on.push.paths-ignore` から `.github/workflows/build-debug.yml` の行を削除する（ファイル削除に伴う dead 参照）。
- `slack_notify.needs` を `[build_ubuntu]` のみに変更。

`.github/workflows/build-debug.yml`: ファイルごと削除する。 run.py の `--local-webrtc-build-dir` / `--local-sora-cpp-sdk-dir` に全面依存しており、 run.py 削除後は成立しない。 再設計（ `-DSORA_DIR` / `-DWEBRTC_*` の手動指定等）は 0006。 それまでの debug build は `uv build --wheel -Ccmake.build-type=Debug` で行う。

`.github/actions/`: `download/` を削除する（ create-release 専用のため job 削除で未参照になる）。 `download-whl/` と `download-openh264/` は残す（参照状況は「現状」の通り）。

`.github/workflows/e2e-test.yml`: run.py 非依存のためファイルは残す。 `push` / `workflow_dispatch` トリガで独立に動くため、 配下の全 job を `if: false` にして一時停止する（ `e2e_test` job は `if: false` を追加、 `slack_notify` job は既存の `if: ${{ !cancelled() && inputs.from_build != true }}` を `if: false` に置換）。 `workflow_call` トリガと `from_build` input は呼び出し元 job の削除で dead になるが、0067 で復活させるため残置する。

## 完了条件

検証は `rm -rf _build dist` の状態から開始する（旧経路の残骸との混同を防ぐ）。

- ubuntu-24.04_x86_64 + Python 3.12 / 3.13 / 3.14 で `uv build --wheel` が成功する。 ローカルは Python バージョンごとに `rm -rf dist && uv build --wheel --python 3.X` を直列実行し、 `dist/` に複数 ABI の wheel を混在させない。
- 生成 wheel タグが `cp3XY-cp3XY-linux_x86_64`、 `python -m zipfile -l dist/*.whl` 出力に `sora_sdk/sora_sdk_ext.cpython-*-linux-gnu.so` / `sora_sdk/sora_sdk_ext.pyi` / `sora_sdk/py.typed` / Python ソースが含まれる。 dist-info の Version が `VERSION` ファイルと一致。
- `ls _deps/ubuntu-24.04_x86_64/webrtc/include/third_party/libc++abi/src/include/__cxxabi_config.h` が存在する。
- ローカル `src/sora_sdk/sora_sdk_ext.cpython-*-linux-gnu.so` を残したまま `uv build --wheel` しても、 wheel 内の `.so` は CMake install 由来のみ。
- `run.py` / `buildbase.py` / `pypath.py` / `setup.py` / `MANIFEST.in` が削除され、 build backend が `scikit_build_core.build` に切替わっている。
- `git grep -nE "run\.py|buildbase|pypath|setup\.py|MANIFEST\.in"` のヒットが `CHANGES.md` と `issues/` 配下のみ（ソースコード / CI / ドキュメントに残存参照が無い）。
- `git grep -nE "BOOST_PP_STRINGIZE|boost/preprocessor" src/` が 0 件。
- `DEPS` のキーが `SORA_CPP_SDK_VERSION` / `WEBRTC_BUILD_VERSION` / `BOOST_VERSION` / `OPENH264_VERSION` の 4 つのみ。
- `.github/actions/` 配下から `download/` が消えている（ `download-whl/` と `download-openh264/` は残る）。
- `.gitignore` に `/_install` / `/_source` / `/_package` が残らず、`/_build` / `/_deps` が存在する。
- pyproject.toml 内の `nanobind` の記述が `[build-system] requires` の 1 箇所のみ。
- `canary.py` の uv sync が `--no-install-project` 付き（ dry-run メッセージ含む）、 `prek.toml` の ty-check が `uv run --no-sync ty check`、 `scripts/` の 2 スクリプトの uv run が `--no-sync` 付きになっている。
- 動作確認（まっさらな ubuntu-24.04 では手順 0 の前提パッケージが必要）:
  0. `sudo apt-get -y install build-essential libx11-dev` （ make は OpenH264 ヘッダ取得、 libx11-dev は Sora C++ SDK のリンクに必要。 git は前提）
  1. `uv venv`
  2. `uv sync --no-install-project`（`--no-install-project` 必須。 理由は「設計方針 → 開発ツールの調整」）
  3. `uv build --wheel`
  4. `uv pip install --force-reinstall dist/*.whl`
  5. `uv run --no-sync pytest tests/test_version.py` 成功
  6. `uv run --no-sync python -c "from sora_sdk import sora_sdk_ext; print(sora_sdk_ext.__file__)"` で site-packages 配下の `.so` を出力
  7. `uv run --no-sync python -c "import sora_sdk; s = sora_sdk.Sora(); print(s)"` がインスタンス生成に成功
- 同じ Python ABI で 2 回目の `uv build --wheel` を実行すると `_deps/<platform>/.stamps/*` と `_deps/llvm/<host_key>/.stamps/llvm` の mtime が変化しない。
- CI: build.yml の job が `get_sdk_version` / `build_ubuntu` (ubuntu-24.04_x86_64 × 3 Python) / `slack_notify` のみで green。 build-debug.yml が存在しない。 e2e-test.yml の全 job が skip 表示。

## 解決方法

実装せず closed にする。

scikit-build-core 化を複数回試みたが難しく、方針としてあきらめることにした。
build backend の移行は行わず、現行の setuptools / `run.py` 経路を維持する。
sysroot 化は 0074 で現行経路向けに切り直す。

## ロールバック

revert は `fetch_deps.cmake` の根本設計（`CMAKE_PROJECT_TOP_LEVEL_INCLUDES` 経路 / `file(LOCK)` 設計 / wheel.packages と CMake install の同居挙動 / ABI ごと build-dir 分離）に起因する不具合で追加コミットでは修正できない場合に選ぶ。 個別関数や設定値レベル（リトライ条件 / VERSIONS 抽出 regex / stamp 一致判定 / `.gitignore` 追加項目）は revert ではなく追加コミットで前進させる。

手順: 本リポジトリは squash merge 運用のため merge commit は無い。 `git revert <squash-commit>` で revert PR を作成する。 revert により削除したレガシーファイル / CI job / build-debug.yml が復元されるので、 復元後に build.yml の全 job が green になることを CI で確認する。 `_deps/` キャッシュは残留しても無害。

## 関連 issue への影響

- 0002 〜 0007: 本 issue の再計画（レガシー削除の前倒し / deps.json 廃止 / CI job 削除方式 / 展開方式の `file(ARCHIVE_EXTRACT)` 化）は refresh で各 issue に反映済み。
- 前提が消滅する open issue: 0046（buildbase.py の `_extractzip`）/ 0060（buildbase.py の `get_macos_osver`）/ 0063（setup.py の osver fallback）/ 0068（`build_ubuntu_arm` job の扱い）。本 issue の実装を先に commit し、次の close commit で 4 issue を `issues/closed/` へ移動する。個別修正 branch は作成しない。0052 は setup.py 削除後の `auditwheel repair` 導入 issue として refresh して残す。
- 後続の責務: 0006（debug build）、0051（sdist）、0052（auditwheel）、0066（publish / release artifact）、0067（E2E / release gate）、0070（archive SHA-256）、0071（cache）。
- 読み替え・交差が必要な open issue: 0043（`run.py` の行参照を git 履歴へ読み替える）/ 0053（E2E matrix。0067 完了までは着手不可）/ 0054（`MANIFEST.in` の `include VERSION` 削除で sdist の VERSION 同梱手段が消えるため 0051 で引き継ぐ）/ 0062（`canary.py` の git flow。本 issue の変更は `uv sync` 引数と dry-run message のみに留める）。

## 参照（一次資料）

実装時に挙動の根拠が必要なら次を参照する。 scikit-build-core の行番号はバージョンで変動するためシンボル名で引くこと（挙動は実装時にインストールされる最新安定版で確認する）:

- `scikit_build_core/cmake.py` — `CMake.init_cache` の `CMakeInit.txt` 書き出し（`CACHE ... FORCE` 形式）と `-D` 引数構築。
- `scikit_build_core/builder/builder.py` — `Builder.configure` の `Python_EXECUTABLE` / `PYTHON_EXECUTABLE` / `Python3_EXECUTABLE` 注入。
- `scikit_build_core/build/_pathutil.py` — `packages_to_file_mapping` の `target_path.is_file()` skip ガード。
- `scikit_build_core/build/_wheelfile.py` — wheel build dir 全走査時の `wheel.exclude` 適用。
- `scikit_build_core/build/_file_processor.py` — `each_unignored_file` の `.gitignore` 評価。
- `nanobind/cmake/nanobind-config.cmake:643-767` (v2.13.0) — `nanobind_add_stub`。 `add_custom_command(OUTPUT ...)` は `:746`、 `WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}` は `:749`。
- `buildbase.py:353` (`extract`。 単一トップディレクトリ rename 方式の移植元) / `:562` (`install_webrtc`) / `:676` (`install_boost`) / `:999` (`install_sora`。 sora アーカイブ URL の組み立て実体) / `:1187` (`install_llvm`) / `:1630` (`install_openh264`) — 展開 / URL 組み立て / ヘッダコピーの移植元。 削除後は `git show <削除前コミット>:buildbase.py` で参照する。
