# macOS arm64 ネイティブビルド対応

- Priority: High
- Created: 2026-05-21
- Updated: 2026-07-16
- Model: Composer 2.5
- Branch: feature/change-macos-arm64-native-build

## 目的

0001 で ubuntu-24.04 x86_64 native 向けに実装する scikit-build-core + `cmake/scripts/fetch_deps.cmake` を macOS arm64 でも動作させ、 macOS host 上で `uv build --wheel` 一発で macOS arm64 用 wheel を生成できる状態にする。 0001 で `build_macos` job は build.yml から削除されるため、 scikit-build-core 経路の `build_macos` job を新設する。

## 設計の前提（プロジェクト全体の新方針からの該当部）

- ビルド環境は ubuntu-24.04 x86_64 host のみに集約するが、 **macOS (arm64) と Windows (x86_64) は例外的にそれぞれの OS で native build を維持する** （ cross-compile しない）
- macOS native は macOS arm64 runner で native build する
- clang は libwebrtc 同梱 clang バイナリを継続使用する（ 0001 で `_sora_fetch_llvm` が tools + libcxx + buildtools を取得して `clang/scripts/update.py` 経由で host 用 clang バイナリを `_SORA_CLANG_DIR` に展開する経路が実装される。 macOS host では host = `Darwin arm64` 用の clang バイナリが取得される）

## スコープ

含む:

- `cmake/scripts/fetch_deps.cmake` の `SORA_PYTHON_SDK_PLATFORM` 算出を macOS host 対応に拡張する（ `CMAKE_HOST_SYSTEM_NAME = Darwin` 分岐で `macos_${arch}` を組み立てる）
- `fetch_deps.cmake` の FATAL_ERROR ガードを `ubuntu-24.04_x86_64` / `macos_arm64` 両方を許容するように拡張する
- `fetch_deps.cmake` の URL 組み立てを macOS 用アーカイブ名（platform 文字列 `macos_arm64`）に対応させる
- `CMakeLists.txt` の `find_package(Python ...)` 周辺と `project()` 前後の処理を macOS でも問題なく動くか確認し、必要なら macOS 固有調整を加える
- `pyproject.toml` に `[[tool.scikit-build.overrides]]` で macOS の `TARGET_OS = "macos"` 上書きを追加する（ 0001 では `[tool.scikit-build.cmake.define] TARGET_OS = "ubuntu"` を直接設定したため、 macOS では override で `"macos"` に変える）
- macOS native での `uv build --wheel` 成功と `pytest tests/test_version.py` 完走（ wheel タグは `macosx_14_0_arm64` 等）
- `.github/workflows/build.yml` に scikit-build-core 経路の `build_macos` job を新設する（ 0001 で旧 job は削除済み。 `build_pyi` artifact 経路は使わない）
- `slack_notify` の `needs:` に `build_macos` を追加する

含まない（別 issue で扱う）:

- Linux arm64 cross-compile (ubuntu armv8) （ 0003 ）
- Linux arm64 cross-compile (jetson / rpi) （ 0004 ）
- Windows x86_64 native （ 0005 ）
- `publish_wheel` / `create-release` / e2e 復活等の CI 最終整理（ 0006 。 レガシーファイル削除は 0001 で完了済み）
- Makefile （ 0007 ）
- `build_macos` matrix の macOS バージョン拡充（旧 job と同じ `macos-15_arm64` / `macos-14_arm64` を維持する）
- macOS x86_64 native （プロジェクトでサポート対象外。 macOS arm64 のみ）

## 現状

