# Linux arm64 クロスコンパイル対応（ubuntu armv8）

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-crosscompile-aarch64-linux

## 目的

ubuntu-24.04 x86_64 host 上で `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` 向け wheel を `uv build --wheel` 一発で生成できる経路を 0016 で確立した scikit-build-core + `cmake/scripts/fetch_deps.cmake` 構成で実装する。 multistrap で sysroot を用意し、 0016 で取得済みの libwebrtc 同梱 clang （ host = Linux x86_64 ）を `-target aarch64-linux-gnu` でクロスコンパイルに使う。

## 設計の前提（プロジェクト全体の新方針からの該当部）

- ビルド環境は ubuntu-24.04 x86_64 host のみ
- Linux arm64 (`ubuntu-22.04_armv8` / `ubuntu-24.04_armv8`) は x86_64 host からの **sysroot クロスコンパイル**
- arm64 native runner (`ubuntu-22.04-arm` / `ubuntu-24.04-arm`) は廃止。 既存 `build_ubuntu_arm` job は 0016 で `if: false` 、 0022 で完全削除
- libwebrtc 同梱 clang バイナリは 0016 で `_sora_fetch_llvm` が host = `x86_64-Linux-24.04` 用に取得済み。 cross-compile では同じバイナリに `-target aarch64-linux-gnu` を渡す

## スコープ

含む:

- `cmake/toolchains/ubuntu-aarch64-cross.cmake` を新設し、 cross-compile 時の `CMAKE_SYSTEM_NAME` / `CMAKE_SYSTEM_PROCESSOR` / `CMAKE_*_COMPILER_TARGET` / `CMAKE_FIND_ROOT_PATH_MODE_*` のみ設定する（ `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` / `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` は `fetch_deps.cmake` 経由の cache 変数で渡る）
- `cmake/scripts/install_rootfs.sh` を新設し、 `buildbase.py:install_rootfs` (L1074-1118) 相当の処理（ multistrap 実行 + 絶対パス symlink の相対化 + `AllowInsecureRepositories=true` multistrap パッチ）を bash で移植する
- `fetch_deps.cmake` に `_sora_fetch_rootfs` を追加し、 multistrap 取得後に `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` cache 変数を `set(... CACHE PATH "" FORCE)` で渡す
- `cmake/scripts/fetch_deps.cmake` の `SORA_PYTHON_SDK_PLATFORM` 自動検出に「cache 値 / 環境変数で渡されていれば自動検出をスキップ」分岐を追加する
- `pyproject.toml` に `[[tool.scikit-build.overrides]]` を追加し、 `SORA_SDK_TARGET=ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` × Python 3.12 / 3.13 / 3.14 の **6 件の独立 override** で `wheel.tags` を 1 要素のみ指定する
- `NB_SUFFIX=.cpython-XYZ-aarch64-linux-gnu.so` を `CMakeLists.txt` の `find_package(Python)` 後に設定する
- `SORA_GEN_PYI=OFF` をクロス時 override で渡す（ pyi はクロス環境では生成できない）
- `_PYTHON_HOST_PLATFORM=linux_aarch64` 環境変数を CI で設定する（ scikit-build-core の `WheelTag.compute_best` が `_PYTHON_HOST_PLATFORM` を見るため、 `wheel.tags` 上書きとの二重指定で platform tag を強制する）
- 0016 で `build_ubuntu` matrix から exclude された `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` 系 entry を再追加する（ runs_on は ubuntu-24.04 のままで、 x86_64 host から cross-compile する）

含まない（別 issue で扱う）:

- jetson / Raspberry Pi OS 向けクロスコンパイル（ 0020 ）
- macOS / Windows native （ 0018 / 0021 ）
- pyi / py.typed の wheel 同梱経路（ 0022 で `build_pyi` 廃止後の代替経路として整理）
- PyPI publish 用 manylinux 検証 (`auditwheel show`) と publish job 復活（ 0022 ）
- `ubuntu-22.04_x86_64` の再有効化（ 0022 ）
- `build_ubuntu_arm` （ native arm64 runner ）の再有効化（新方針で廃止のため復活なし。 0022 で完全削除）

