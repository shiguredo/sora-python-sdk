# Jetson / Raspberry Pi OS 向けクロスコンパイル対応と sora_sdk_rpi パッケージ

- Priority: High
- Created: 2026-05-21
- Updated: 2026-07-16
- Model: Composer 2.5
- Branch: feature/change-jetson-rpi-platform

## 目的

ubuntu-24.04 x86_64 host 上で `ubuntu-22.04_armv8_jetson` と `raspberry-pi-os_armv8` 向け wheel を `uv build --wheel` で生成できる経路を 0001 / 0003 で確立した scikit-build-core + `fetch_deps.cmake` + `install_rootfs.sh` 構成で実装する。 Raspberry Pi OS 向けは `sora_sdk_rpi` というパッケージ名で publish するため、 `pyproject.toml` の `project.name` を CI step で sed 切替する経路を踏襲する。

## 設計の前提（プロジェクト全体の新方針からの該当部）

- ビルド環境は ubuntu-24.04 x86_64 host のみ
- jetson / raspberry-pi-os は x86_64 host からの sysroot クロスコンパイル
- arm64 native runner は廃止（ `build_ubuntu_arm` job は 0001 で build.yml から削除される。 復活はしない）
- libwebrtc 同梱 clang は 0001 で取得済み（ host = `x86_64-Linux` 。 0001 の `<host_key>` は ubuntu バージョンを含まない）。 cross 時はそれに `-target aarch64-linux-gnu` を渡す

## スコープ

含む:

- `cmake/toolchains/jetson-aarch64-cross.cmake` と `cmake/toolchains/raspberry-pi-os-aarch64-cross.cmake` を新設する（ 0003 の `ubuntu-aarch64-cross.cmake` を参考。 jetson は Tegra / NVIDIA ライブラリパスを `target_link_directories` で追加する必要があるため別 toolchain ）
- 0003 で新設した `cmake/scripts/install_rootfs.sh` を jetson / RPi conf でも呼ぶ（ multistrap conf は既存 `multistrap/ubuntu-22.04_armv8_jetson.conf` / `multistrap/raspberry-pi-os_armv8.conf` を流用する。 ただし RPi conf の `noauth=true` / `ignorenativearch=true` 欠落は 0061 が扱うため、 conf 整備は 0061 と調整する）
- `install_rootfs.sh` に jetson 系の `libnvbuf_fdmap.so` symlink 補完処理（旧 `buildbase.py:1102-1118` 。 0001 で削除されるため git 履歴参照）を追加する。 RPi では不要
- `fetch_deps.cmake` の `_sora_fetch_rootfs` 呼び出しを jetson / RPi 判定で拡張する
- `[[tool.scikit-build.overrides]]` で `SORA_SDK_TARGET=ubuntu-22.04_armv8_jetson` × Python 3.10 のみ、 `raspberry-pi-os_armv8` × Python 3.12 / 3.13 / 3.14 の override を追加する（ jetson の Python は L4T r36 同梱の Python 3.10 固定。 `requires-python = ">= 3.12"` との矛盾は 0043 が扱っており、 本 issue の jetson 部分は 0043 の方針決定を前提とする）
- wheel タグの強制（ wheel 生成後に `wheel tags` CLI を CI step で実行して post-process する）:
  - jetson: `wheel tags --remove --platform-tag manylinux_2_17_aarch64.manylinux2014_aarch64 dist/sora_sdk-*-cp310-*.whl` （旧 `setup.py:26` の値）
  - RPi: `wheel tags --remove --platform-tag manylinux_2_35_aarch64 dist/sora_sdk_rpi-*-cp3XY-*.whl` （旧 `setup.py:38` の値）
  - `wheel` パッケージは現在 dependency-groups に含まれず、 0001 で `[build-system]` からも消えるため、 post-process 方式を採る場合は `wheel` を dev dependency-group に追加する必要がある
  - なお 0003 は `wheel.tags` override + `_PYTHON_HOST_PLATFORM` の二重指定方式を採用している。 `wheel.tags` がクロス時に問題なく機能するなら 0003 方式に統一して post-process と `wheel` 依存を廃止できるため、 実装時に scikit-build-core の挙動を確認してどちらかに揃える
