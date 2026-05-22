# macOS arm64 ネイティブビルド対応

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-macos-arm64-native-build

## 目的

0001 で ubuntu-24.04 x86_64 native 向けに実装した scikit-build-core + `cmake/scripts/fetch_deps.cmake` を macOS arm64 でも動作させ、 macOS host 上で `uv build --wheel` 一発で macOS arm64 用 wheel を生成できる状態にする。 これにより 0001 で `if: false` で disable していた `build_macos` job を復活させる。

## 設計の前提（プロジェクト全体の新方針からの該当部）

- ビルド環境は ubuntu-24.04 x86_64 host のみに集約するが、 **macOS (arm64) と Windows (x86_64) は例外的にそれぞれの OS で native build を維持する** （ cross-compile しない）
- macOS native は macOS arm64 runner で native build する
- clang は libwebrtc 同梱 clang バイナリを継続使用する（ 0001 で `_sora_fetch_llvm` が tools + libcxx + buildtools を取得して `clang/scripts/update.py` 経由で host 用 clang バイナリを `_SORA_CLANG_DIR` に展開する経路を既に実装済み。 macOS host では host = `Darwin arm64` 用の clang バイナリが取得される）

## スコープ

含む:

- `cmake/scripts/fetch_deps.cmake` の `SORA_PYTHON_SDK_PLATFORM` 算出を macOS host 対応に拡張する（ `CMAKE_HOST_SYSTEM_NAME = Darwin` 分岐で `macos_${arch}` を組み立てる）
- `fetch_deps.cmake` の FATAL_ERROR ガードを `ubuntu-24.04_x86_64` / `macos_arm64` 両方を許容するように拡張する
- `CMakeLists.txt` の `find_package(Python ...)` 周辺と `project()` 前後の処理を macOS でも問題なく動くか確認し、必要なら macOS 固有調整を加える
- `pyproject.toml` に `[[tool.scikit-build.overrides]]` で macOS の `TARGET_OS = "macos"` 上書きを追加する（ 0001 では `[tool.scikit-build.cmake.define] TARGET_OS = "ubuntu"` を直接設定したため、 macOS では override で `"macos"` に変える）
- macOS native での `uv build --wheel` 成功と `pytest tests/test_version.py` 完走（ wheel タグは `macosx_14_0_arm64` 等）
- `.github/workflows/build.yml` の `build_macos` job の `if: false` を解除し、 0001 で削除した `build_pyi` artifact 経路を経ずに scikit-build-core 経路で完結させる
- `slack_notify` の `needs:` に `build_macos` を戻す

含まない（別 issue で扱う）:

- Linux arm64 cross-compile (ubuntu armv8) （ 0004 ）
- Linux arm64 cross-compile (jetson / rpi) （ 0005 ）
- Windows x86_64 native （ 0006 ）
- レガシーファイル削除（ 0007 ）
- Makefile （ 0008 ）
- `build_macos` matrix の macOS バージョン拡充（既存 `macos-15_arm64` / `macos-14_arm64` を維持する）
- macOS x86_64 native （プロジェクトでサポート対象外。 macOS arm64 のみ）

## 現状

- 0001 で `_SORA_CLANG_DIR = ${DEPS_ROOT}/llvm/${LLVM_HOST_KEY}/clang` が `_sora_fetch_llvm` の戻り変数として確定する
- 0001 で `LLVM_HOST_KEY = ${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}-${_SORA_UBUNTU_VERSION_ID}` と組み立てているため、 macOS host では `_SORA_UBUNTU_VERSION_ID` が空になる
- `CMakeLists.txt:111-131` の `if(TARGET_OS STREQUAL "macos")` ブランチで `-nostdinc++ -isystem${LIBCXX_INCLUDE_DIR}` と `-isystem${LIBCXXABI_INCLUDE_DIR}` を `sora_sdk_ext` / `nanobind-static` に付ける既存実装がある（このまま使える）
- `CMakeLists.txt:111-120` で macOS のときに `BOOST_ASIO_DISABLE_STD_ATOMIC_WAIT` を立てる既存実装がある（このまま使える）
- 既存 `run.py:320-332` で macOS arm64 native の `cmake_args` として `CMAKE_SYSTEM_PROCESSOR=arm64` / `CMAKE_OSX_ARCHITECTURES=arm64` / `CMAKE_*_COMPILER_TARGET=aarch64-apple-darwin` / `CMAKE_SYSROOT=$(xcrun --sdk macosx --show-sdk-path)` を渡している
- 既存 `build.yml:230-279` の `build_macos` job は `macos-15_arm64` / `macos-14_arm64` matrix で Python 3.12 / 3.13 / 3.14 を回し、 `uv run python run.py build macos_arm64` + `uv build` を実行する 2 段構成

## 設計方針

### SORA_PYTHON_SDK_PLATFORM 算出の macOS 対応