## 現状

- `run.py:283-373` のクロス用 cmake 引数生成（ L303-318 が armv8 クロス）。 `SORA_SDK_TARGET` 環境変数を `setup.py` 側で読み、 `target_platform` を上書きする
- `buildbase.py:install_rootfs` (L1074-1118) が `multistrap --no-auth -a arm64 -d <rootfs_dir> -f <conf>` 実行 + 絶対パス symlink 相対化を行う
- multistrap conf: `multistrap/ubuntu-22.04_armv8.conf` (`suite=jammy`, `libstdc++-11-dev`) / `multistrap/ubuntu-24.04_armv8.conf` (`suite=noble`, `libstdc++-13-dev`)。 `noauth=true / ignorenativearch=true` 設定済み
- `.github/workflows/build.yml:140-146` で既存 CI が以下を実行している:
  - `sudo apt-get -y install multistrap binutils-aarch64-linux-gnu`
  - `sudo sed -e 's/Apt::Get::AllowUnauthenticated=true/Apt::Get::AllowUnauthenticated=true";\n$config_str .= " -o Acquire::AllowInsecureRepositories=true/' -i /usr/sbin/multistrap`（ multistrap 本体パッチ）
- `setup.py:bdist_wheel.get_tag()` で `ubuntu-22.04_armv8` → `manylinux_2_31_aarch64` 、 `ubuntu-24.04_armv8` → `manylinux_2_35_aarch64` を強制する
- manylinux タグ番号の根拠（既存 `setup.py:27-31` を踏襲）:
  - 22.04 → `manylinux_2_31` （ Ubuntu 20.04 / Debian 11 互換）
  - 24.04 → `manylinux_2_35` （ Ubuntu 22.04 互換）
  - 実シンボル検証は 0022 で `auditwheel show` を導入して確認する
- 0016 で `SORA_PYTHON_SDK_PLATFORM` は `/etc/os-release` から自動検出される設計（ ubuntu 24.04 x86_64 のみ受け入れ）。 cross 時に `SORA_SDK_TARGET` 環境変数を見て自動検出をスキップする分岐を本 issue で追加する
- 0016 で `_SORA_CLANG_DIR = ${DEPS_ROOT}/llvm/${LLVM_HOST_KEY}/clang` が `fetch_deps.cmake` 経由で確定する（ cross 時もホスト側 clang を使うためそのまま流用）

## 設計方針

### toolchain ファイル

`cmake/toolchains/ubuntu-aarch64-cross.cmake` を新設する:

```cmake
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_CXX_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
```

toolchain ファイルでは `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` / `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` を一切触らない。 これらは `fetch_deps.cmake` 末尾の cache 変数上書きで設定する（ rootfs / clang 取得後にしか確定しないため）。

### install_rootfs.sh

`cmake/scripts/install_rootfs.sh` を新設する。 引数: `--conf <conf>` `--dest <rootfs_dir>` `--arch arm64` 。 処理:

1. `multistrap` と `binutils-aarch64-linux-gnu` の存在確認。 不在なら `apt-get -y install` を促す
2. `/usr/sbin/multistrap` の `AllowInsecureRepositories=true` パッチを冪等に適用（既に当たっていれば skip ）
3. `multistrap --no-auth -a arm64 -d <rootfs_dir> -f <conf>` を実行
4. `<rootfs_dir>` 内の絶対パス symlink を相対パスに置き換える（ `buildbase.py:install_rootfs` L1079-1100 と同等）
5. JetPack 6 系 symlink workaround（ `buildbase.py:install_rootfs` L1102-1118 ）は 0020 で扱うため本 issue では実装しない

### fetch_deps.cmake の cross 対応