- RPi 向け `pyproject.toml` の package name を `sora_sdk_rpi` に切り替える経路:
  - scikit-build-core の `[[tool.scikit-build.overrides]] metadata.<field>` は PEP 621 `dynamic` field の provider を指定する hook で、 `project.name` は PEP 621 で dynamic 不可。 scikit-build-core 経由で `name` を override する手段は存在しないことが確定済み
  - 旧 CI が採用していた `sed -i 's/^name = "sora_sdk"/name = "sora_sdk_rpi"/' pyproject.toml` 経路（旧 `build.yml:131-136` 。 0001 で削除されるため git 履歴参照）を踏襲して step を新設する。 0001 / 0003 の「 `run.py build` を呼ばない方針」とは矛盾しない（ sed は `uv build --wheel` の直前 step として走る）
  - sed step は `build_ubuntu` matrix の `if: matrix.platform.name == 'raspberry-pi-os_armv8'` ガードで RPi entry のみで実行する
- RPi wheel に `libcamerac.so` を同梱する。 Sora C++ SDK の RPi 用 archive に `libcamerac.so` が含まれているため、 CMake `install(FILES ${SORA_DIR}/lib/libcamerac.so DESTINATION sora_sdk)` で wheel 内 `sora_sdk/` に置き、 ランタイムで `RPATH=$ORIGIN` 経由でロードできるようにする（ archive 同梱は実装時に `DEPS` 現在値のアーカイブで確認する）
- `Sora` クラスのバージョン取得経路（旧 `run.py:267-270` で RPi は `importlib.metadata.version('sora-sdk-rpi')` を使っていた）を CMake 側で再実装する。 新経路では `SORA_PYTHON_SDK_VERSION` は `VERSION` ファイル直読みで両ターゲット同値（ PyPI dist-info 名が異なるだけで C++ マクロは同じ）
- `_sora_fetch_archive` の WebRTC / Sora / Boost / OpenH264 取得は target 別 platform 文字列で呼ぶ（ `ubuntu-22.04_armv8_jetson` / `raspberry-pi-os_armv8` ）
- `SORA_GEN_PYI=OFF` をクロス時 override で渡す
- `_PYTHON_HOST_PLATFORM=linux_aarch64` 環境変数を CI で設定する
- 0001 で `ubuntu-24.04_x86_64` の 1 entry に縮小された `build_ubuntu` matrix に jetson / RPi の entry を新規追加する（ jetson entry は旧 build.yml にも存在しなかったため完全な新設。 RPi entry は 0001 で削除された旧 entry の scikit-build-core 経路での新設）

含まない（別 issue で扱う）:

- 0003 で扱う ubuntu armv8 クロスコンパイル本体
- macOS / Windows ネイティブビルド（ 0002 / 0005 ）
- pyi / py.typed の wheel 同梱経路（ 0006 。 `build_pyi` job 自体は 0001 で削除済み）
- PyPI publish 用 manylinux 検証（ 0006 ）
- ネイティブ jetson / ネイティブ RPi runner での E2E テスト復活（ 0006 / E2E test issue で扱う）
- `Sora C++ SDK` 内 `libcamerac.so` を別経路で追加取得すること（既に Sora アーカイブに含まれる前提）
- jetson の Python バージョン方針（ `requires-python = ">= 3.12"` と Python 3.10 の矛盾解消）の決定（ 0043 ）
- jetson 分岐の RPATH 欠落対応（ 0045 ）

## 現状

以下のレガシーファイル・旧 CI step への参照は 0001 で削除されるため、 実装時は git 履歴 (`git show <削除前コミット>:run.py` 等) で参照する:

