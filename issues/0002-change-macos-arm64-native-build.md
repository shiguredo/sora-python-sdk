# macOS arm64 ネイティブビルド対応

- Priority: High
- Created: 2026-05-21
- Updated: 2026-07-17
- Completed: 2026-07-23
- Model: Composer 2.5
- Branch: feature/change-macos-arm64-native-build
- Polished: 2026-07-23

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
- `CMakeLists.txt` の `find_package(Python ...)` が scikit-build-core 注入の exact interpreter を使い、project 後の sysroot 変更を必要としないことを検証する。
- `pyproject.toml` に `[[tool.scikit-build.overrides]]` で macOS の `TARGET_OS = "macos"` 上書きを追加する（ 0001 では `[tool.scikit-build.cmake.define] TARGET_OS = "ubuntu"` を直接設定したため、 macOS では override で `"macos"` に変える）
- macOS native での `uv build --wheel` 成功と `pytest tests/test_version.py` 完走（ wheel タグは `macosx_14_0_arm64` 等）
- `.github/workflows/build.yml` に scikit-build-core 経路の `build_macos` job を新設する（ 0001 で旧 job は削除済み。 `build_pyi` artifact 経路は使わない）
- `build_macos` matrix は、2026 年 11 月 2 日に support 終了予定の `macos-14` を使わず、GitHub が support する arm64 の `macos-15` / `macos-26` に固定する。
- macos-15 / macos-26 のどちらで build しても binary と wheel tag の最小 deployment target を macOS 14.0 に固定する。`macos-15_arm64` を canonical 配布 artifact、`macos-26_arm64` を validation-only とし、0066 / 0067 と同じ名前空間を使う。
- `slack_notify` の `needs:` に `build_macos` を追加する

含まない（別 issue で扱う）:

- Linux arm64 cross-compile（Ubuntu は 0003、Raspberry Pi OS は 0004、Jetson は 0043）
- Windows x86_64 native （ 0005 ）
- publish / release artifact の選定（0066）と E2E（0067）。レガシーファイル削除は 0001 で完了済み。
- Makefile （ 0007 ）
- macOS x86_64 native （プロジェクトでサポート対象外。 macOS arm64 のみ）

## 現状

- 0001 で `_SORA_CLANG_DIR = ${DEPS_ROOT}/llvm/<host_key>/clang` が `_sora_fetch_llvm` の戻り変数として確定する
- 0001 の `<host_key>` は `${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}` で ubuntu バージョンを含まないため、 macOS host では追加変更なしで `arm64-Darwin` になる（ LLVM 周りの 0002 側対応は不要）
- `CMakeLists.txt:111-123` の `if(TARGET_OS STREQUAL "macos")` ブランチで `CXX_VISIBILITY_PRESET hidden` を設定し、 `sora_sdk_ext` に `-nostdinc++ -isystem${LIBCXX_INCLUDE_DIR}` を、 `nanobind-static` にはさらに `-isystem${LIBCXXABI_INCLUDE_DIR}` を付ける既存実装がある（このまま使える）
- `BOOST_ASIO_DISABLE_STD_ATOMIC_WAIT` は sora-cpp-sdk 側で PUBLIC 定義されるようになったため CMakeLists.txt から削除済み（ 69ac472 ）。 Python SDK 側の対応は不要
- 0001 で削除される run.py （削除前 `run.py:319-331` ）は macOS arm64 native の `cmake_args` として `CMAKE_SYSTEM_PROCESSOR=arm64` / `CMAKE_OSX_ARCHITECTURES=arm64` / `CMAKE_*_COMPILER_TARGET=aarch64-apple-darwin` / `CMAKE_SYSROOT=$(xcrun --sdk macosx --show-sdk-path)` を渡していた。 削除後は git 履歴 (`git show <削除前コミット>:run.py`) で参照する
- 0001 で削除される旧 `build_macos` job （削除前 `build.yml:230-279` ）は `macos-15_arm64` / `macos-14_arm64` matrix で Python 3.12 / 3.13 / 3.14 を回し、 `uv run python run.py build macos_arm64` + `uv build` を実行する 2 段構成だった。Python matrix だけを引き継ぎ、deprecated な runner label は引き継がない。

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