- 0001 で `_SORA_CLANG_DIR = ${DEPS_ROOT}/llvm/<host_key>/clang` が `_sora_fetch_llvm` の戻り変数として確定する
- 0001 の `<host_key>` は `${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}` で ubuntu バージョンを含まないため、 macOS host では追加変更なしで `arm64-Darwin` になる（ LLVM 周りの 0002 側対応は不要）
- `CMakeLists.txt:111-123` の `if(TARGET_OS STREQUAL "macos")` ブランチで `CXX_VISIBILITY_PRESET hidden` を設定し、 `sora_sdk_ext` に `-nostdinc++ -isystem${LIBCXX_INCLUDE_DIR}` を、 `nanobind-static` にはさらに `-isystem${LIBCXXABI_INCLUDE_DIR}` を付ける既存実装がある（このまま使える）
- `BOOST_ASIO_DISABLE_STD_ATOMIC_WAIT` は sora-cpp-sdk 側で PUBLIC 定義されるようになったため CMakeLists.txt から削除済み（ 69ac472 ）。 Python SDK 側の対応は不要
- 0001 で削除される run.py （削除前 `run.py:319-331` ）は macOS arm64 native の `cmake_args` として `CMAKE_SYSTEM_PROCESSOR=arm64` / `CMAKE_OSX_ARCHITECTURES=arm64` / `CMAKE_*_COMPILER_TARGET=aarch64-apple-darwin` / `CMAKE_SYSROOT=$(xcrun --sdk macosx --show-sdk-path)` を渡していた。 削除後は git 履歴 (`git show <削除前コミット>:run.py`) で参照する
- 0001 で削除される旧 `build_macos` job （削除前 `build.yml:230-279` ）は `macos-15_arm64` / `macos-14_arm64` matrix で Python 3.12 / 3.13 / 3.14 を回し、 `uv run python run.py build macos_arm64` + `uv build` を実行する 2 段構成だった。 matrix 構成（ runner とラベル）は新設 job に引き継ぐ

## 設計方針

### SORA_PYTHON_SDK_PLATFORM 算出の macOS 対応

`fetch_deps.cmake` の platform 自動検出ロジック（ 0001 のメインスクリプト手順 2 ）に `CMAKE_HOST_SYSTEM_NAME` 分岐を追加する:

```cmake
if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux")
  # 既存 ubuntu 経路（0001 で実装される。 /etc/os-release から ID / VERSION_ID を抽出）
elseif(CMAKE_HOST_SYSTEM_NAME STREQUAL "Darwin")
  # 新規 macOS 経路
  if(CMAKE_HOST_SYSTEM_PROCESSOR STREQUAL "arm64")
    set(SORA_PYTHON_SDK_PLATFORM "macos_arm64" CACHE STRING "" FORCE)
  else()
    message(FATAL_ERROR
      "macOS host must be arm64; got '${CMAKE_HOST_SYSTEM_PROCESSOR}'. "
      "macOS x86_64 is not supported.")
  endif()
else()
  message(FATAL_ERROR "Unsupported host: ${CMAKE_HOST_SYSTEM_NAME}")
endif()
```

`SORA_PYTHON_SDK_PLATFORM` 許容リストは `ubuntu-24.04_x86_64` / `macos_arm64` の 2 つになる。 0003 で `ubuntu-22.04_x86_64` を host として許容するか判断する（クロス build に 24.04 host のみ使うなら追加不要）。

LLVM の `<host_key>` は 0001 の定義 `${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}` のままで macOS では `arm64-Darwin` になるため、 0002 での変更は不要。

### TARGET_OS の macOS 上書き

`pyproject.toml` に override を追加する:

```toml
[[tool.scikit-build.overrides]]
if.platform-system = "darwin"
cmake.define.TARGET_OS = "macos"
```

scikit-build-core の `if.platform-system` は `sys.platform` ベース。 `darwin` で macOS にマッチする。

これにより:

- ubuntu host: `TARGET_OS = "ubuntu"` （ 0001 のデフォルト）
- macOS host: override で `TARGET_OS = "macos"` に切替

`CMakeLists.txt:111-123` の `if(TARGET_OS STREQUAL "macos")` ブランチが有効化され、 `-nostdinc++ -isystem${LIBCXX_INCLUDE_DIR}` 等が付く。

### macOS 用 cmake.args の追加

旧 run.py （削除前 `run.py:319-331` 。 git 履歴参照）で渡していた macOS 固有引数を `pyproject.toml` の `[[tool.scikit-build.overrides]]` に移植する:

```toml
[[tool.scikit-build.overrides]]
if.platform-system = "darwin"
cmake.define.CMAKE_SYSTEM_PROCESSOR = "arm64"
cmake.define.CMAKE_OSX_ARCHITECTURES = "arm64"
cmake.define.CMAKE_C_COMPILER_TARGET = "aarch64-apple-darwin"
cmake.define.CMAKE_CXX_COMPILER_TARGET = "aarch64-apple-darwin"
```