- `run.py:332-351`（ jetson ）/ `run.py:352-372`（ raspberry-pi-os ）/ `run.py:420-423`（ RPi の `libcamerac.so` コピー）でクロス用 cmake 引数生成
- `buildbase.py:install_rootfs` (L1074-1118) の L1102-1118 で jetson 系 `libnvbuf_fdmap.so` symlink 補完（ tegra 分 L1102-1108 + JetPack 6 で tegra → nvidia リネームに伴う補完 L1110-1118 ）
- `setup.py:26` で `ubuntu-22.04_armv8_jetson` → `manylinux_2_17_aarch64.manylinux2014_aarch64` を強制
- `setup.py:38` で `raspberry-pi-os_armv8` → `manylinux_2_35_aarch64` を強制
- 旧 `build.yml:131-136` で `if: matrix.platform.name == 'raspberry-pi-os_armv8'` の sed が `pyproject.toml` の `name = "sora_sdk"` を `name = "sora_sdk_rpi"` に書き換えていた

現存するファイル・関連 issue:

- multistrap conf:
  - `multistrap/ubuntu-22.04_armv8_jetson.conf`: `suite=jammy`、 `libstdc++-10-dev`、 Jetson 用 nvidia リポジトリ (`https://repo.download.nvidia.com/jetson/common` r36.3) + T234 用 (`/jetson/t234` r36.3)。 Jetpack 6 / L4T r36 ベース
  - `multistrap/raspberry-pi-os_armv8.conf`: `suite=bookworm`（ Debian 12 ）、 `libcamera-dev` を Raspberry Pi 公式リポジトリ (`http://archive.raspberrypi.org/debian` bookworm) から取得。 `noauth=true` / `ignorenativearch=true` の欠落は 0061 が扱う
- 現行 build.yml の `build_ubuntu` matrix に jetson entry は存在しない（ jetson wheel を作る job は現行 CI に無い）
- `pyproject.toml` は `requires-python = ">= 3.12"` / classifiers 3.12-3.14 のみで、 jetson の Python 3.10 wheel とは矛盾する。 この矛盾は 0043 が issue 化しており、 本 issue の jetson 部分は 0043 の方針決定に依存する

## 設計方針

### toolchain ファイル

`cmake/toolchains/jetson-aarch64-cross.cmake`:

```cmake
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_CXX_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
# Jetson の Python は sysroot 内 Python 3.10
set(_SORA_JETSON_TOOLCHAIN TRUE)
```

`_SORA_JETSON_TOOLCHAIN` は `CMakeLists.txt` 側で `target_link_directories(... ${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/tegra ${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/nvidia)` を有効化するフラグ（既存 `CMakeLists.txt:148-151` の jetson 経路に倣う）。

`cmake/toolchains/raspberry-pi-os-aarch64-cross.cmake`:

```cmake
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_CXX_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
set(_SORA_RPI_TOOLCHAIN TRUE)
```

`_SORA_RPI_TOOLCHAIN` は `libcamerac.so` 同梱と `BUILD_RPATH "\$ORIGIN"` 設定の有効化フラグ（既存 `CMakeLists.txt:164-165` ）。

### install_rootfs.sh の jetson 対応

`cmake/scripts/install_rootfs.sh` に以下を追加する:

- `--arch arm64 --jetson` フラグを受け取る
- multistrap 実行後に jetson 用 `libnvbuf_fdmap.so` symlink を補完する（旧 `buildbase.py:1102-1118` 移植。 git 履歴参照）:
  ```bash
  if [[ "${JETSON:-false}" == "true" ]]; then
    link="${ROOTFS_DIR}/usr/lib/aarch64-linux-gnu/tegra/libnvbuf_fdmap.so"
    file="${ROOTFS_DIR}/usr/lib/aarch64-linux-gnu/tegra/libnvbuf_fdmap.so.1.0.0"
    if [[ -f "${file}" && ! -e "${link}" ]]; then
      ln -s "$(basename "${file}")" "${link}"
    fi
    # JetPack 6 で tegra → nvidia リネームに伴う補完
    nvidia_link="${ROOTFS_DIR}/usr/lib/aarch64-linux-gnu/nvidia/libnvbuf_fdmap.so"
    nvidia_file="${ROOTFS_DIR}/usr/lib/aarch64-linux-gnu/nvidia/libnvbuf_fdmap.so.1.0.0"
    if [[ -f "${nvidia_file}" && ! -e "${nvidia_link}" ]]; then
      ln -s "$(basename "${nvidia_file}")" "${nvidia_link}"
    fi
  fi
  ```

