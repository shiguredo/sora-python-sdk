# ubuntu armv8 クロスコンパイル対応（x86_64 ホストから aarch64 ターゲット）

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-crosscompile-aarch64-linux

## 目的

x86_64 Linux ランナー上で `ubuntu-22.04_armv8` と `ubuntu-24.04_armv8` 向け wheel を `uv build --wheel` 一発で生成できる経路を 0001 / 0002 で確立した scikit-build-core + `fetch_deps.cmake` 構成で実装する。multistrap で sysroot を用意し、libwebrtc 同梱 clang（host = Linux x86_64 用バイナリ）で `-target aarch64-linux-gnu` クロスコンパイルする。

## 優先度根拠

High。PyPI publish 対象に `ubuntu-22.04_armv8` と `ubuntu-24.04_armv8` が含まれ、CI の `build_ubuntu` matrix の armv8 entry はネイティブ arm64 ランナーではなく x86_64 ランナー上でのクロスコンパイル経路を使う（`publish_wheel` の依存先も `build_ubuntu`）。0003 が通らないと armv8 wheel の publish が止まる。

## スコープ

含む:

- `cmake/toolchains/ubuntu-aarch64-cross.cmake` を新設し、`CMAKE_SYSTEM_NAME` / `CMAKE_SYSTEM_PROCESSOR` / `CMAKE_C_COMPILER_TARGET` / `CMAKE_FIND_ROOT_PATH_MODE_*` のみ設定する（`CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` / `CMAKE_C_COMPILER` / `CLANG_DIR` は toolchain ファイルでは触らず、`fetch_deps.cmake` 経由で cache 変数として渡る）
- `cmake/scripts/install_rootfs.sh` を新設し、`buildbase.py:install_rootfs` (L1074-1118) 相当の処理（multistrap 実行 + 絶対パス symlink の相対化）を bash で移植する。`.github/workflows/build.yml:144-146` 既存の `sudo sed -e ... -i /usr/sbin/multistrap` パッチ（ports リポジトリの `AllowInsecureRepositories=true` 設定）も同スクリプト冒頭で実行する
- `fetch_deps.cmake` に `_sora_fetch_rootfs` を追加し、multistrap 取得後に `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` cache 変数を `set(... CACHE PATH "" FORCE)` で渡す
- `[tool.scikit-build.overrides]` で `SORA_SDK_TARGET=ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` × Python 3.12 / 3.13 / 3.14 の **6 件の独立 override** を書き、各 override で `wheel.tags` を 1 要素のみ指定する
- LLVM clang バイナリは host = Linux x86_64 用を `_sora_fetch_llvm(fetch_clang=TRUE)` で取得する（0002 で実装済み機能を再利用）
- `NB_SUFFIX=.cpython-XYZ-aarch64-linux-gnu.so` を `CMakeLists.txt` の `find_package(Python)` 後に設定する
- `SORA_GEN_PYI=OFF` をクロス時 override で渡す（pyi はクロス環境では生成できない）
- `_PYTHON_HOST_PLATFORM=linux_aarch64` 環境変数も CI で設定する（scikit-build-core の `WheelTag.compute_best` が `_PYTHON_HOST_PLATFORM` を見るため、`wheel.tags` 上書きと組み合わせて二重に platform tag を強制する。`wheel.tags` 動作不良時の fallback）
- 0001 で `build_ubuntu` matrix から `if: false` / exclude された `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` 系 entry を再有効化する
- `SORA_PYTHON_SDK_PLATFORM` 自動検出（0001 / 0002 実装）に「cache 値で渡されていれば自動検出をスキップ」分岐を追加する
- `_sora_fetch_rootfs` 内で `CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux"` ガードを入れ、Linux 以外ホストでは `FATAL_ERROR` で停止する

含まない（別 issue で扱う）:

- jetson / Raspberry Pi OS 向けクロスコンパイル（0004）
- macOS / Windows ネイティブビルド（0002 / 0005）
- pyi / py.typed の wheel 同梱経路（0006 で `build_pyi` 廃止後の代替 job として整理）
- PyPI publish 用 manylinux 検証 (`auditwheel show`) と publish job 復活（0006）
- `ubuntu-22.04_x86_64` 系 entry の再有効化（0005 / 0006）
- `build_ubuntu_arm`（ネイティブ arm64 runner）の再有効化（0006）

## 依存 issue への影響（事実記述）