`CMakeLists.txt` の platform 算出ロジックに `CMAKE_HOST_SYSTEM_NAME` 分岐を追加する:

```cmake
if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux")
  # 既存 ubuntu 経路 (0001 で実装済み)
  file(READ /etc/os-release _OS_RELEASE)
  if(NOT _OS_RELEASE MATCHES "(^|\n)ID=([^\n]+)")
    message(FATAL_ERROR "Failed to read ID from /etc/os-release")
  endif()
  set(_ID "${CMAKE_MATCH_2}")
  if(NOT _ID STREQUAL "ubuntu")
    message(FATAL_ERROR "Linux host must be ubuntu; got '${_ID}'")
  endif()
  string(REGEX MATCH "(^|\n)VERSION_ID=\"?([^\"\n]+)\"?" _ "${_OS_RELEASE}")
  set(_SORA_UBUNTU_VERSION_ID "${CMAKE_MATCH_2}")
  set(_arch "${CMAKE_HOST_SYSTEM_PROCESSOR}")
  set(SORA_PYTHON_SDK_PLATFORM "ubuntu-${_SORA_UBUNTU_VERSION_ID}_${_arch}" CACHE STRING "")
elseif(CMAKE_HOST_SYSTEM_NAME STREQUAL "Darwin")
  # 新規 macOS 経路
  set(_SORA_UBUNTU_VERSION_ID "")
  if(CMAKE_HOST_SYSTEM_PROCESSOR STREQUAL "arm64")
    set(SORA_PYTHON_SDK_PLATFORM "macos_arm64" CACHE STRING "")
  else()
    message(FATAL_ERROR
      "macOS host must be arm64; got '${CMAKE_HOST_SYSTEM_PROCESSOR}'. "
      "macOS x86_64 is not supported.")
  endif()
else()
  message(FATAL_ERROR "Unsupported host: ${CMAKE_HOST_SYSTEM_NAME}")
endif()
```

`SORA_PYTHON_SDK_PLATFORM` 許容リストは `ubuntu-24.04_x86_64` / `macos_arm64` の 2 つになる。 0004 で `ubuntu-22.04_x86_64` を host として許容するか判断する（クロス build に 24.04 host のみ使うなら追加不要）。

`LLVM_HOST_KEY` の組み立ては:

```cmake
if(_SORA_UBUNTU_VERSION_ID)
  set(_LLVM_HOST_KEY "${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}-${_SORA_UBUNTU_VERSION_ID}")
else()
  set(_LLVM_HOST_KEY "${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}")
endif()
```

macOS では `arm64-Darwin` となる（ Darwin の glibc 相当バージョンは無いため）。

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

`CMakeLists.txt:111-131` の `if(TARGET_OS STREQUAL "macos")` ブランチが有効化され、 `-nostdinc++ -isystem${LIBCXX_INCLUDE_DIR}` 等が付く。

### macOS 用 cmake.args の追加

既存 `run.py:320-332` で渡していた macOS 固有引数を `pyproject.toml` の `[[tool.scikit-build.overrides]]` に移植する:

```toml
[[tool.scikit-build.overrides]]
if.platform-system = "darwin"
cmake.define.CMAKE_SYSTEM_PROCESSOR = "arm64"
cmake.define.CMAKE_OSX_ARCHITECTURES = "arm64"
cmake.define.CMAKE_C_COMPILER_TARGET = "aarch64-apple-darwin"
cmake.define.CMAKE_CXX_COMPILER_TARGET = "aarch64-apple-darwin"
```

`CMAKE_SYSROOT` は `xcrun --sdk macosx --show-sdk-path` 経由で動的に決まるため、 `CMakeLists.txt` 側で `if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Darwin" AND NOT CMAKE_SYSROOT)` ガードで `execute_process(COMMAND xcrun --sdk macosx --show-sdk-path OUTPUT_VARIABLE _macos_sysroot OUTPUT_STRIP_TRAILING_WHITESPACE)` + `set(CMAKE_SYSROOT "${_macos_sysroot}" CACHE PATH "" FORCE)` で設定する。 `fetch_deps.cmake` ではなく `CMakeLists.txt` の `project()` 後（ compiler 確定後）に置く。

`CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` は 0001 で `_SORA_CLANG_DIR/bin/clang(++)` に設定済みのため、 macOS でも libwebrtc 同梱 clang が使われる。

### deps.json の macOS platform 文字列

`deps.json` の `url_template` 内 `{platform}` プレースホルダに対し macOS 用アーカイブ名を確認する:

- WebRTC: `webrtc.macos_arm64.tar.gz` （`https://github.com/shiguredo-webrtc-build/webrtc-build/releases/download/m149.7827.0.0/webrtc.macos_arm64.tar.gz`）
- Sora C++ SDK: `sora-cpp-sdk-2026.2.0-canary.11_macos_arm64.tar.gz`
- Boost: `boost-1.91.0_sora-cpp-sdk-2026.2.0-canary.11_macos_arm64.tar.gz`