### fetch_deps.cmake の jetson / RPi 対応

メインスクリプトの `if(SORA_PYTHON_SDK_PLATFORM MATCHES "^ubuntu-([0-9.]+)_armv8$")` 分岐の次に以下を追加する（ rootfs / stamp のパスは 0003 と同じく 0001 のレイアウト `_deps/<platform>/` に従う）:

```cmake
if(SORA_PYTHON_SDK_PLATFORM STREQUAL "ubuntu-22.04_armv8_jetson")
  set(_rootfs_dir "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/rootfs")
  set(_rootfs_conf "${CMAKE_SOURCE_DIR}/multistrap/${SORA_PYTHON_SDK_PLATFORM}.conf")
  _sora_fetch_rootfs("${_rootfs_dir}" "${_rootfs_conf}" "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/.stamps/rootfs" JETSON)
  set(CMAKE_SYSROOT       "${_rootfs_dir}" CACHE PATH "" FORCE)
  set(CMAKE_FIND_ROOT_PATH "${_rootfs_dir}" CACHE PATH "" FORCE)
elseif(SORA_PYTHON_SDK_PLATFORM STREQUAL "raspberry-pi-os_armv8")
  set(_rootfs_dir "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/rootfs")
  set(_rootfs_conf "${CMAKE_SOURCE_DIR}/multistrap/${SORA_PYTHON_SDK_PLATFORM}.conf")
  _sora_fetch_rootfs("${_rootfs_dir}" "${_rootfs_conf}" "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/.stamps/rootfs")
  set(CMAKE_SYSROOT       "${_rootfs_dir}" CACHE PATH "" FORCE)
  set(CMAKE_FIND_ROOT_PATH "${_rootfs_dir}" CACHE PATH "" FORCE)
endif()
```

`_sora_fetch_rootfs` の 4 番目引数（オプション `JETSON` ）は 0003 で導入したシグネチャに追加する:

```cmake
function(_sora_fetch_rootfs rootfs_dir conf stamp_path)
  cmake_parse_arguments(_arg "JETSON" "" "" ${ARGN})
  # ... 0003 の処理 ...
  # install_rootfs.sh 呼び出し時に JETSON フラグを渡す
  set(_jetson_arg "")
  if(_arg_JETSON)
    set(_jetson_arg "--jetson")
  endif()
  execute_process(
    COMMAND bash "${CMAKE_SOURCE_DIR}/cmake/scripts/install_rootfs.sh"
      --conf "${conf}"
      --dest "${rootfs_dir}"
      --arch arm64
      ${_jetson_arg}
    RESULT_VARIABLE _r)
  # ...
endfunction()
```

許容 `SORA_PYTHON_SDK_PLATFORM` リストに `ubuntu-22.04_armv8_jetson` / `raspberry-pi-os_armv8` を追加する。

### CMakeLists.txt の jetson / RPi 対応

既存 `CMakeLists.txt:136-151` の jetson 分岐と `:152-165` の raspberry-pi-os 分岐は **TARGET_OS が "jetson" / "raspberry-pi-os" のときに有効化される** 仕組み。 0001 で `TARGET_OS = "ubuntu"` をデフォルト設定したため、 cross 時は override で上書きする必要がある。

`pyproject.toml` 側で:

```toml
[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^ubuntu-22\\.04_armv8_jetson$"
cmake.define.TARGET_OS = "jetson"

[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^raspberry-pi-os_armv8$"
cmake.define.TARGET_OS = "raspberry-pi-os"
```

を追加する。

