# ubuntu-24.04_armv8 platform の cross-compile wheel ビルドを sysroot.py 経路で追加する

- Priority: High
- Created: 2026-06-22
- Completed: 2026-06-22
- Model: Opus 4.7
- Branch: feature/add-ubuntu-24-04-armv8-cross-build
- Polished: 2026-06-22

## 目的

0024 で multistrap 経路から sysroot.py 経路への置き換えが完了し、 `sysroot.py` と `sysroot/*.json` 4 ファイルは merge 済だが、 `cmake/scripts/fetch_deps.cmake` の `_sora_fetch_rootfs` 関数定義はメインスクリプトから呼び出されておらず、 `cmake/toolchains/*.cmake` 自体も存在しないため、 cross-compile wheel ビルドは CI でも復活していない。

本 issue では 4 platform (ubuntu-22.04_armv8 / ubuntu-24.04_armv8 / raspberry-pi-os_armv8 / ubuntu-22.04_armv8_jetson) のうち最も構成が単純な **`ubuntu-24.04_armv8` 1 platform に絞って**、 `uv build` → `cmake configure` → `_sora_fetch_rootfs` → `sysroot.py build` → cmake build → wheel 生成の経路を最初から最後まで通す。 本 issue で生成される wheel は CI artifact までで、 manylinux タグ確定と PyPI publish は 0022 + 別 issue で対応する (本 issue 単体では PyPA Warehouse 仕様で plain `linux_aarch64` タグは publish 不可、 `pip install` も不可)。 これが green になれば、 残り 3 platform は同じパターンで後続 issue として順次足せる。

## 優先度根拠

High:

- 0024 で sysroot.py を merge した直後の最初の cross-compile 経路。 本 issue が動かない限り、 後続 3 platform の cross-compile 復活を進める根拠が立たない
- 0024 (closed) の `## スコープ境界` で「cross-compile した wheel を実際に生成する経路 (toolchain ファイル新設、 pyproject.toml override 追加、 `SORA_PYTHON_SDK_PLATFORM` 許容リスト追加、 `_sora_fetch_rootfs` の **実呼び出し**、 CI matrix の `exclude` 解除) は本 issue では行わず、 後続 cross 系 issue で扱う」 と明示されており、 その後続 issue の第 1 弾に該当する

## 現状

### sysroot.py 側 (0024 merge 済)

- `sysroot.py` (約 1071 行、 リポジトリルート直下) と `sysroot/*.json` 4 ファイル (ubuntu-22.04_armv8 / ubuntu-24.04_armv8 / ubuntu-22.04_armv8_jetson / raspberry-pi-os_armv8) は配置済み
- CLI: `python3 sysroot.py build --config <json> --dest <dir>` で rootfs を構築できる
- 既存 `verify_sysroot` job (`.github/workflows/build.yml` の 156-245 行) で ubuntu-24.04 x86_64 host での 4 platform 順次 build → 検証 → clean が CI で走っており、 sysroot.py の動作自体は green

### cmake 側 (0024 merge 済 / 本 issue で改修)

- `cmake/scripts/fetch_deps.cmake` の 381-401 行に `_sora_fetch_rootfs(rootfs_dir json_config)` 関数定義あり (メインスクリプトから呼び出されていない)
- 76 行目の `_SORA_ALLOWED_PLATFORMS` は `ubuntu-24.04_x86_64` / `macos_arm64` / `windows_x86_64` の 3 つのみ。 cross 系 platform は configure 時点で `FATAL_ERROR` で落ちる
- `cmake/toolchains/` ディレクトリ自体が存在しない (現状 `cmake/` 配下は `scripts/` のみ)
- `CMakeLists.txt` の 21-42 行には既に `if (CMAKE_CROSSCOMPILING)` ガードと `find_package(Python)` 前後の `CMAKE_FIND_ROOT_PATH_MODE_*` 切り替え (NEVER → BOTH) が用意されているため、 cross 経路の host Python 検出ロジックは既存を再利用する
- 128-207 行の `TARGET_OS STREQUAL "ubuntu"` 分岐 (149-160 行) も既存ロジックを再利用する
- `nanobind_add_module` (90 行目) は nanobind 公式 `cmake/nanobind-config.cmake` 内部で `set_target_properties(... SUFFIX "${NB_SUFFIX}")` を呼ぶため、 `NB_SUFFIX` を `nanobind_add_module` 呼び出しより **前** に CMake 変数として渡せば nanobind 自身が target の `.so` suffix を上書きする (CMakeLists.txt 側に追加の `set_target_properties` は不要)
- `nanobind_add_stub` (107-116 行) は cross-compile 時に host 上で aarch64 `.so` を import しようとして必ず失敗する (既存 Windows override で `SORA_GEN_PYI = "OFF"` が同じ理由で設定済)

### pyproject.toml 側 (0024 merge 済 / 本 issue で改修)

- `[tool.scikit-build.cmake.define]` で base 値として `TARGET_OS = "ubuntu"` を定義
- macOS / Windows 用 override (`[[tool.scikit-build.overrides]]`) は存在するが、 cross-compile 用 override は無い
- 既存 override は `if.platform-system = "^darwin"` のように **正規表現** で書かれている (scikit-build-core の `if.*` は `re.search` でマッチするため、 完全一致を意図する場合は `^...$` で anchored 化が必須)

### CI 側 (0024 merge 済 / 本 issue で改修)