### macOS toolchain override

0001 の scikit-build-core requirement を `scikit-build-core>=1.0,<2`、`minimum-version = "1.0"` へ更新する。1.0 以降は `CMAKE_OSX_DEPLOYMENT_TARGET` を wheel tag 算出へ反映するため、ローカルの素の `uv build --wheel` と CI が同じ `macosx_14_0_arm64` tag を生成できる。

build-system requirement は通常の project dependency として `uv.lock` に記録されないため、backend version 確認のためだけに scikit-build-core を dev dependency へ重複追加しない。`uv build -v --wheel` の build isolation log から実際に解決された version が `>=1.0,<2` であることを確認する。この global backend 更新後に、0001 の ubuntu-24.04 x86_64 × Python 3.12 / 3.13 / 3.14 について wheel filename / 内容、型情報、version metadata、install / import smoke を再実行し、0.11 系からの回帰が無いことを必須とする。0003 / 0005 は同じ 1.x backend 契約を維持し、downgrade しない。

`pyproject.toml` に macOS 用 override を 1 block だけ追加する。matching override が `cmake.define` table を置換しないよう `inherit.cmake.define = "append"` を必須とし、`TARGET_OS` と全 Apple toolchain define を同じ block に置く。

```toml
[[tool.scikit-build.overrides]]
if.platform-system = "darwin"
inherit.cmake.define = "append"
cmake.define.TARGET_OS = "macos"
cmake.define.CMAKE_SYSTEM_PROCESSOR = "arm64"
cmake.define.CMAKE_OSX_ARCHITECTURES = "arm64"
cmake.define.CMAKE_OSX_DEPLOYMENT_TARGET = "14.0"
cmake.define.CMAKE_OSX_SYSROOT = "macosx"
cmake.define.CMAKE_C_COMPILER_TARGET = "aarch64-apple-darwin"
cmake.define.CMAKE_CXX_COMPILER_TARGET = "aarch64-apple-darwin"
```

scikit-build-core の `if.platform-system` は `sys.platform` ベースで、`darwin` が macOS に一致する。`CMAKE_OSX_SYSROOT=macosx` は最初の `project()` より前に cache へ渡され、CMake が active Xcode の SDK を解決する。Apple SDK に `CMAKE_SYSROOT` を使わず、`project()` 後に sysroot を変更しない。

CI は configure 前に `xcrun --sdk macosx --show-sdk-path` の exit code、空出力、directory 実在を検証する。configure 後は compile / link command の `-isysroot` が同じ SDK realpath、`CMAKE_OSX_DEPLOYMENT_TARGET=14.0`、全 Mach-O の minimum OS が 14.0 であることを検証する。

`CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` は 0001 で `_SORA_CLANG_DIR/bin/clang(++)` に設定されるため、 macOS でも libwebrtc 同梱 clang が使われる。

### fetch_deps.cmake の URL 組み立ての macOS 対応

fetch_deps.cmake が `DEPS` の値から組み立てる各アーカイブ URL の platform 文字列に `macos_arm64` を対応させる。 アーカイブ名の例（バージョンは `DEPS` の現在値で組み立てる。 現時点では `WEBRTC_BUILD_VERSION=m150.7871.3.1` / `SORA_CPP_SDK_VERSION=2026.2.0-canary.23` / `BOOST_VERSION=1.91.0` ）:

- WebRTC: `webrtc.macos_arm64.tar.gz`
- Sora C++ SDK: `sora-cpp-sdk-2026.2.0-canary.23_macos_arm64.tar.gz`
- Boost: `boost-1.91.0_sora-cpp-sdk-2026.2.0-canary.23_macos_arm64.tar.gz`

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
  - matrix: platform は `macos-15_arm64` (runs_on: macos-15) / `macos-26_arm64` (runs_on: macos-26) の 2 entry、Python version は 3.12 / 3.13 / 3.14。
  - steps: checkout → setup-uv → `uv sync --no-install-project` → `uv build --wheel` → `uv pip install dist/*.whl` → `uv run --no-sync pytest tests/test_version.py` → upload-artifact （ 0001 の `build_ubuntu` job 構成に準拠。 apt install step は不要）
  - `needs` は付けない（ `build_pyi` artifact 経路は 0001 で廃止済み）