RPi 向けに `CMakeLists.txt:152-165` の既存ロジックを利用しつつ、 `libcamerac.so` を wheel に同梱する `install` 命令を追加する:

```cmake
if(_SORA_RPI_TOOLCHAIN)
  install(FILES "${SORA_DIR}/lib/libcamerac.so" DESTINATION sora_sdk)
endif()
```

### pyproject.toml の jetson / RPi override

```toml
# Jetson × Python 3.10 のみ
[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^ubuntu-22\\.04_armv8_jetson$"
cmake.define.TARGET_OS = "jetson"
cmake.define.CMAKE_TOOLCHAIN_FILE = "${PROJECT_ROOT}/cmake/toolchains/jetson-aarch64-cross.cmake"
cmake.define.NB_SUFFIX = ".cpython-310-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"

# RPi × Python 3.12 / 3.13 / 3.14 (3 件)
[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^raspberry-pi-os_armv8$"
if.python-version = "3.12"
cmake.define.TARGET_OS = "raspberry-pi-os"
cmake.define.CMAKE_TOOLCHAIN_FILE = "${PROJECT_ROOT}/cmake/toolchains/raspberry-pi-os-aarch64-cross.cmake"
cmake.define.NB_SUFFIX = ".cpython-312-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"

# (Python 3.13 / 3.14 用 2 件は同様)
```

`wheel.tags` は scikit-build-core 側では指定せず、 CI step で `wheel tags --remove --platform-tag ... dist/*.whl` で post-process する（ `wheel` を dev dependency-group に追加する。 0003 の `wheel.tags` override 方式で足りることが確認できた場合はそちらに統一する）。

### CI 影響

`.github/workflows/build.yml` の `build_ubuntu` matrix （ 0001 で `ubuntu-24.04_x86_64` の 1 entry に縮小済み。 0003 で ubuntu armv8 の 2 entry が追加される）:

- `raspberry-pi-os_armv8` entry を新規追加する
- jetson 用 entry を新規追加する:

  ```yaml
  - name: ubuntu-22.04_armv8_jetson
    target: ubuntu-22.04_armv8_jetson
    runs_on: ubuntu-24.04
    os: jetson
    arch: armv8
  ```

  Jetson は Python 3.10 固定のため `python_version` matrix も `3.10` 限定で別 matrix 軸を作るか、 entry に `python_version: '3.10'` を埋め込む形にする（ 0043 の方針決定が前提）。

cross 用ステップ（ ubuntu armv8 用の multistrap install / build step は 0003 が追加するため、 本 issue の step は jetson / raspberry-pi-os のみを対象にして二重実行を避ける）:

```yaml
- if: ${{ matrix.platform.os == 'jetson' || matrix.platform.os == 'raspberry-pi-os' }}
  run: |
    sudo apt-get update
    sudo apt-get -y install multistrap binutils-aarch64-linux-gnu
- if: ${{ matrix.platform.name == 'raspberry-pi-os_armv8' }}
  run: sed -i 's/^name = "sora_sdk"/name = "sora_sdk_rpi"/' pyproject.toml
- if: ${{ matrix.platform.os == 'jetson' || matrix.platform.os == 'raspberry-pi-os' }}
  env:
    SORA_SDK_TARGET: ${{ matrix.platform.target }}
    _PYTHON_HOST_PLATFORM: linux_aarch64
  run: |
    uv build --wheel
    # wheel タグ post-process
    if [ "${{ matrix.platform.os }}" = "jetson" ]; then
      uv run wheel tags --remove --platform-tag manylinux_2_17_aarch64.manylinux2014_aarch64 dist/sora_sdk-*-cp310-*.whl
    elif [ "${{ matrix.platform.os }}" = "raspberry-pi-os" ]; then
      uv run wheel tags --remove --platform-tag manylinux_2_35_aarch64 dist/sora_sdk_rpi-*-cp3*.whl
    fi
```

## 完了条件