- 0001 完了状態を前提とする。`build_pyi` job は 0001 で `if: false` 済み、各 platform job の `needs: [build_pyi]` 削除と `build_pyi` artifact ダウンロードステップ削除も 0001 で完了済み。本 issue では `needs` 関連の追加変更なし
- 0001 / 0002 で `SORA_PYTHON_SDK_PLATFORM` 自動検出に「`if(NOT SORA_PYTHON_SDK_PLATFORM)` ガード」分岐を追加する（本 issue が真の使用者）
- 0004 は本 issue の `install_rootfs.sh` と `ubuntu-aarch64-cross.cmake` を流用して jetson / RPi toolchain を作る
- 0006 polish 時に「pyi artifact 配布経路の代替（クロス wheel に native 生成 pyi を後段で同梱する CI step）」「`auditwheel show` で manylinux タグ実態検証」を解決方法に含める必要がある

## 現状

- `run.py:283-373` のクロス用 cmake 引数生成（L303-318 が armv8 クロス）
- `buildbase.py:install_rootfs` (L1074-1118) が `multistrap --no-auth -a arm64 -d <rootfs_dir> -f <conf>` 実行 + 絶対パス symlink 相対化を行う
- multistrap conf: `multistrap/ubuntu-22.04_armv8.conf` (`suite=jammy`, `libstdc++-11-dev`) / `multistrap/ubuntu-24.04_armv8.conf` (`suite=noble`, `libstdc++-13-dev`)。`noauth=true / ignorenativearch=true` 設定済み
- `.github/workflows/build.yml:140-146` で既存 CI が以下を実行している（本 issue で `install_rootfs.sh` に移植する対象）:
  - `sudo apt-get -y install multistrap binutils-aarch64-linux-gnu`
  - `sudo sed -e 's/Apt::Get::AllowUnauthenticated=true/Apt::Get::AllowUnauthenticated=true";\n$config_str .= " -o Acquire::AllowInsecureRepositories=true/' -i /usr/sbin/multistrap`（multistrap 本体パッチ）
- `setup.py:bdist_wheel.get_tag()` で `ubuntu-22.04_armv8` → `manylinux_2_31_aarch64`、`ubuntu-24.04_armv8` → `manylinux_2_35_aarch64` を強制する
- manylinux タグ番号の根拠（既存 `setup.py:27-31` をそのまま踏襲）:
  - 22.04 → `manylinux_2_31`: Ubuntu 22.04 の glibc は 2.35 だが、`manylinux_2_31`（Debian 11 / Ubuntu 20.04 互換）を選ぶことで「2.31 ホスト互換」を主張する。実シンボル検証は 0006 で `auditwheel show` を導入して確認する
  - 24.04 → `manylinux_2_35`: Ubuntu 24.04 の glibc は 2.39 だが、`manylinux_2_35`（Ubuntu 22.04 互換）を選ぶ。同上で 0006 で検証
- 0001 / 0002 で `SORA_PYTHON_SDK_PLATFORM` は `/etc/os-release` から自動検出される設計（ubuntu / Darwin のみ受け入れ）
- 0001 / 0002 で `CLANG_DIR` cache 変数が `fetch_deps.cmake` 経由で渡される設計

## 設計方針

### toolchain ファイル

- `cmake/toolchains/ubuntu-aarch64-cross.cmake` を新設。最小内容:

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

  toolchain ファイルからは `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` / `CMAKE_C_COMPILER` / `CLANG_DIR` を一切触らない。これらは `fetch_deps.cmake` 末尾の cache 変数上書きで設定する（rootfs / clang 取得後にしか確定しないため）
- toolchain ファイルは `[[tool.scikit-build.overrides]]` の `cmake.toolchain-file` で渡す。relative path 解決基準は scikit-build-core 仕様で実装時に「`pyproject.toml` 直下からの相対」「`cmake.source-dir` 基準」「絶対パス必須」のいずれかを `--toolchain` 渡し結果の `cmake --trace-expand` で確認する。動かない場合は `${PROJECT_SOURCE_DIR}/cmake/toolchains/...` 相当の絶対化を `pyproject.toml` から指定する（scikit-build-core の placeholder 展開対応状況による）

### rootfs 取得スクリプト