0003 実装時に `curl -sL <url> | tar tzf - | head -5` で各 macOS アーカイブの strip_components を確認する。 ubuntu と同じく暫定 `1` で開始する。

### OpenH264 ヘッダ取得

macOS native では Xcode Command Line Tools 経由で `make` がインストール済みのため、 `_sora_fetch_openh264` の `find_program(_SORA_MAKE_EXECUTABLE make)` がそのまま動く。 GitHub Actions macOS runner には `make` が pre-install 済み。 ローカル開発で `xcode-select --install` がされていない環境では FATAL_ERROR メッセージから誘導する（既存 `_sora_fetch_openh264` のメッセージは Linux 寄りなので、 macOS 文言を補足）:

```cmake
message(FATAL_ERROR
  "OpenH264 header installation requires 'make'. "
  "On Debian/Ubuntu: run 'apt-get install build-essential'. "
  "On macOS: run 'xcode-select --install'.")
```

### CI 影響

- `build_macos` job の `jobs.build_macos` 直下の `if: false` を削除する
- `build_macos` job の `needs: [build_pyi]` を完全削除する
- `build_macos` job の `download-artifact` / `cp` ステップ（既存 L256-259 / L260-262 ）を削除する
- `build_macos` job の `uv run python run.py build macos_arm64` 行（既存 L271 付近）を削除し、 `uv build` だけを残す
- `slack_notify` job の `needs:` に `build_macos` を戻す（ 0001 で `build_ubuntu` のみに絞った）

### pyproject.toml の override 整理

0001 の `[tool.scikit-build.cmake.define] TARGET_OS = "ubuntu"` は **デフォルト値** として残し、 macOS override が打ち消す形にする。 Windows native (0006) も同様に `[[tool.scikit-build.overrides]]` で `TARGET_OS = "windows"` を上書きする予定。

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
- CI で `build_macos` job が green になる（ matrix 内全 entry ）
- `slack_notify` job が `build_ubuntu` + `build_macos` の両 needs を持って動作する

## 解決方法

### cmake/scripts/fetch_deps.cmake

`SORA_PYTHON_SDK_PLATFORM` 算出と `LLVM_HOST_KEY` 算出を「設計方針 → SORA_PYTHON_SDK_PLATFORM 算出の macOS 対応」のコード形に書き換える。 既存 FATAL_ERROR メッセージは「 ubuntu-24.04_x86_64 / macos_arm64 only 」に拡張する。 0004 / 0005 / 0006 で順次追加。

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

既存 `BUILD_PROFILE=debug` override は維持する（複数 override は順次適用される）。

### CMakeLists.txt

- `if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Darwin" AND NOT CMAKE_SYSROOT)` ガードで `xcrun --sdk macosx --show-sdk-path` 経由で `CMAKE_SYSROOT` を設定するロジックを `project()` 直後に追加する
- 既存 `CMakeLists.txt:111-131` の macOS ブランチは触らない（ 0001 後の `TARGET_OS=macos` で自動的に有効化される）
- `find_package(Python ...)` 周辺で macOS の SDK path 不整合が出ないか確認する（必要なら `CMAKE_FIND_FRAMEWORK = LAST` 追加検討）

### .github/workflows/build.yml

- `jobs.build_macos.if: false` を削除する
- `jobs.build_macos.needs: [build_pyi]` を完全削除する
- `jobs.build_macos.steps` から `actions/download-artifact name: sora_sdk_${python_version}` と `cp sora_sdk/py.typed src/sora_sdk/py.typed` + `cp sora_sdk/sora_sdk_ext.pyi src/sora_sdk/sora_sdk_ext.pyi` を削除する
- `uv run python run.py build macos_arm64` 行を削除し、 `uv build` のみを残す
- `jobs.slack_notify.needs` を `[build_ubuntu]` から `[build_ubuntu, build_macos]` に戻す

### CHANGES.md

`## develop` セクションに以下を追加する（既存 `[CHANGE] build backend を ...` の下、 `[CHANGE]` グループ内）:

```
- [CHANGE] macOS arm64 ネイティブビルドを scikit-build-core 経路に移行する
  - @voluntas
```

`build_macos` job の復活、 `build_pyi` artifact 経路廃止等の実装詳細はリリースノートに含めない。

## ロールバック

0003 マージ後に macOS native build で問題が発覚した場合:

1. `git revert -m 1 <merge-commit>` で revert PR を作成する
2. revert 後、 `build_macos` job が再び `if: false` に戻り skip されるか確認する
3. `pyproject.toml` の macOS override セクションが消えるか確認する
4. 0001 + 0004 + 0005 + 0006 の進捗状況に応じて、 macOS だけ別途修正コミットで forward fix するか判断する