- `.github/workflows/build.yml` の 84-152 行の `build_ubuntu` job の matrix に 5 platform entry (`ubuntu-24.04_x86_64` / `ubuntu-22.04_x86_64` / `ubuntu-24.04_armv8` / `ubuntu-22.04_armv8` / `raspberry-pi-os_armv8`) あり
- 118-122 行の `exclude:` で `ubuntu-22.04_x86_64` / `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` / `raspberry-pi-os_armv8` の 4 entry が無効化されており、 現状 build される native は `ubuntu-24.04_x86_64` × 3 Python のみ
- `ubuntu-22.04_armv8_jetson` のみ matrix entry 自体が無い (後続 jetson 復活 issue で matrix entry 追加が必要)
- 0024 で multistrap install + sed パッチ step と `uv run python run.py build && uv build` step は削除済
- `build_ubuntu_arm` job (`if: false` 済) は 0022 で job ごと削除予定。 本 issue では touch しない
- `publish_wheel` matrix (419-430 行) には `ubuntu-24.04_armv8` 自体が存在せず、 本 issue で生成する wheel は publish 対象外
- `create-release` job (473- 行) は `actions/download` で `ubuntu-24.04_armv8` × 3 Python の artifact を取得する設計 (504-508 行)。 現在は exclude のため artifact 不在で release tag 時に download に失敗する状態。 本 issue merge 後は artifact が生成されるため副次的に解消する

## 設計方針

### スコープ境界

本 issue で行うこと:

- `cmake/toolchains/aarch64-linux-gnu.cmake` を新設
- `cmake/scripts/fetch_deps.cmake` を改修
  - `_SORA_ALLOWED_PLATFORMS` (76 行目) に `ubuntu-24.04_armv8` を追加
  - メインスクリプトの `_sora_fetch_llvm` を含む `if(NOT WIN32) ... endif()` ブロック (455-459 行) 直後、 `# 出力契約 8 変数を CACHE PATH で確定` コメント (461 行) より **前** に、 cross 系 platform 用の分岐を挿入し `_sora_fetch_rootfs` を呼び出して sysroot 内容を構築する。 `CMAKE_SYSROOT` 自体は toolchain ファイル経由で確定済 (後述「`CMAKE_SYSROOT` 確定戦略」)
- `pyproject.toml` に cross 用 `[[tool.scikit-build.overrides]]` を **Python ABI 別に 3 件** 追加
- `.github/workflows/build.yml` の `exclude:` から `ubuntu-24.04_armv8` を 1 行削除し、 cross 用 build step と wheel 検証 step を追加。 `build_ubuntu` job の `timeout-minutes: 15` (124 行) を `60` に引き上げる (cross-compile では sysroot 構築 5 分 + LLVM 取得 10 分 + cmake build + nanobind link で 30 分以上かかるため。 既存 native build の timeout も同時に緩和されるが matrix で job 共有のため避けられない)
- `CHANGES.md` の `## develop` セクションに `[ADD]` エントリを 1 件追加し、 既存 0024 由来 `[CHANGE]` エントリの 2 行目 (`armv8 系 cross-compile wheel は CI で生成されない (元から matrix exclude 済)`) を削除する (0030 merge で ubuntu-24.04_armv8 が CI で生成されるようになり、 22 行目の記述は事実と矛盾するため。 0024 エントリの 1 行目 / 3-4 行目はそのまま残す)

CMakeLists.txt の改修は **不要** (nanobind が `NB_SUFFIX` CMake 変数を自身で受け取って target SUFFIX に反映するため、 pyproject.toml の `cmake.define.NB_SUFFIX` 経由で渡せば足りる)。

本 issue で行わないこと (後続 issue で扱う):

- `ubuntu-22.04_armv8` / `raspberry-pi-os_armv8` / `ubuntu-22.04_armv8_jetson` の cross-compile 復活 (本 issue が green になった後、 1 platform 1 issue で順次)。 `ubuntu-22.04_armv8_jetson` は matrix entry の追加自体も必要
- `auditwheel repair --strip --only-plat` による manylinux タグ確定 (0022 で扱う。 0022 のスコープに `ubuntu-24.04_armv8` も含まれる)
- `publish_wheel` matrix への `ubuntu-24.04_armv8` 追加 (0022 で manylinux タグ確定後に別 issue)
- `sysroot.py` の単体テスト (0025 で扱う)
- `sysroot.py` を ty 型チェック対象に追加 (0026 で扱う)
- `sysroot.py` の docstring 拡充 (0028 で扱う)
- `Repo.allow_insecure` 等の YAGNI 整理 (0029 で扱う)

設計上の関係 (本 issue では touch しないが、 影響を確認した項目):

- `sora_sdk_rpi` rename step (build.yml の 130-133 行) は `matrix.platform.name == 'raspberry-pi-os_armv8'` で発火するため `ubuntu-24.04_armv8` には影響しない
- 既存 Upload Artifact step (148-152 行) は matrix の全 entry に対して走るため、 `exclude` から外した `ubuntu-24.04_armv8` の `dist/` も既存 step がそのまま `ubuntu-24.04_armv8_python-3.{12,13,14}` の artifact 名で upload する
- `verify_sysroot` job (156-245 行) と `build_ubuntu` は `needs:` で繋がず並列実行のまま (sysroot.py 起因の fail が 2 job で同時に観察され原因特定が早いため)
- 0022 (open) との順序: 本 issue で生成する `linux_aarch64.whl` artifact 自体は 0022 と独立に CI で完結する。 0022 が後で `auditwheel repair --strip --only-plat` を入れると本 issue の artifact が manylinux 化される

### cmake/toolchains/aarch64-linux-gnu.cmake の新設