- `SORA_PYTHON_SDK_PLATFORM` 算出の冒頭に「 cache 値 / 環境変数で既に設定済みなら自動検出をスキップ」分岐を追加する:

  ```cmake
  if(NOT SORA_PYTHON_SDK_PLATFORM)
    if(DEFINED ENV{SORA_SDK_TARGET})
      set(SORA_PYTHON_SDK_PLATFORM "$ENV{SORA_SDK_TARGET}" CACHE STRING "")
    else()
      # 0016 の自動検出ロジック
    endif()
  endif()
  ```

  `SORA_SDK_TARGET` は既存 `setup.py:69-79` で使われている環境変数名と一致させる（互換性のため）。

- FATAL_ERROR の許容リストに `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` を追加する
- `LLVM_HOST_KEY` は cross 時もホスト側 LLVM を使うため `x86_64-Linux-24.04` のまま（ 0016 と共有）
- `_sora_fetch_rootfs(rootfs_dir conf stamp_path)` を追加する:

  ```cmake
  function(_sora_fetch_rootfs rootfs_dir conf stamp_path)
    # conf ファイルの MD5 を stamp 値にする (buildbase.py:62 と同等)
    file(MD5 "${conf}" _conf_md5)
    if(EXISTS "${stamp_path}")
      file(READ "${stamp_path}" _existing_stamp)
      string(STRIP "${_existing_stamp}" _existing_stamp)
      if("${_existing_stamp}" STREQUAL "${_conf_md5}")
        message(STATUS "Sora deps: rootfs cache hit")
        return()
      endif()
    endif()

    if(NOT CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux")
      message(FATAL_ERROR
        "ubuntu armv8 cross-compile requires Linux host; got '${CMAKE_HOST_SYSTEM_NAME}'.")
    endif()

    message(STATUS "Sora deps: building rootfs via multistrap (conf=${conf})")
    file(REMOVE_RECURSE "${rootfs_dir}")
    execute_process(
      COMMAND bash "${CMAKE_SOURCE_DIR}/cmake/scripts/install_rootfs.sh"
        --conf "${conf}"
        --dest "${rootfs_dir}"
        --arch arm64
      RESULT_VARIABLE _r)
    if(NOT _r EQUAL 0)
      file(REMOVE_RECURSE "${rootfs_dir}")
      message(FATAL_ERROR "install_rootfs.sh failed (conf=${conf})")
    endif()
    get_filename_component(_stamp_parent "${stamp_path}" DIRECTORY)
    file(MAKE_DIRECTORY "${_stamp_parent}")
    file(WRITE "${stamp_path}" "${_conf_md5}")
  endfunction()
  ```

- メインスクリプトに以下を追加する（ `SORA_PYTHON_SDK_PLATFORM` が `ubuntu-*_armv8` のときのみ実行）:

  ```cmake
  if(SORA_PYTHON_SDK_PLATFORM MATCHES "^ubuntu-([0-9.]+)_armv8$")
    set(_ubuntu_version "${CMAKE_MATCH_1}")
    set(_rootfs_dir "${_PLATFORM_ROOT}/rootfs")
    set(_rootfs_conf "${CMAKE_SOURCE_DIR}/multistrap/${SORA_PYTHON_SDK_PLATFORM}.conf")
    _sora_fetch_rootfs("${_rootfs_dir}" "${_rootfs_conf}" "${_STAMPS_ROOT}/rootfs")
    set(CMAKE_SYSROOT       "${_rootfs_dir}" CACHE PATH "" FORCE)
    set(CMAKE_FIND_ROOT_PATH "${_rootfs_dir}" CACHE PATH "" FORCE)
  endif()
  ```

### pyproject.toml の cross override

`SORA_SDK_TARGET=ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` × Python 3.12 / 3.13 / 3.14 の 6 件 override を追加する。 各 override に `wheel.tags` を 1 要素のみ指定し、 platform tag を強制する。