- ubuntu-24.04 x86_64 host で `SORA_SDK_TARGET=ubuntu-22.04_armv8_jetson uv python pin 3.10 && uv venv && uv build --wheel` が成功し、 post-process 後の wheel タグが `cp310-cp310-manylinux_2_17_aarch64.manylinux2014_aarch64` になる（ `requires-python = ">= 3.12"` との矛盾解消は 0043 に依存。 0043 の方針が決まるまでこの手順は検証できない）
- ubuntu-24.04 x86_64 host で `SORA_SDK_TARGET=raspberry-pi-os_armv8` × Python 3.12 / 3.13 / 3.14 で `uv build --wheel` が成功し、 wheel 名が `sora_sdk_rpi-*-cp3XY-cp3XY-manylinux_2_35_aarch64.whl` になる
- RPi wheel 内に `sora_sdk/libcamerac.so` が含まれる（ `unzip -l dist/sora_sdk_rpi-*.whl | grep libcamerac.so` で確認）
- Jetson wheel 内に `sora_sdk/sora_sdk_ext.cpython-310-aarch64-linux-gnu.so` が含まれる
- 2 回目以降の cross build で `_deps/ubuntu-22.04_armv8_jetson/rootfs` / `_deps/raspberry-pi-os_armv8/rootfs` が再生成されない
- CI で `build_ubuntu` matrix の jetson / RPi entry が green になる

## 解決方法

### cmake/toolchains/jetson-aarch64-cross.cmake / raspberry-pi-os-aarch64-cross.cmake

「設計方針 → toolchain ファイル」のコードを新設する。

### cmake/scripts/install_rootfs.sh

「設計方針 → install_rootfs.sh の jetson 対応」の `--jetson` フラグと `libnvbuf_fdmap.so` symlink 補完を追加する。 RPi は 0003 のシンプル版で動作する。

### cmake/scripts/fetch_deps.cmake

- 許容 `SORA_PYTHON_SDK_PLATFORM` リストに 2 値追加
- `_sora_fetch_rootfs` シグネチャに `JETSON` キーワード引数追加
- メインスクリプトに jetson / RPi 分岐追加

### CMakeLists.txt

- 既存 `:136-151` （ jetson ）と `:152-165` （ raspberry-pi-os ）の分岐はそのまま使う（ jetson 分岐の RPATH 欠落は 0045 が扱う）
- `_SORA_RPI_TOOLCHAIN` が立っているときに `install(FILES "${SORA_DIR}/lib/libcamerac.so" DESTINATION sora_sdk)` を追加する

### pyproject.toml

「設計方針 → pyproject.toml の jetson / RPi override 」の 4 件 override を末尾に追加する。 post-process 方式を採る場合は `wheel` を dev dependency-group に追加する。

### .github/workflows/build.yml

- `build_ubuntu.strategy.matrix.platform` に `raspberry-pi-os_armv8` と jetson の entry を新規追加し、 jetson は Python 3.10 限定で動かす
- sed step を新設する（旧 `build.yml:131-136` の step を踏襲。 RPi entry のみで動くガード付き）
- cross 用 build step と wheel タグ post-process step を追加する（ jetson / raspberry-pi-os のみ対象。 ubuntu armv8 は 0003 の step が担当）

### CHANGES.md

`## develop` の `[CHANGE]` グループに追加:

```
- [CHANGE] Jetson / Raspberry Pi OS wheel を ubuntu-24.04 x86_64 host からのクロスコンパイルで生成するように切り替える
  - @voluntas
```

## ロールバック

0004 マージ後に jetson / RPi wheel が壊れた場合:

1. `git revert -m 1 <merge-commit>` で revert PR を作成
2. revert 後、 `build_ubuntu` matrix から jetson / RPi entry が消えるか確認
3. `_deps/ubuntu-22.04_armv8_jetson/` / `_deps/raspberry-pi-os_armv8/` 配下のキャッシュは残っても問題ない（次回 build まで参照されない）
4. PyPI 上の `sora-sdk-rpi` パッケージ publish が止まる（ 0006 の publish 再構築までは止まっている前提のため影響は限定的）