`CMAKE_SYSROOT` は `xcrun --sdk macosx --show-sdk-path` 経由で動的に決まるため、 `CMakeLists.txt` 側で `if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Darwin" AND NOT CMAKE_SYSROOT)` ガードで `execute_process(COMMAND xcrun --sdk macosx --show-sdk-path OUTPUT_VARIABLE _macos_sysroot OUTPUT_STRIP_TRAILING_WHITESPACE)` + `set(CMAKE_SYSROOT "${_macos_sysroot}" CACHE PATH "" FORCE)` で設定する。 `fetch_deps.cmake` ではなく `CMakeLists.txt` の `project()` 後（ compiler 確定後）に置く。

`CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` は 0001 で `_SORA_CLANG_DIR/bin/clang(++)` に設定されるため、 macOS でも libwebrtc 同梱 clang が使われる。

### fetch_deps.cmake の URL 組み立ての macOS 対応

fetch_deps.cmake が `DEPS` の値から組み立てる各アーカイブ URL の platform 文字列に `macos_arm64` を対応させる。 アーカイブ名の例（バージョンは `DEPS` の現在値で組み立てる。 現時点では `WEBRTC_BUILD_VERSION=m150.7871.3.0` / `SORA_CPP_SDK_VERSION=2026.2.0-canary.22` / `BOOST_VERSION=1.91.0` ）:

- WebRTC: `webrtc.macos_arm64.tar.gz`
- Sora C++ SDK: `sora-cpp-sdk-2026.2.0-canary.22_macos_arm64.tar.gz`
- Boost: `boost-1.91.0_sora-cpp-sdk-2026.2.0-canary.22_macos_arm64.tar.gz`

0002 実装時に `curl -sL <url> | tar tzf - | head -5` で各 macOS アーカイブの実在と展開後レイアウトを確認する（ 0001 と同じ手順。 展開は `file(ARCHIVE_EXTRACT)` + 単一トップディレクトリの動的判定のため strip 数の確定は不要）。

### OpenH264 ヘッダ取得

macOS native では Xcode Command Line Tools 経由で `make` がインストール済みのため、 `_sora_fetch_openh264` の `find_program(_SORA_MAKE_EXECUTABLE make NO_CACHE)` がそのまま動く。 GitHub Actions macOS runner には `make` が pre-install 済み。 ローカル開発で `xcode-select --install` がされていない環境では FATAL_ERROR メッセージから誘導する（既存 `_sora_fetch_openh264` のメッセージは Linux 寄りなので、 macOS 文言を補足）:

```cmake
message(FATAL_ERROR
  "OpenH264 header installation requires 'make'. "
  "On Debian/Ubuntu: run 'apt-get install build-essential'. "
  "On macOS: run 'xcode-select --install'.")
```

### CI 影響

- `build.yml` に `build_macos` job を新設する（ 0001 で旧 job は削除済みのため、 `if: false` 解除ではなく新規追加）:
  - matrix: platform は `macos-15_arm64` (runs_on: macos-15) / `macos-14_arm64` (runs_on: macos-14) の 2 entry、 python_version は 3.12 / 3.13 / 3.14 （旧 job の構成を git 履歴から引き継ぐ）
  - steps: checkout → setup-uv → `uv sync --no-install-project` → `uv build --wheel` → `uv pip install dist/*.whl` → `uv run --no-sync pytest tests/test_version.py` → upload-artifact （ 0001 の `build_ubuntu` job 構成に準拠。 apt install step は不要）
  - `needs` は付けない（ `build_pyi` artifact 経路は 0001 で廃止済み）
- `slack_notify` job の `needs:` を `[build_ubuntu]` から `[build_ubuntu, build_macos]` に変更する

### pyproject.toml の override 整理

0001 の `[tool.scikit-build.cmake.define] TARGET_OS = "ubuntu"` は **デフォルト値** として残し、 macOS override が打ち消す形にする。 Windows native (0005) も同様に `[[tool.scikit-build.overrides]]` で `TARGET_OS = "windows"` を上書きする予定。

scikit-build-core の override 適用順は `if.<key>` の評価で順次適用される（先勝ち優先ではなく後勝ち優先）。 ubuntu host 上では `if.platform-system = "darwin"` が false になり、 `TARGET_OS` はデフォルト `ubuntu` のまま残る。 macOS host 上では override が match して `TARGET_OS = "macos"` に切替わる。

## 完了条件