- `cmake/scripts/install_rootfs.sh` を新設し、引数で `<conf_path>` と `<dest_rootfs_dir>` を受け取る:

  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  conf="${1:?conf required}"
  dest="${2:?dest required}"

  # ホスト OS チェック (Linux 以外では multistrap が動かない)
  if [ "$(uname -s)" != "Linux" ]; then
    echo "install_rootfs.sh requires Linux host; got $(uname -s)" >&2
    exit 1
  fi

  # multistrap 本体パッチ (既存 build.yml:144-146 を移植)
  # ports.ubuntu.com の Release 検証で失敗するため AllowInsecureRepositories=true を強制
  if ! grep -q "AllowInsecureRepositories=true" /usr/sbin/multistrap; then
    sudo sed -e 's/Apt::Get::AllowUnauthenticated=true/Apt::Get::AllowUnauthenticated=true";\n$config_str .= " -o Acquire::AllowInsecureRepositories=true/' -i /usr/sbin/multistrap
  fi

  rm -rf "${dest}"
  multistrap --no-auth -a arm64 -d "${dest}" -f "${conf}"

  # 絶対パス symlink を相対パスに書き換える (buildbase.py:1078-1100 相当)
  # find -print0 + IFS read で改行込みパスにも対応
  find "${dest}" -type l -print0 | while IFS= read -r -d '' link; do
    target=$(readlink "${link}")
    case "${target}" in
      /*)
        full="${dest}${target}"
        if [ -e "${full}" ]; then
          rel=$(realpath --relative-to="$(dirname "${link}")" "${full}")
          ln -snf "${rel}" "${link}"
        fi
        ;;
    esac
  done
  ```

  `realpath --relative-to` は GNU coreutils 提供。Linux ホスト前提なので問題ない。`sudo sed` は冪等性のため `grep -q` でガード。CI runner（passwordless sudo 設定済み）と Docker container（root 実行）で動く

### fetch_deps.cmake への rootfs 取得追加

- `_sora_fetch_rootfs(conf_path dest stamp_path script_path)` 関数を追加:

  ```cmake
  function(_sora_fetch_rootfs conf_path dest stamp_path script_path)
    if(NOT CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux")
      message(FATAL_ERROR "armv8 cross-compile requires Linux host; got ${CMAKE_HOST_SYSTEM_NAME}")
    endif()
    file(MD5 "${conf_path}" _conf_md5)
    file(MD5 "${script_path}" _script_md5)
    set(_expected "${_conf_md5}|${_script_md5}")
    if(EXISTS "${stamp_path}")
      file(READ "${stamp_path}" _cur)
      if(_cur STREQUAL "${_expected}")
        return()
      endif()
    endif()
    execute_process(
      COMMAND bash "${script_path}" "${conf_path}" "${dest}"
      RESULT_VARIABLE _r
    )
    if(NOT _r EQUAL 0)
      message(FATAL_ERROR "Failed to fetch rootfs: 'apt install multistrap binutils-aarch64-linux-gnu' required")
    endif()
    get_filename_component(_stamp_dir "${stamp_path}" DIRECTORY)
    file(MAKE_DIRECTORY "${_stamp_dir}")
    file(WRITE "${stamp_path}" "${_expected}")
  endfunction()
  ```

  stamp に conf MD5 と `install_rootfs.sh` の MD5 の両方を `|` 区切りで書く（スクリプト変更時も再構築される）
- メインスクリプト末尾の cache 変数上書きセクションに以下を追加:

  ```cmake
  if(SORA_PYTHON_SDK_PLATFORM MATCHES "_armv8$" AND NOT SORA_PYTHON_SDK_PLATFORM MATCHES "jetson")
    _sora_fetch_rootfs(
      "${PROJECT_ROOT}/multistrap/${SORA_PYTHON_SDK_PLATFORM}.conf"
      "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/rootfs"
      "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/.stamps/rootfs"
      "${PROJECT_ROOT}/cmake/scripts/install_rootfs.sh"
    )
    set(CMAKE_SYSROOT      "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/rootfs" CACHE PATH "" FORCE)
    set(CMAKE_FIND_ROOT_PATH "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/rootfs" CACHE PATH "" FORCE)
  endif()
  ```

### `SORA_PYTHON_SDK_PLATFORM` 自動検出のバイパス

- 0001 / 0002 で実装した自動検出ロジックに `if(NOT SORA_PYTHON_SDK_PLATFORM)` ガードを追加する:

  ```cmake
  if(NOT SORA_PYTHON_SDK_PLATFORM)
    # /etc/os-release ベース自動検出（0001 / 0002 実装）
  endif()
  ```

  cache 値で渡されていれば自動検出をスキップ。これで cross 時に `cmake.define.SORA_PYTHON_SDK_PLATFORM = "ubuntu-22.04_armv8"` 等が cache に渡された状態で自動検出をバイパスできる

### pyproject.toml overrides

- `wheel.tags` は scikit-build-core 仕様上、列挙すると全要素を `.` 結合した複合タグになる（実装時に確認: `WheelWriter.basename` で `pyver = ".".join(sorted({t.interpreter for t in self.tags}))`）。単一 ABI の wheel を生成するには `wheel.tags` を **1 要素** だけ書く必要がある
- そのため `[[tool.scikit-build.overrides]]` を **6 件**（target 2 種 × Python ABI 3 種）に分けて書く:

  ```toml
  [[tool.scikit-build.overrides]]
  if.env.SORA_SDK_TARGET = "^ubuntu-22\\.04_armv8$"
  if.python-version = "==3.12.*"
  cmake.define.SORA_PYTHON_SDK_PLATFORM = "ubuntu-22.04_armv8"
  cmake.toolchain-file = "cmake/toolchains/ubuntu-aarch64-cross.cmake"
  cmake.define.SORA_GEN_PYI = "OFF"
  wheel.tags = ["cp312-cp312-manylinux_2_31_aarch64"]

  [[tool.scikit-build.overrides]]
  if.env.SORA_SDK_TARGET = "^ubuntu-22\\.04_armv8$"
  if.python-version = "==3.13.*"
  cmake.define.SORA_PYTHON_SDK_PLATFORM = "ubuntu-22.04_armv8"
  cmake.toolchain-file = "cmake/toolchains/ubuntu-aarch64-cross.cmake"
  cmake.define.SORA_GEN_PYI = "OFF"
  wheel.tags = ["cp313-cp313-manylinux_2_31_aarch64"]

  # 3.14 / 22.04 同様、ubuntu-24.04_armv8 × 3.12/3.13/3.14 同様
  ```

  実装時には DRY 化のため scikit-build-core が他の override 合成構文を持っていれば活用するが、最初は 6 件全列挙で動作確認する

- `_PYTHON_HOST_PLATFORM=linux_aarch64` 環境変数を CI step で `env:` 経由設定する。`wheel.tags` 上書きが動かない / 一部しか効かない場合の fallback 兼 scikit-build-core 内部 `WheelTag.compute_best` での platform 強制指定。0001 で macOS native 経路で `_PYTHON_HOST_PLATFORM` を使う前例はないが、scikit-build-core ソース確認で対応済み

### NB_SUFFIX と CLANG_DIR 参照

- `CMakeLists.txt` 内 `find_package(Python)` 後に追加:

  ```cmake
  if(CMAKE_CROSSCOMPILING AND CMAKE_SYSTEM_PROCESSOR STREQUAL "aarch64")
    string(REPLACE "." "" _py_nodot "${Python_VERSION_MAJOR}.${Python_VERSION_MINOR}")
    set(NB_SUFFIX ".cpython-${_py_nodot}-aarch64-linux-gnu.so")
  endif()
  ```

- `CLANG_DIR` を `fetch_deps.cmake` include 直後に参照:

  ```cmake
  if(CLANG_DIR)
    set(CMAKE_C_COMPILER "${CLANG_DIR}/bin/clang" CACHE FILEPATH "" FORCE)
    set(CMAKE_CXX_COMPILER "${CLANG_DIR}/bin/clang++" CACHE FILEPATH "" FORCE)
  endif()
  ```

  既存 `CMakeLists.txt:132-143` の ubuntu ターゲット compile options (`-nostdinc++ -isystem${LIBCXX_INCLUDE_DIR}`) はクロスでも有効

### `find_package(Python)` クロス時動作検証

- 既存 `CMakeLists.txt:21-38` の `CMAKE_FIND_ROOT_PATH_MODE_*=NEVER` 一時切替経路はそのまま再利用する
- scikit-build-core 経由で `Python_EXECUTABLE` / `Python_INCLUDE_DIR` 等のホスト Python hints が `-D` で渡される。これと既存クロス時設定の相互作用を 0003 実装 1 ステップ目で確認する:
  - `cmake -DCMAKE_TOOLCHAIN_FILE=... -DPython_EXECUTABLE=$(uv run which python) -DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=NEVER ...` の挙動を `cmake --trace-expand` で追跡
  - クロス時 `find_package(Python ... Development.Module)` が aarch64 sysroot 内の libpython を見ない（ホスト側を見る）ことを確認
  - 動かない場合は `Python_NumPy_INCLUDE_DIR` / `Python_INCLUDE_DIR` / `Python_LIBRARY` の明示的 hint 渡しを toolchain ファイルに追加

### CI 再有効化

- 0001 で `build_ubuntu` matrix から exclude された `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` を再有効化する
- 再有効化 entry の step を `uv build --wheel`（`SORA_SDK_TARGET` env + `_PYTHON_HOST_PLATFORM=linux_aarch64` env 付き）のみに変更
- 既存 `build.yml:140-146` の `multistrap install` + `sed パッチ` step は `install_rootfs.sh` 内に移植したため CI step では不要になる（ただし `sudo apt-get -y install multistrap binutils-aarch64-linux-gnu` は事前に実行する必要があるため CI step に残す）
- 0001 で `needs: [build_pyi]` を削除済みなので本 issue では `needs` 関連変更なし

## 完了条件

- x86_64 Linux ランナー（ubuntu-24.04 GitHub Actions runner）上で以下が成功する:
  - `SORA_SDK_TARGET=ubuntu-22.04_armv8 _PYTHON_HOST_PLATFORM=linux_aarch64 uv build --wheel`（Python 3.12 / 3.13 / 3.14 それぞれ）
  - `SORA_SDK_TARGET=ubuntu-24.04_armv8 _PYTHON_HOST_PLATFORM=linux_aarch64 uv build --wheel`（同上）
- 生成された wheel ファイル名が `sora_sdk-<version>-cp3XY-cp3XY-manylinux_2_31_aarch64.whl` / `sora_sdk-<version>-cp3XY-cp3XY-manylinux_2_35_aarch64.whl` になる（unzip で `*-WHEEL` 内の `Tag` 行を確認）
- 拡張モジュールが `sora_sdk_ext.cpython-3XY-aarch64-linux-gnu.so` で wheel 内 `sora_sdk/` 配下に置かれる
- wheel に pyi / py.typed が含まれない
- `_deps/<target>/{webrtc,sora,boost,openh264,rootfs}` と `_deps/llvm/x86_64-Linux-<host VERSION_ID>/{clang,libcxx,buildtools,tools}` が生成される
- 2 回目以降の `uv build --wheel` で rootfs が再構築されない（multistrap conf と `install_rootfs.sh` の MD5 stamp 一致で skip）
- 0001 の ubuntu-24.04 x86_64 native 経路に regression なし（`SORA_SDK_TARGET` 未指定で自動検出経由ビルド → `pytest tests/test_version.py` 通過）
- CI `build_ubuntu` matrix の `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` × Python 3.12 / 3.13 / 3.14 entry が green

## 解決方法

- `cmake/toolchains/ubuntu-aarch64-cross.cmake` を新設（設計方針の最小内容）
- `cmake/scripts/install_rootfs.sh` を新設し `chmod +x`（設計方針の bash 内容、sed パッチ移植含む）
- `cmake/scripts/fetch_deps.cmake`
  - `_sora_fetch_rootfs(conf_path dest stamp_path script_path)` 関数を追加（Linux ホストガード含む）
  - メインスクリプト末尾の cache 変数上書きセクションで armv8 判定の rootfs 取得と `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` cache 設定を追加
  - `SORA_PYTHON_SDK_PLATFORM` 自動検出に `if(NOT SORA_PYTHON_SDK_PLATFORM)` ガードを追加
- `CMakeLists.txt`
  - `find_package(Python)` 後にクロス時 `NB_SUFFIX` 設定ブロックを追加
  - `fetch_deps.cmake` include 直後に `if(CLANG_DIR) set(CMAKE_C_COMPILER ...) endif()` を追加
- `pyproject.toml`
  - `[[tool.scikit-build.overrides]]` を 6 件追加（22.04_armv8 / 24.04_armv8 × Python 3.12 / 3.13 / 3.14）。各 override で `wheel.tags` を 1 要素のみ指定
- `.github/workflows/build.yml`
  - `build_ubuntu` matrix の `exclude:` から `ubuntu-22.04_armv8` と `ubuntu-24.04_armv8` を除く
  - 再有効化 entry の step を `uv build --wheel` のみに変更し、env `SORA_SDK_TARGET` / `_PYTHON_HOST_PLATFORM=linux_aarch64` を設定
  - L140-146 既存の `sudo apt-get install multistrap binutils-aarch64-linux-gnu` step は残し、その直後の `sudo sed パッチ` step は `install_rootfs.sh` 内移植のため CI step から削除する
- 1 ステップ目に実装する検証コマンド: `cmake -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/ubuntu-aarch64-cross.cmake -DCMAKE_SYSROOT=/tmp/dummy_rootfs --trace-expand` で toolchain と `find_package(Python)` の相互作用を確認
- `tests/` への追加変更なし
- `CHANGES.md` 単独エントリは追加しない（0001 の `[CHANGE]` に含意される実装詳細）