```toml
# ubuntu-22.04_armv8 (manylinux_2_31_aarch64) × Python 3.12
[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^ubuntu-22\\.04_armv8$"
if.python-version = "3.12"
wheel.tags = ["cp312-cp312-manylinux_2_31_aarch64"]
cmake.define.CMAKE_TOOLCHAIN_FILE = "${PROJECT_ROOT}/cmake/toolchains/ubuntu-aarch64-cross.cmake"
cmake.define.NB_SUFFIX = ".cpython-312-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"

# ubuntu-22.04_armv8 × Python 3.13
[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^ubuntu-22\\.04_armv8$"
if.python-version = "3.13"
wheel.tags = ["cp313-cp313-manylinux_2_31_aarch64"]
cmake.define.CMAKE_TOOLCHAIN_FILE = "${PROJECT_ROOT}/cmake/toolchains/ubuntu-aarch64-cross.cmake"
cmake.define.NB_SUFFIX = ".cpython-313-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"

# ubuntu-22.04_armv8 × Python 3.14
[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^ubuntu-22\\.04_armv8$"
if.python-version = "3.14"
wheel.tags = ["cp314-cp314-manylinux_2_31_aarch64"]
cmake.define.CMAKE_TOOLCHAIN_FILE = "${PROJECT_ROOT}/cmake/toolchains/ubuntu-aarch64-cross.cmake"
cmake.define.NB_SUFFIX = ".cpython-314-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"

# ubuntu-24.04_armv8 (manylinux_2_35_aarch64) × Python 3.12 / 3.13 / 3.14
# (上 3 つと同様、manylinux タグだけ 2_35 に変える)
```

`${PROJECT_ROOT}` は scikit-build-core 提供の特殊変数（プロジェクトルートに展開される）。 6 件の冗長は許容する（ scikit-build-core の override は配列で順次適用される仕様で、 まとめて書くと条件の OR が表現できないため）。

### CMakeLists.txt の cross 対応

- `find_package(Python)` 後（既存 L40-47 周辺）に `NB_SUFFIX` を nanobind に渡す処理を追加する:

  ```cmake
  if(NB_SUFFIX)
    set_target_properties(sora_sdk_ext PROPERTIES SUFFIX "${NB_SUFFIX}")
  endif()
  ```

  既存 `run.py:318, 351, 372` で渡していた `-DNB_SUFFIX=.cpython-XYZ-aarch64-linux-gnu.so` を踏襲する。
- 既存 `CMakeLists.txt:21-38` の `if(CMAKE_CROSSCOMPILING)` ガード（ Python find のクロス対応）はそのまま動く

### CI 影響

`.github/workflows/build.yml` の `build_ubuntu` matrix に以下を **追加** する（ 0016 の `exclude:` から 2 entry を外す）:

```yaml
- name: ubuntu-22.04_armv8
  target: ubuntu-22.04_armv8
  runs_on: ubuntu-24.04         # x86_64 host で cross-compile
  os: ubuntu
  arch: armv8
- name: ubuntu-24.04_armv8
  target: ubuntu-24.04_armv8
  runs_on: ubuntu-24.04         # 同上
  os: ubuntu
  arch: armv8
```

cross-compile 用ステップ:

```yaml
- if: ${{ matrix.platform.arch == 'armv8' && matrix.platform.os == 'ubuntu' }}
  run: |
    sudo apt-get update
    sudo apt-get -y install multistrap binutils-aarch64-linux-gnu
- if: ${{ matrix.platform.arch == 'armv8' && matrix.platform.os == 'ubuntu' }}
  env:
    SORA_SDK_TARGET: ${{ matrix.platform.target }}
    _PYTHON_HOST_PLATFORM: linux_aarch64
  run: uv build --wheel
```

既存 native x86_64 step の `uv build` 行は維持する。

`build_ubuntu_arm` job (既存 L172-228) は 0016 の `if: false` のまま据え置く（ 0022 で完全削除）。 `slack_notify` には `build_ubuntu_arm` を戻さない（新方針で完全廃止のため）。

## 完了条件