- 両 runner の build step に `MACOSX_DEPLOYMENT_TARGET=14.0` を設定し、override の `CMAKE_OSX_DEPLOYMENT_TARGET=14.0` と一致させる。生成 wheel は `macosx_14_0_arm64` tag とし、macOS 14 で利用できない binary を同 tag で配布しない。
- artifact 名は `${{ matrix.platform.name }}_python-${{ matrix.python_version }}` に固定する。各 artifact は対応 ABI の wheel を厳密に 1 件だけ含み、upload 前に distribution、version、CPython / ABI tag、`macosx_14_0_arm64`、全 Mach-O の arm64 / minimum OS 14.0 を検証する。
- `slack_notify` job の `needs:` を `[build_ubuntu]` から `[build_ubuntu, build_macos]` に変更する。
- 後続 0003 は `build_macos` dependency を維持し、0067 が `ci_result` へ置き換えるまで `[build_ubuntu, build_macos]` から退行させない。

### pyproject.toml の override 整理

0001 の `[tool.scikit-build.cmake.define] TARGET_OS = "ubuntu"` は **デフォルト値** として残し、 macOS override が打ち消す形にする。 Windows native (0005) も同様に `[[tool.scikit-build.overrides]]` で `TARGET_OS = "windows"` を上書きする予定。

scikit-build-core の override 適用順は `if.<key>` の評価で順次適用される（先勝ち優先ではなく後勝ち優先）。 ubuntu host 上では `if.platform-system = "darwin"` が false になり、 `TARGET_OS` はデフォルト `ubuntu` のまま残る。 macOS host 上では override が match して `TARGET_OS = "macos"` に切替わる。

## 完了条件

- macOS arm64 host（macos-15_arm64 / macos-26_arm64）+ Python 3.12 / 3.13 / 3.14 で `uv build --wheel` が成功する。
- 両 runner で生成された wheel のタグが `cp312-cp312-macosx_14_0_arm64` 等になり、Mach-O の minimum OS が 14.0 である
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
- CI で新設 `build_macos` job が green になり、完全名 artifact 6 件が各 1 wheel を持つ。
- `slack_notify` job が `build_ubuntu` + `build_macos` の両 needs を持って動作する
- `pyproject.toml` の build requirement と `uv build -v` の build isolation log が scikit-build-core `>=1.0,<2` を示し、ubuntu-24.04 x86_64 × 3 ABI の 0001 成果物 / install smoke が backend 更新後も green になる。

## 解決方法

### cmake/scripts/fetch_deps.cmake

- `_SORA_ALLOWED_PLATFORMS` に `macos_arm64` を追加する。
- 自動検出ロジックを `CMAKE_HOST_SYSTEM_NAME` の Linux / Darwin / other 3 分岐に書き直す。 Darwin 分岐では `CMAKE_HOST_SYSTEM_PROCESSOR STREQUAL "arm64"` のとき `SORA_PYTHON_SDK_PLATFORM = macos_arm64` を確定し、それ以外は FATAL_ERROR で拒否する。 Rosetta 2 (`arch -x86_64`) 経由の shell で誤起動した場合の誘導文言も FATAL_ERROR に含める。
- URL 組み立ては `${SORA_PYTHON_SDK_PLATFORM}` 展開で自動的に macOS 用アーカイブ名に対応するため既存ロジックのまま流用する。
- `_sora_fetch_openh264` の FATAL_ERROR メッセージを Debian/Ubuntu (`apt-get install build-essential`) と macOS (`xcode-select --install`) 両プラットフォームの誘導を含む形に拡張する。
- 自動検出パスの `Detected platform:` message は末尾で常に出力される `platform: ${SORA_PYTHON_SDK_PLATFORM}` message と重複するため削除する。

### pyproject.toml

- 既存 `[tool.scikit-build.cmake.define] TARGET_OS = "ubuntu"` はデフォルトとして残し、`[[tool.scikit-build.overrides]]` with `if.platform-system = "darwin"` + `inherit.cmake.define = "append"` で macOS 用 define を上書き追加する。
- 実際に採用した define は次の 4 つに絞る:
  - `TARGET_OS = "macos"`
  - `CMAKE_OSX_ARCHITECTURES = "arm64"`
  - `CMAKE_OSX_DEPLOYMENT_TARGET = "14.0"`
  - `CMAKE_OSX_SYSROOT = "macosx"`