CMake 公式仕様 (https://cmake.org/cmake/help/latest/variable/CMAKE_SYSROOT.html ) では `CMAKE_SYSROOT` は **toolchain ファイル内でのみ設定可能** と明示されているため、 toolchain ファイル側で確定する。 ただし sysroot の中身は cmake configure 中に sysroot.py で動的構築されるため、 toolchain 評価時点では空ディレクトリの可能性がある。 中身は fetch_deps.cmake メインスクリプトで埋める。

toolchain ファイルでは sysroot path を環境変数 `SORA_PYTHON_SDK_SYSROOT_DIR` から取得する (CI step で絶対パスを渡す):

```cmake
# cross-compile toolchain for aarch64-linux-gnu (Ubuntu / Raspberry Pi OS / Jetson 共通)
# CMAKE_SYSROOT は CMake 仕様で toolchain ファイル内でのみ設定可能。
# sysroot path は CI step (もしくは開発者の uv build 起動時) に環境変数で渡す。
# sysroot の中身は fetch_deps.cmake 内 _sora_fetch_rootfs で構築する。
# CMAKE_FIND_ROOT_PATH_MODE_* は CMakeLists.txt 25-42 行の既存ロジックに集約する。
# CMAKE_C_COMPILER / CMAKE_CXX_COMPILER は fetch_deps.cmake で LLVM 同梱 clang に確定する。
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_CXX_COMPILER_TARGET aarch64-linux-gnu)
if(DEFINED ENV{SORA_PYTHON_SDK_SYSROOT_DIR})
  set(CMAKE_SYSROOT "$ENV{SORA_PYTHON_SDK_SYSROOT_DIR}")
endif()
```

toolchain ファイル名は GNU triple そのもの (`aarch64-linux-gnu`) を採用する。 4 platform で同じ GNU triple のため共通で使い回す。 glibc バージョン差は sysroot 側で扱う。 platform 別の `TARGET_OS` 切り替えは後続 issue で pyproject.toml の cross override 内で対応する。

### `CMAKE_SYSROOT` 確定戦略

CMake の評価順序:

1. `project(sora_sdk)` 開始時に toolchain ファイルが読まれ、 `CMAKE_SYSROOT` が `SORA_PYTHON_SDK_SYSROOT_DIR` 環境変数 (CI step で `${{ github.workspace }}/_deps/ubuntu-24.04_armv8/rootfs` 等の絶対パスを渡す) で確定する。 この時点では sysroot ディレクトリ自体は未作成
2. 言語有効化 (`enable_language(C/CXX)`)。 通常 cmake は sysroot 内の compiler / libc / startup file を要求するが、 host LLVM clang は本ステップ時点で未取得のため、 `CMAKE_C_COMPILER_WORKS = "TRUE"` / `CMAKE_CXX_COMPILER_WORKS = "TRUE"` を pyproject.toml の cross override で渡して try_compile を skip させる
3. `project()` の末尾で `CMAKE_PROJECT_TOP_LEVEL_INCLUDES` (= `fetch_deps.cmake`) が読まれる
4. fetch_deps.cmake メインスクリプトで `_sora_fetch_llvm` が `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` を host LLVM clang の絶対パスに確定し、 続いて cross 分岐で `_sora_fetch_rootfs` が sysroot の中身 (libc / libstdc++ / 各種 dev headers) を構築する
5. cmake が `find_package(Boost ...)` 等を評価する時点では `CMAKE_SYSROOT` も中身も確定済で、 sysroot 内 lib をリンカが見つけられる

`CMAKE_FIND_ROOT_PATH_MODE_*` は CMakeLists.txt の 25-42 行の既存 `if (CMAKE_CROSSCOMPILING)` ブロックで `find_package(Python)` 前後で NEVER ↔ BOTH に切り替えられている。 `CMAKE_FIND_ROOT_PATH_MODE_PACKAGE = BOTH` のため sysroot 配下と `_PLATFORM_ROOT` 配下 (prebuilt deps) の両方が探索対象になる。

### `CMAKE_TOOLCHAIN_FILE` の相対パス解決

CMake 公式仕様 (https://cmake.org/cmake/help/latest/variable/CMAKE_TOOLCHAIN_FILE.html ) は「relative path は build dir (`CMAKE_BINARY_DIR`) を起点に評価し、 そこに無ければ source dir (`CMAKE_SOURCE_DIR`) でフォールバック」 と定義する。 scikit-build-core の `build-dir = "_build/{wheel_tag}"` (pyproject.toml の 40 行) で build dir は `<repo>/_build/<tag>/` に置かれ、 そこに `cmake/toolchains/aarch64-linux-gnu.cmake` は存在しないため、 自動的に source dir `<repo>/cmake/toolchains/aarch64-linux-gnu.cmake` で解決される。

### Python ヘッダ / ABI の扱い

`find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)` (CMakeLists.txt の 22 / 35 行) は cross 時に `CMAKE_FIND_ROOT_PATH_MODE_*` を NEVER に切り替えて **host (x86_64) Python** を探す既存ロジックを利用する。 `Python_INCLUDE_DIR` も host Python のものになるが、 nanobind は `Development.Module` のみを要求し libpython リンクを行わない (Python C API は ABI 安定で aarch64 でも同じ ABI ナンバー)。 そのため host の `Python.h` で cross compile した `.so` が target で正しく import される。 CMakeLists.txt の 17-19 行の `cmake_policy(SET CMP0190 OLD)` 設定はこれと整合する。

### cmake/scripts/fetch_deps.cmake の改修

1. **76 行目**: `_SORA_ALLOWED_PLATFORMS` に `ubuntu-24.04_armv8` を追加

   ```cmake
   set(_SORA_ALLOWED_PLATFORMS "ubuntu-24.04_x86_64" "ubuntu-24.04_armv8" "macos_arm64" "windows_x86_64")
   ```

2. **`_sora_fetch_llvm` を含む `if(NOT WIN32) ... endif()` ブロック (455-459 行) の直後、 `# 出力契約 8 変数を CACHE PATH で確定` (461 行) より前** に cross 分岐を挿入:

   ```cmake
   # cross 系 platform 用 sysroot 構築 (rootfs を `_PLATFORM_ROOT/rootfs` に展開)
   # CMAKE_SYSROOT は toolchain ファイル経由で SORA_PYTHON_SDK_SYSROOT_DIR 環境変数から確定済。
   # ここでは rootfs ディレクトリの中身 (libc / libstdc++ / dev headers) を sysroot.py で構築する。
   if(SORA_PYTHON_SDK_PLATFORM STREQUAL "ubuntu-24.04_armv8")
     set(_ROOTFS_DIR "${_PLATFORM_ROOT}/rootfs")
     set(_SYSROOT_JSON "${CMAKE_SOURCE_DIR}/sysroot/${SORA_PYTHON_SDK_PLATFORM}.json")
     _sora_fetch_rootfs("${_ROOTFS_DIR}" "${_SYSROOT_JSON}")
     # CMAKE_SYSROOT と _ROOTFS_DIR が一致することを sanity check
     if(NOT CMAKE_SYSROOT STREQUAL _ROOTFS_DIR)
       message(FATAL_ERROR
         "CMAKE_SYSROOT (${CMAKE_SYSROOT}) does not match _ROOTFS_DIR (${_ROOTFS_DIR}). "
         "Set SORA_PYTHON_SDK_SYSROOT_DIR env var to absolute path of _PLATFORM_ROOT/rootfs.")
     endif()
   endif()
   ```

   `CMAKE_SOURCE_DIR` は scikit-build-core 0.12 で repository root (= `<repo>`) に解決される (fetch_deps.cmake の 14 行 `set(DEPS_ROOT "${CMAKE_SOURCE_DIR}/_deps")` および 406 行 `file(READ "${CMAKE_SOURCE_DIR}/deps.json" ...)` が ubuntu-24.04_x86_64 native build で実呼び出しされており、 同じ前提で動作している)。

   sanity check で `CMAKE_SYSROOT` と `_ROOTFS_DIR` の一致を確認することで、 `SORA_PYTHON_SDK_SYSROOT_DIR` 環境変数の誤設定や CI step での値ずれを早期に検出する。

   初版は 1 platform のみのため `if STREQUAL` 1 段で実装する。 2 件目以降の cross platform を追加する後続 issue で list 化 (`set(_SORA_CROSS_PLATFORMS ...)` + `list(FIND ...)`) への refactor を別 issue として扱う。

3. `file(LOCK "${DEPS_ROOT}/.fetch.lock" ... TIMEOUT 1800)` (86 行目) の保持時間が sysroot 構築 (ubuntu-24.04_armv8 で約 5 分以内) ぶん延長されるが、 これは「複数 Python ABI 並列ビルド時に sysroot 構築を 1 回に直列化する」 設計意図と整合する (`sysroot.py` 側の stamp 機構で 2 回目以降は skip)。 TIMEOUT 1800 (30 分) は ubuntu-24.04_armv8 では十分

### pyproject.toml の cross 用 override 追加

`NB_SUFFIX` が Python ABI ごとに値が異なるため、 Python マイナーバージョン別に **3 件独立** で追加する。 `if.env.SORA_PYTHON_SDK_PLATFORM` と `if.python-version` の AND 条件で発火する:

```toml
# cross-compile (ubuntu-24.04_armv8) 用 override - Python 3.12
[[tool.scikit-build.overrides]]
if.env.SORA_PYTHON_SDK_PLATFORM = "^ubuntu-24\\.04_armv8$"
if.python-version = ">=3.12,<3.13"
inherit.cmake.define = "append"
cmake.define.SORA_PYTHON_SDK_PLATFORM = "ubuntu-24.04_armv8"
cmake.define.CMAKE_TOOLCHAIN_FILE = "cmake/toolchains/aarch64-linux-gnu.cmake"
cmake.define.CMAKE_C_COMPILER_WORKS = "TRUE"
cmake.define.CMAKE_CXX_COMPILER_WORKS = "TRUE"
cmake.define.NB_SUFFIX = ".cpython-312-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"

# cross-compile (ubuntu-24.04_armv8) 用 override - Python 3.13
[[tool.scikit-build.overrides]]
if.env.SORA_PYTHON_SDK_PLATFORM = "^ubuntu-24\\.04_armv8$"
if.python-version = ">=3.13,<3.14"
inherit.cmake.define = "append"
cmake.define.SORA_PYTHON_SDK_PLATFORM = "ubuntu-24.04_armv8"
cmake.define.CMAKE_TOOLCHAIN_FILE = "cmake/toolchains/aarch64-linux-gnu.cmake"
cmake.define.CMAKE_C_COMPILER_WORKS = "TRUE"
cmake.define.CMAKE_CXX_COMPILER_WORKS = "TRUE"
cmake.define.NB_SUFFIX = ".cpython-313-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"

# cross-compile (ubuntu-24.04_armv8) 用 override - Python 3.14
[[tool.scikit-build.overrides]]
if.env.SORA_PYTHON_SDK_PLATFORM = "^ubuntu-24\\.04_armv8$"
if.python-version = ">=3.14,<3.15"
inherit.cmake.define = "append"
cmake.define.SORA_PYTHON_SDK_PLATFORM = "ubuntu-24.04_armv8"
cmake.define.CMAKE_TOOLCHAIN_FILE = "cmake/toolchains/aarch64-linux-gnu.cmake"
cmake.define.CMAKE_C_COMPILER_WORKS = "TRUE"
cmake.define.CMAKE_CXX_COMPILER_WORKS = "TRUE"
cmake.define.NB_SUFFIX = ".cpython-314-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"
```

設計判断:

- `if.env.SORA_PYTHON_SDK_PLATFORM` は scikit-build-core 公式仕様 (https://scikit-build-core.readthedocs.io/en/latest/configuration/overrides.html ) で **正規表現 `re.search`** で評価される。 `.` をリテラルとして扱うため `\\.` (TOML 文字列内では `\` を 2 回エスケープ) で書き、 完全一致を意図するため `^...$` で anchored 化する。 0019 (closed) の TOML 書式 (`"^ubuntu-22\\.04_armv8$"`) を踏襲する。 anchored 化しないと後続 issue で `ubuntu-22.04_armv8_jetson` 等を追加した瞬間に `ubuntu-22.04_armv8` の override も同時発火するリスクがある
- `inherit.cmake.define = "append"` の挙動: 「新規キーは override に追加、 同名キーは override の値で **置換**」。 base の `TARGET_OS = "ubuntu"` (pyproject.toml の 49 行) は override で再宣言しないためそのまま使われる (ubuntu-24.04_armv8 では `TARGET_OS = "ubuntu"` で正しい)。 後続 issue (raspberry-pi-os_armv8 / jetson) では `TARGET_OS` を override 側で再宣言して置換する
- `CMAKE_C_COMPILER_WORKS = "TRUE"` / `CMAKE_CXX_COMPILER_WORKS = "TRUE"` は **必須**: `enable_language(C/CXX)` の try_compile が走る時点では host LLVM clang はまだ取得されておらず (fetch_deps.cmake の `_sora_fetch_llvm` 内で取得)、 cmake が compiler を確認しようとして fail する。 try_compile を skip させて言語有効化を進め、 fetch_deps.cmake で `CMAKE_C_COMPILER` を CACHE FORCE で確定する設計に依存する
- `if.env.SORA_PYTHON_SDK_PLATFORM` (override 発火条件) と `cmake.define.SORA_PYTHON_SDK_PLATFORM` (CMake 変数値) は役割が分離しているため、 同じ値を双方で指定するのは冗長ではあるが必須 (env は CMake 変数に自動昇格しない)
- `cmake.define.CMAKE_TOOLCHAIN_FILE` / `CMAKE_C_COMPILER_WORKS` / `CMAKE_CXX_COMPILER_WORKS` / `SORA_GEN_PYI` の 4 値は 3 件で同一だが、 Python ABI 別 override の独立性 (`NB_SUFFIX` が Python ABI 別に異なる) を保つため重複させる。 共通 override を別途追加して DRY 化することも可能だが、 `inherit.cmake.define = "append"` の重複合成挙動が複雑になるため避ける
- `NB_SUFFIX` は nanobind 公式 `cmake/nanobind-config.cmake` 内で `set_target_properties(... SUFFIX "${NB_SUFFIX}")` が呼ばれるため、 `cmake.define.NB_SUFFIX` で CMake 変数として渡せば target の `.so` suffix が確定する (CMakeLists.txt 側の追加コードは不要)
- `wheel.tags` は本 issue では指定しない (撤回された 0017 / 0019 では Python ABI 別に指定していた)。 wheel タグの確定は `_PYTHON_HOST_PLATFORM=linux-aarch64` 環境変数経由で cpython `sysconfig.get_platform()` を上書きする方式に変更する。 scikit-build-core 0.12.2 の `wheel_tag.py` は `_PYTHON_HOST_PLATFORM` を読んで `replace("-", "_")` でアンダースコア変換し、 platform tag に `linux_aarch64` を確定する。 interpreter tag と ABI tag (例: `cp312`) は **build host の `packaging.tags.sys_tags()` から取得される** ため、 cpython 3.12 / 3.13 / 3.14 (arch 非依存の interpreter/abi tag) を ubuntu-24.04 x86_64 host で使う本構成では `cp3XY-cp3XY-linux_aarch64.whl` が確定する。 将来 free-threading build (cpython 3.13t 等) を扱うときは追加指定が要る可能性がある
- `CMAKE_TOOLCHAIN_FILE` は相対パス `cmake/toolchains/aarch64-linux-gnu.cmake` で渡す。 CMake 仕様で build dir フォールバックして source dir で解決される

### .github/workflows/build.yml の改修

1. `build_ubuntu` matrix の `exclude:` (現状 118-122 行) から `ubuntu-24.04_armv8` の 1 行のみ削除。 残り 3 entry (`ubuntu-22.04_x86_64` / `ubuntu-22.04_armv8` / `raspberry-pi-os_armv8`) はそのまま
2. `build_ubuntu` job の `timeout-minutes: 15` (124 行) を `60` に引き上げる
3. 既存 x86_64 用 build step (`if: ${{ matrix.platform.arch == 'x86_64' }}`、 現状 145-146 行) はそのまま残す
4. その直後に以下を **新規追加**:

   ```yaml
   - name: Build wheel (cross ubuntu-24.04_armv8)
     if: matrix.platform.target == 'ubuntu-24.04_armv8'
     env:
       SORA_PYTHON_SDK_PLATFORM: ubuntu-24.04_armv8
       SORA_PYTHON_SDK_SYSROOT_DIR: ${{ github.workspace }}/_deps/ubuntu-24.04_armv8/rootfs
       _PYTHON_HOST_PLATFORM: linux-aarch64
     run: |
       mkdir -p "${SORA_PYTHON_SDK_SYSROOT_DIR}"
       uv build --wheel
   - name: Verify wheel architecture (cross ubuntu-24.04_armv8)
     if: matrix.platform.target == 'ubuntu-24.04_armv8'
     shell: bash
     run: |
       set -eux
       shopt -s nullglob
       ls dist/
       WHEELS=(dist/sora_sdk-*-cp*-linux_aarch64.whl)
       (( ${#WHEELS[@]} == 1 )) || { echo "ERROR: expected 1 linux_aarch64 wheel, got ${#WHEELS[@]}"; ls dist/; exit 1; }
       WHL="${WHEELS[0]}"
       mkdir -p /tmp/wheel-content
       unzip -o "$WHL" -d /tmp/wheel-content
       SO_FILES=(/tmp/wheel-content/sora_sdk/sora_sdk_ext.*.so)
       (( ${#SO_FILES[@]} == 1 )) || { echo "ERROR: expected 1 .so, got ${#SO_FILES[@]}"; ls /tmp/wheel-content/sora_sdk/; exit 1; }
       SO_FILE="${SO_FILES[0]}"
       [[ "$SO_FILE" == *"-aarch64-linux-gnu.so" ]] || { echo "ERROR: .so suffix is not -aarch64-linux-gnu: $SO_FILE"; exit 1; }
       file "$SO_FILE" | tee /tmp/file-out
       grep -E 'ELF 64-bit LSB.*ARM aarch64' /tmp/file-out
   ```

   条件は `matrix.platform.arch == 'armv8'` ではなく `matrix.platform.target == 'ubuntu-24.04_armv8'` で限定する。 `arch == 'armv8'` だと後続 issue で `raspberry-pi-os_armv8` の exclude を外したとき、 同じ step が発火して RPi 固有の `sora_sdk_rpi` rename / cross override 不一致で別の事故が起きる。 後続 issue では platform ごとに新規 step を増やす方針とする

   `SORA_PYTHON_SDK_SYSROOT_DIR` は toolchain ファイル経由で `CMAKE_SYSROOT` に渡される (前述「toolchain」 節)。 `mkdir -p` で空ディレクトリを先行作成しておくのは、 toolchain 評価時に path 存在チェックが走った場合の保険。 中身は `_sora_fetch_rootfs` 内 `sysroot.py` で構築される

   `_PYTHON_HOST_PLATFORM=linux-aarch64` を渡すことで cpython `sysconfig.get_platform()` が上書きされ、 scikit-build-core 経由で生成される wheel タグの platform 部分が `linux_aarch64` に確定する (macOS の build.yml の 336-339 行の `_PYTHON_HOST_PLATFORM=macosx-14.0-arm64` 例と同じ仕組み)

   Verify step の `shopt -s nullglob` は bash glob が 0 件マッチしたときの罠 (リテラル文字列のまま展開され配列長が 1 になる) を防ぐ。 `failglob` は使わない (array 代入は `||` で守れず sudden death するため)。 検証は 4 段:
   - wheel ファイル名末尾が `linux_aarch64.whl` であること (タグが間違って `linux_x86_64.whl` になる事故を検出)
   - 1 wheel に `.so` が 1 個だけ含まれること (cross 残骸の混入を検出)
   - `.so` ファイル名末尾が `-aarch64-linux-gnu.so` であること (`NB_SUFFIX` が反映されていない事故を検出)
   - `.so` の ELF target が aarch64 であること (host 用にフォールバックした事故を検出)

### CHANGES.md の更新

`shiguredo-changelog` 規約に従い `## develop` セクションを以下のように変更する (利用者向け wheel への影響が直接あるため `### misc` ではなく本流に置く):

1. 既存 0024 由来 `[CHANGE] cross-compile 用 sysroot 構築から multistrap を廃止する` エントリ (CHANGES.md の 20-23 行) の **2 行目** (現状 22 行 `armv8 系 cross-compile wheel は CI で生成されない (元から matrix exclude 済)`) を **削除する**。 0030 merge 後は ubuntu-24.04_armv8 が CI で生成されるようになり、 22 行目の記述は事実と矛盾するため。 0024 エントリの 1 行目 (タイトル) / 3 行目以降 / 著者 mention はそのまま残す
2. `[ADD]` グループ内、 既存の `[ADD] cross-compile 用 sysroot 構築スクリプト sysroot.py を追加する` (CHANGES.md の 24-26 行) の **直後** に以下を追加 (sysroot.py 追加と最初の cross 経路 wheel ビルド追加の関連性を読みやすくするため):

```markdown
- [ADD] ubuntu-24.04_armv8 platform の cross-compile wheel ビルドを sysroot.py 経路で追加する
  - 0024 で停止していた cross-compile wheel ビルドを scikit-build-core (cmake) → _sora_fetch_rootfs → sysroot.py 経路で再開
  - ubuntu-24.04_armv8 のみ追加、 残り 3 platform (ubuntu-22.04_armv8 / raspberry-pi-os_armv8 / ubuntu-22.04_armv8_jetson) は後続 issue で順次対応
  - wheel タグは `linux_aarch64` で artifact 化のみ。 manylinux タグ確定と PyPI publish は後続 issue で対応
  - @voluntas
```

## 完了条件

### 事前確認 (PR description に結果を記載 / macOS host で実行可能)

- `https://github.com/shiguredo/sora-cpp-sdk/releases/download/<VERSION>/sora-cpp-sdk-<VERSION>_ubuntu-24.04_armv8.tar.gz` 等 (sora-cpp-sdk / webrtc-build / boost の `ubuntu-24.04_armv8` 用 prebuilt) が `curl -fI` で 200 を返すこと (`deps.json` の `<VERSION>` を使う)

### ローカル macOS で実行可能な確認

- `uv run ruff check` / `uv run ruff format --check` が pass
- `cmake -P cmake/toolchains/aarch64-linux-gnu.cmake` で toolchain ファイルの **構文エラーが出ない** こと (関数本体のロジック検証は不可、 cmake が変数を set するだけ)
- `python3 -c "import tomllib; tomllib.loads(open('pyproject.toml','rb').read())"` で pyproject.toml の構文確認

### CI 上の反復確認 (PR 上で観察 / macOS host では実行不可)

- `sysroot/ubuntu-24.04_armv8.json` の packages (現状 `libc6-dev` / `libstdc++-13-dev` / `libxext-dev` / `libdbus-1-dev` の 4 つ) で libwebrtc + Sora C++ SDK のリンクが通るかの確認。 通らない場合は不足パッケージを `sysroot/ubuntu-24.04_armv8.json` に追加して push を繰り返す。 不足候補: `libpulse-dev` / `libnss3-dev` / `libasound2-dev` / `libudev-dev` / `libxtst-dev` / `libexpat1-dev` 等。 CI fail ログの undefined reference シンボルから逆引きする
- `_sora_fetch_rootfs` の動的検証は実機 (`runs_on: ubuntu-24.04`) でしか走らないため、 cmake 関数本体の bug (`execute_process` 引数誤り等) は CI 1 回目で初めて顕在化する可能性がある
- `CMAKE_SYSROOT` 確定戦略 (`SORA_PYTHON_SDK_SYSROOT_DIR` 環境変数経由 + `CMAKE_C_COMPILER_WORKS = "TRUE"`) で enable_language が pass することを CI 1 周目で観察。 fail した場合は環境変数 path のずれや `_sora_fetch_llvm` 内 `CMAKE_C_COMPILER` 確定タイミングの調査が必要
- CI 1 回あたりの所要時間目安: 1 Python ABI 単独で約 30 分 (sysroot 構築 5 分 + LLVM 取得 10 分 + cmake build + nanobind link + wheel 生成)。 3 Python ABI は matrix の並列実行で同時進行するため walltime は約 30 分

### CI 上で確認 (本 issue 完了条件)

- `cmake/toolchains/aarch64-linux-gnu.cmake` が新設されている
- `cmake/scripts/fetch_deps.cmake` の `_SORA_ALLOWED_PLATFORMS` に `ubuntu-24.04_armv8` が含まれている
- `cmake/scripts/fetch_deps.cmake` のメインスクリプトで cross 系 platform 時に `_sora_fetch_rootfs` が呼ばれ、 `CMAKE_SYSROOT` と `_ROOTFS_DIR` の sanity check が pass する
- `pyproject.toml` に Python 3.12 / 3.13 / 3.14 別の cross 用 `[[tool.scikit-build.overrides]]` が 3 件 (`if.env.SORA_PYTHON_SDK_PLATFORM = "^ubuntu-24\\.04_armv8$"` の anchored regex で) 追加されている
- `.github/workflows/build.yml` の `exclude:` から `ubuntu-24.04_armv8` が外れている
- `.github/workflows/build.yml` の `build_ubuntu` job に cross 用 build step / Verify step が追加され、 `timeout-minutes: 60` に変更されている
- `CHANGES.md` の `## develop` セクションに `[ADD]` エントリが既存 sysroot.py `[ADD]` の直後に追加され、 0024 由来 `[CHANGE]` エントリの 2 行目が削除されている
- CI で `ubuntu-24.04_armv8` × 3 Python (3.12 / 3.13 / 3.14) の wheel が artifact として生成され、 `build_ubuntu` job が green
- 生成された wheel ファイル名が `sora_sdk-<version>-cp3XX-cp3XX-linux_aarch64.whl` 形式
- wheel 内 `sora_sdk/sora_sdk_ext.cpython-3XX-aarch64-linux-gnu.so` の `file` 出力が `ELF 64-bit LSB shared object, ARM aarch64` を含む (Verify step で確認)

## 解決方法

1. `cmake/toolchains/aarch64-linux-gnu.cmake` を新規作成
   - `CMAKE_SYSTEM_NAME` / `CMAKE_SYSTEM_PROCESSOR` / `CMAKE_C_COMPILER_TARGET` / `CMAKE_CXX_COMPILER_TARGET` を set
   - `SORA_PYTHON_SDK_SYSROOT_DIR` 環境変数があれば `CMAKE_SYSROOT` に確定
2. `cmake/scripts/fetch_deps.cmake` を改修
   - `_SORA_ALLOWED_PLATFORMS` に `ubuntu-24.04_armv8` を追加 (エラーメッセージも同期)
   - メインスクリプトの `_sora_fetch_llvm` 直後に cross 分岐を追加し、 `_sora_fetch_rootfs` で sysroot を構築
   - sanity check は `file(REAL_PATH)` で両辺正規化したうえで `STREQUAL` 比較し、 末尾スラッシュ / シンボリックリンク差を吸収。 空 `CMAKE_SYSROOT` 検出時は明示的に `FATAL_ERROR`。 比較式の右辺は CMP0054 NEW のもとで文字列リテラル扱いされないよう明示的に `"${...}"` で展開
3. **設計変更**: `pyproject.toml` の cross 用 `[[tool.scikit-build.overrides]]` は **0 件** とし、 CI step の `CMAKE_ARGS` 環境変数で `-DCMAKE_TOOLCHAIN_FILE` / `-DSORA_PYTHON_SDK_PLATFORM` / `-DCMAKE_C_COMPILER_WORKS=TRUE` / `-DCMAKE_CXX_COMPILER_WORKS=TRUE` を直接渡す経路に変更
   - 元設計の Python ABI 別 override 3 件は、 cross platform を追加するたびに 3 倍に増えるため
   - `NB_SUFFIX` / `SORA_GEN_PYI` は `CMakeLists.txt` の cross 分岐内 (`SORA_PYTHON_SDK_PLATFORM` 単独条件) で確定。 `NB_SUFFIX` は `Python_VERSION_MAJOR` / `Python_VERSION_MINOR` から組み立てる
4. `.github/workflows/build.yml` の `build_ubuntu` を改修
   - `exclude:` から `ubuntu-24.04_armv8` を 1 行削除
   - `timeout-minutes` を 15 → 60 に引き上げ
   - cross build step (env で `SORA_PYTHON_SDK_PLATFORM` / `SORA_PYTHON_SDK_SYSROOT_DIR` / `_PYTHON_HOST_PLATFORM` / `CMAKE_ARGS` を渡す) を追加
   - Verify wheel architecture step (wheel 個数 / `.so` 個数 / `.so` suffix / ELF target の 4 段検証) を追加。 配列長判定は `[[ ... -eq ]]`、 unzip 先は `mktemp -d`、 ELF 検証は `grep -qE ... <<< "$FILE_OUT"` で fail 時のエラーメッセージを強化
5. `CHANGES.md` の `## develop` に `[ADD]` エントリを既存 sysroot.py `[ADD]` 直後に追加し、 0024 由来 `[CHANGE]` エントリの 2 行目 (`armv8 系 cross-compile wheel は CI で生成されない (元から matrix exclude 済)`) を削除。 利用者向けに PyPI publish の影響 (`pip install sora_sdk` は未対応) を明示
6. ローカル macOS で「ローカル macOS で実行可能な確認」 を実施 (`cmake -P cmake/toolchains/aarch64-linux-gnu.cmake` / `tomllib.load(pyproject.toml)` / `uv run ruff format --check` が pass、 prebuilt artifact 3 件の HTTP 200 確認)

## ロールバック

`sysroot.py` 経路 / scikit-build-core の cross override 設計 / toolchain ファイル経由の `CMAKE_SYSROOT` 確定戦略のいずれかの根本に起因する不具合で追加コミットで前進できない場合に revert を選ぶ。 個別の packages 不足 / `NB_SUFFIX` の値ミス / build step の if 条件ミス等は追加コミットで前進させる。

revert を選ぶ判断基準の例:

- sysroot 内 `lib*.so` / ヘッダの不足が体系的に発生し、 packages 追加では収束しない
- `CMAKE_C_COMPILER_WORKS = "TRUE"` で try_compile を skip しても enable_language が pass しない (cmake 内部の別チェックで fail する)
- scikit-build-core の `if.env` トリガーが anchored regex でも想定通り発火しない (scikit-build-core 自身の bug)

revert 手順:

- merge 方式に応じて以下を選ぶ:
  - PR を squash merge した場合: `git revert <merge-commit>` で revert PR を作成
  - PR を merge commit で merge した場合: `git revert -m 1 <merge-commit>` で revert PR を作成
- revert 後 develop の tree が本 PR merge 前と一致することを確認 (`git diff <merge-commit>^..HEAD` が空になる)
- CI が再び `ubuntu-24.04_x86_64` × 3 Python のみで green になることを確認 (既存挙動に戻る)

CHANGES.md の `[ADD]` エントリも `git revert` で自動で取り除かれる。 また 0024 由来 `[CHANGE]` エントリの 2 行目削除も自動で revert され、 元の 2 行目が復元される。

## 関連

- 0017 (closed): `ubuntu-24.04_armv8` を Chromium prebuilt sysroot 経路で cross-compile しようとして閉じられた issue。 本 issue と同一 platform に対する先行試行 (sysroot 取得経路のみ Chromium → sysroot.py で異なる)
- 0019 (closed): aarch64-linux cross-compile (ubuntu-22.04/24.04 系) を multistrap 経路で進めようとして閉じられた issue。 本 issue は sysroot.py 経路での再挑戦。 pyproject.toml override の `if.env` 正規表現書式 (`"^ubuntu-22\\.04_armv8$"`) と Python ABI 別 3 件独立 override の先例
- 0020 (closed): jetson / RPi platform 対応を multistrap 経路で進めようとして閉じられた issue
- 0024 (closed): sysroot.py 新設の親 issue。 本 issue で行うこと / 行わないことの境界が明示されている
- 0022 (open): レガシーファイル削除と CI 最終整理 (`auditwheel repair --strip --only-plat` 対応含む)。 本 issue で生成する `linux_aarch64.whl` の manylinux 化を担う後続 issue (0022 のスコープに `ubuntu-24.04_armv8` も含まれる)
- 0025 (open): `tests/test_sysroot.py` 新設。 本 issue とは独立 (sysroot.py 単体テストカバレッジ)
- 0026 (open): sysroot.py を ty 型チェック対象に追加。 本 issue とは独立
- 0027 (open): `_sora_fetch_rootfs` 関数をメインスクリプトを走らせずに 4 platform 一括で dry-run 検証する CI を追加する別 issue。 本 issue は ubuntu-24.04_armv8 1 platform のみを実 wheel ビルド経路で検証するため、 残り 3 platform の検証カバレッジは別途必要。 本 issue merge 後も 0027 の責務は独立に残る (verify_sysroot は sysroot.py 単体動作、 0027 は cmake 関数の dry-run、 本 issue は 1 platform を実 wheel まで、 の 3 段階責務分離)
- 0028 (open): sysroot.py の docstring 拡充。 本 issue とは独立
- 0029 (open): sysroot.py の `Repo.allow_insecure` 等の YAGNI 整理。 本 issue とは独立