- ubuntu-24.04 x86_64 host で `SORA_SDK_TARGET=ubuntu-22.04_armv8 _PYTHON_HOST_PLATFORM=linux_aarch64 uv build --wheel` が成功し、 wheel タグが `cp312-cp312-manylinux_2_31_aarch64` 等になる（ Python 3.12 / 3.13 / 3.14 × 22.04 / 24.04 = 6 通り）
- 生成された wheel 内に `sora_sdk/sora_sdk_ext.cpython-XYZ-aarch64-linux-gnu.so` が含まれる
- `file dist/sora_sdk*.whl` 相当で wheel 内 `.so` のアーキテクチャが `aarch64` であることを確認する（具体的には `unzip -p dist/*.whl 'sora_sdk/sora_sdk_ext.*.so' | file -` で `ELF 64-bit LSB shared object, ARM aarch64`）
- 2 回目以降の cross build で `_deps/ubuntu-22.04_armv8/{webrtc,sora,boost,openh264}` / `_deps/ubuntu-22.04_armv8/rootfs` が再生成されない
- CI で `build_ubuntu` matrix の armv8 entry 全 6 件（ 22.04 × 3 Python + 24.04 × 3 Python ）が green
- `slack_notify` job は `needs: [build_ubuntu]` のまま動作する（ matrix 内の追加 entry も自動的に対象になる）
- pytest 動作確認はクロスのため実行しない。 0022 で `auditwheel show` 確認に置き換える

## 解決方法

### cmake/toolchains/ubuntu-aarch64-cross.cmake

「設計方針 → toolchain ファイル」の CMake コードを新設する。

### cmake/scripts/install_rootfs.sh

「設計方針 → install_rootfs.sh」の手順を bash で実装する。 シェバン `#!/usr/bin/env bash` + `set -euo pipefail` 付き。 既存 `buildbase.py:install_rootfs` を踏襲する。

### cmake/scripts/fetch_deps.cmake

`SORA_PYTHON_SDK_PLATFORM` 算出冒頭に `SORA_SDK_TARGET` 環境変数チェック追加 + `_sora_fetch_rootfs` 関数追加 + メインスクリプトの `if(SORA_PYTHON_SDK_PLATFORM MATCHES "^ubuntu-([0-9.]+)_armv8$")` ブロック追加。

### pyproject.toml

「設計方針 → pyproject.toml の cross override」の 6 件 override を末尾に追記する。 0016 / 0018 の override は維持する。

### CMakeLists.txt

`find_package(Python)` 後に `if(NB_SUFFIX) set_target_properties(sora_sdk_ext PROPERTIES SUFFIX "${NB_SUFFIX}") endif()` を追加する。

### .github/workflows/build.yml

- `build_ubuntu.strategy.matrix.exclude` から `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` の 2 entry を削除する（ 0016 で追加した 4 entry のうち 2 entry を残す: `ubuntu-22.04_x86_64` と `raspberry-pi-os_armv8` は 0022 / 0020 で扱うので残す）
- cross-compile 用ステップ（ multistrap install + `SORA_SDK_TARGET` + `_PYTHON_HOST_PLATFORM` 付き `uv build --wheel` ）を `build_ubuntu` job に追加する。 native x86_64 step との `if:` 分岐を明示する

### CHANGES.md

`## develop` の `[CHANGE]` グループに追加:

```
- [CHANGE] Linux arm64 wheel を ubuntu-24.04 x86_64 host からのクロスコンパイルで生成するように切り替える
  - @voluntas
```

旧 `build_ubuntu_arm` （ native arm64 runner ）廃止の旨は 0022 でまとめて記載する。

## ロールバック

0019 マージ後、 armv8 wheel が壊れた場合の手順:

1. `git revert -m 1 <merge-commit>` で revert PR を作成
2. revert 後、 `build_ubuntu` matrix から armv8 entry が消えて `exclude:` に戻ること、 `multistrap` install step が消えることを確認
3. armv8 wheel publish が止まる（ 0022 の `publish_wheel` 復活までは 0016 / 0018 / 0021 完了でも publish は止まっている前提なので影響は限定的）
4. forward fix を選ぶ判断: cross-compile ステップ単位（ multistrap / fetch_deps / toolchain ） の単一不具合なら追加コミットで対応する