- macOS arm64 host （ macos-15_arm64 / macos-14_arm64 ）+ Python 3.12 / 3.13 / 3.14 で `uv build --wheel` が成功する
- 生成された wheel のタグが `cp312-cp312-macosx_14_0_arm64` 等になる（ scikit-build-core デフォルトの macOS deployment target に依存）
- wheel 内に `sora_sdk/sora_sdk_ext.cpython-*-darwin.so` / `sora_sdk/sora_sdk_ext.pyi` / `sora_sdk/py.typed` / Python ソースが含まれる
- 次の手順で動作確認が成功する:
  1. `uv venv`
  2. `uv sync --no-install-project`
  3. `uv build --wheel`
  4. `uv pip install --force-reinstall dist/*.whl`
  5. `uv run --no-sync pytest tests/test_version.py` が成功する
  6. `uv run --no-sync python -c "from sora_sdk import sora_sdk_ext; print(sora_sdk_ext.__file__)"` が `site-packages/sora_sdk/sora_sdk_ext.cpython-*-darwin.so` を出力する
  7. `uv run --no-sync python -c "import sora_sdk; print(sora_sdk.Sora)"` がクラスを返す
- `_deps/macos_arm64/{webrtc,sora,boost,openh264}` および `_deps/llvm/arm64-Darwin/{clang,libcxx}` が 2 回目以降の `uv build --wheel` で再 DL されない
- CI で新設 `build_macos` job が green になる（ matrix 内全 entry ）
- `slack_notify` job が `build_ubuntu` + `build_macos` の両 needs を持って動作する

## 解決方法

### cmake/scripts/fetch_deps.cmake

`SORA_PYTHON_SDK_PLATFORM` 算出を「設計方針 → SORA_PYTHON_SDK_PLATFORM 算出の macOS 対応」のコード形に書き換え、 URL 組み立ての platform 文字列に `macos_arm64` を対応させる。 既存 FATAL_ERROR メッセージは「 ubuntu-24.04_x86_64 / macos_arm64 only 」に拡張する。 0003 / 0004 / 0005 で順次追加。

### pyproject.toml

0001 の末尾追加セクション群に以下を追記する:

```toml
[[tool.scikit-build.overrides]]
if.platform-system = "darwin"
cmake.define.TARGET_OS = "macos"
cmake.define.CMAKE_SYSTEM_PROCESSOR = "arm64"
cmake.define.CMAKE_OSX_ARCHITECTURES = "arm64"
cmake.define.CMAKE_C_COMPILER_TARGET = "aarch64-apple-darwin"
cmake.define.CMAKE_CXX_COMPILER_TARGET = "aarch64-apple-darwin"
```

### CMakeLists.txt

- `if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Darwin" AND NOT CMAKE_SYSROOT)` ガードで `xcrun --sdk macosx --show-sdk-path` 経由で `CMAKE_SYSROOT` を設定するロジックを `project()` 直後に追加する
- 既存 `CMakeLists.txt:111-123` の macOS ブランチは触らない（ 0001 後の `TARGET_OS=macos` で自動的に有効化される）
- `find_package(Python ...)` 周辺で macOS の SDK path 不整合が出ないか確認する（必要なら `CMAKE_FIND_FRAMEWORK = LAST` 追加検討）

### .github/workflows/build.yml

- 「設計方針 → CI 影響」の通り `build_macos` job を新設する
- `jobs.slack_notify.needs` を `[build_ubuntu]` から `[build_ubuntu, build_macos]` に変更する

### CHANGES.md

`## develop` セクションに以下を追加する（既存 `[CHANGE] build backend を ...` の下、 `[CHANGE]` グループ内）:

```
- [CHANGE] macOS arm64 ネイティブビルドを scikit-build-core 経路に移行する
  - @voluntas
```

`build_macos` job の新設、 `build_pyi` artifact 経路廃止等の実装詳細はリリースノートに含めない。

## ロールバック

0002 マージ後に macOS native build で問題が発覚した場合:

1. `git revert -m 1 <merge-commit>` で revert PR を作成する
2. revert 後、 新設した `build_macos` job が build.yml から消え、 0001 適用直後の job 構成（ `get_sdk_version` / `build_ubuntu` / `slack_notify` ）に戻ることを確認する
3. `pyproject.toml` の macOS override セクションが消えるか確認する
4. 0001 + 0003 + 0004 + 0005 の進捗状況に応じて、 macOS だけ別途修正コミットで forward fix するか判断する