- 設計方針時に列挙していた `CMAKE_SYSTEM_PROCESSOR` / `CMAKE_C_COMPILER_TARGET` / `CMAKE_CXX_COMPILER_TARGET` は、実 build (`_build/.../build.ninja`) の compile flag に一切伝播しないことを確認したため不採用とした（Apple プラットフォームでは `CMAKE_OSX_ARCHITECTURES` + `CMAKE_OSX_DEPLOYMENT_TARGET` が最終 triple を決定する）。 native macOS build では dead define のため残さない。

### CMakeLists.txt

- 変更なし（既存 macOS 分岐が `TARGET_OS=macos` で自動的に有効化される）。

### .github/workflows/build.yml

- `build_macos` job を新設する。 matrix は `macos-15_arm64` (runs_on: macos-15) / `macos-26_arm64` (runs_on: macos-26) × Python 3.12 / 3.13 / 3.14。 timeout は 30 分。
- steps: checkout → Verify Xcode SDK (`xcodebuild -version`, `xcrun --sdk macosx --show-sdk-version`, `xcrun --sdk macosx --show-sdk-path` の実在検証) → setup-uv → `uv sync --no-install-project` → `uv build -v --wheel` (build isolation ログに scikit-build-core の解決 version を残す) → Verify wheel → Install wheel (`--force-reinstall`) → Smoke test (`sora_sdk_ext.__file__`, `sora_sdk.Sora`) → `pytest tests/test_version.py` → upload-artifact。
- Verify wheel step は: dist/ に wheel が 1 件 / wheel filename の distribution・CPython・ABI・platform tag の regex 一致 / wheel 内に `sora_sdk/__init__.py` / `sora_sdk/py.typed` / `sora_sdk/sora_sdk_ext.pyi` が同梱 / Mach-O が arm64 単一 slice / Mach-O `LC_BUILD_VERSION` の minos が 14.0、を検証する。
- `MACOSX_DEPLOYMENT_TARGET` env は設定しない。 scikit-build-core 1.x が `CMAKE_OSX_DEPLOYMENT_TARGET` cmake define から wheel tag を算出することを確認したため、 pyproject.toml の該当 define を single source of truth とする。 実 build でも env なしで `macosx_14_0_arm64` tag と minos 14.0 が生成されることを確認した。
- `jobs.slack_notify.needs` を `[build_ubuntu]` から `[build_ubuntu, build_macos]` に変更する。

### CHANGES.md

`## develop` セクションの `[CHANGE]` グループ内、既存 `[CHANGE] build backend を setuptools から scikit-build-core に切り替える` の下に次を追加する:

```
- [CHANGE] macOS arm64 ネイティブビルドを scikit-build-core 経路に移行する
  - @voluntas
```

### .gitignore

- 旧 `run.py` 経路の残骸である `/_install` `/_source` を追加する。 新 scikit-build-core 経路 (`/_build` `/_deps`) は 0001 で対応済み。

## ロールバック

後続 issue が未着手の場合だけ、0002 の squash commit を `git revert <squash-commit>` し、0001 適用直後の `get_sdk_version` / `build_ubuntu` / `slack_notify` 構成へ戻す。

0003 / 0004 / 0005 または 0066 / 0067 / 0070 / 0071 が merge 済みなら、先に publish / release / E2E を停止して forward fix を優先する。根本設計を revert する場合は依存 issue を逆順に revert または workflow 無効化してから 0002 を戻し、scikit-build-core version、macOS artifact 名、Slack dependency の dangling reference が無いことを確認する。

## 参照（一次資料）

- CMake `CMAKE_OSX_SYSROOT`: https://cmake.org/cmake/help/latest/variable/CMAKE_OSX_SYSROOT.html
- scikit-build-core overrides: https://scikit-build-core.readthedocs.io/en/stable/configuration/overrides.html
- scikit-build-core changelog: https://scikit-build-core.readthedocs.io/en/stable/about/changelog.html
- GitHub Actions runner images: https://github.com/actions/runner-images
