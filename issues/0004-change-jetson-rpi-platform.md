# jetson / Raspberry Pi OS 向けクロスコンパイル対応と sora_sdk_rpi パッケージ

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-jetson-rpi-platform

## 目的

x86_64 Linux ランナー上で `ubuntu-22.04_armv8_jetson` と `raspberry-pi-os_armv8` 向け wheel を `uv build --wheel` で生成できる経路を 0001 / 0002 / 0003 で確立した scikit-build-core + `fetch_deps.cmake` + `install_rootfs.sh` 構成で実装する。Raspberry Pi OS 向けは `sora_sdk_rpi` というパッケージ名で publish するため、`pyproject.toml` の `project.name` を override で切り替える経路を新設する。

## 優先度根拠

High。publish / release 対象に `raspberry-pi-os_armv8`（PyPI 上の `sora-sdk-rpi` パッケージ）と `ubuntu-22.04_armv8_jetson` が含まれる。0004 が通らないと両 wheel の publish が止まる。

## スコープ

含む:

- `cmake/toolchains/jetson-aarch64-cross.cmake` と `cmake/toolchains/raspberry-pi-os-aarch64-cross.cmake` を新設する（0003 の `ubuntu-aarch64-cross.cmake` を参考。jetson は Tegra/NVIDIA ライブラリパスを `target_link_directories` 等で追加する必要があるため別 toolchain）
- 0003 で新設した `cmake/scripts/install_rootfs.sh` を jetson / RPi conf でも呼ぶ（multistrap conf は既存 `multistrap/ubuntu-22.04_armv8_jetson.conf` / `multistrap/raspberry-pi-os_armv8.conf` をそのまま流用）
- `install_rootfs.sh` に jetson 系の `libnvbuf_fdmap.so` symlink 補完処理（`buildbase.py:1101-1117`）を追加する。RPi では不要
- `fetch_deps.cmake` の `_sora_fetch_rootfs` 呼び出しを jetson / RPi 判定で拡張する
- `[[tool.scikit-build.overrides]]` で `SORA_SDK_TARGET=ubuntu-22.04_armv8_jetson` × Python 3.10 のみ、`raspberry-pi-os_armv8` × Python 3.12 / 3.13 / 3.14 の override を追加する（jetson の Python は L4T r36 同梱の Python 3.10 固定）
- wheel タグの強制（scikit-build-core では `wheel.tags` 設定キーや `metadata.name` override が機能しないため、wheel 生成後に `wheel tags` CLI を CI step で実行して post-process する）:
  - jetson: `wheel tags --remove --platform-tag manylinux_2_17_aarch64.manylinux2014_aarch64 dist/sora_sdk-*-cp310-*.whl`（`setup.py:26` 既存値）
  - RPi: `wheel tags --remove --platform-tag manylinux_2_35_aarch64 dist/sora_sdk-*-cp3XY-*.whl`（Debian bookworm の glibc 互換ライン。既存 `setup.py:38`）
- RPi 向け `pyproject.toml` の package name を `sora_sdk_rpi` に切り替える経路:
  - scikit-build-core の `[[tool.scikit-build.overrides]] metadata.<field>` は PEP 621 `dynamic` field の provider を指定する hook で、`project.name` は PEP 621 で dynamic 不可。scikit-build-core 経由で `name` を override する手段は存在しないことが確定済み（scikit-build-core ソース確認）
  - 既存 CI（`.github/workflows/build.yml`）が採用する `sed -i 's/name = "sora_sdk"/name = "sora_sdk_rpi"/' pyproject.toml` 経路を継続採用する。0001 / 0003 の「`run.py build` を呼ばない方針」とは矛盾しない（sed は `uv build --wheel` の直前 step として走る）
  - sed step は `build_ubuntu` matrix の `if: matrix.platform.name == 'raspberry-pi-os_armv8'` ガードで RPi entry のみで実行する
- RPi wheel に `libcamerac.so` を同梱する。Sora C++ SDK の RPi 用 archive に `libcamerac.so` が含まれているため、CMake `install(FILES ${SORA_DIR}/lib/libcamerac.so DESTINATION sora_sdk)` で wheel ルートに置き、ランタイムで `RPATH=$ORIGIN` 経由でロードできるようにする
- `Sora` クラスのバージョン取得経路（`run.py:267-271` で RPi は `importlib.metadata.version('sora-sdk-rpi')` を使う）を CMake 側で再実装する。新経路では `SORA_PYTHON_SDK_VERSION` は `VERSION` ファイル直読みで両ターゲット同値（PyPI dist-info 名が異なるだけで C++ マクロは同じ）
- `_sora_fetch_llvm(fetch_clang=TRUE)` で host 用 clang を取得（0003 と同じ）
- `_sora_fetch_archive` の WebRTC / Sora / Boost / OpenH264 取得は target 別 platform 文字列で呼ぶ（`ubuntu-22.04_armv8_jetson` / `raspberry-pi-os_armv8`）
- `SORA_GEN_PYI=OFF` をクロス時 override で渡す
- `_PYTHON_HOST_PLATFORM=linux_aarch64` 環境変数を CI で設定する
- 0001 で disable された `build_ubuntu` matrix の jetson / RPi entry を再有効化する

含まない（別 issue で扱う）:

- 0003 で扱う ubuntu armv8 クロスコンパイル本体
- macOS / Windows ネイティブビルド（0002 / 0005）
- pyi / py.typed の wheel 同梱経路（0006）
- PyPI publish 用 manylinux 検証（0006）
- ネイティブ jetson / ネイティブ RPi runner での E2E テスト復活（0006 / E2E test issue で扱う）
- `Sora C++ SDK` 内 `libcamerac.so` を別経路で追加取得すること（既に Sora アーカイブに含まれる前提）

## 依存 issue への影響（事実記述）

- 0003 完了状態を前提とする。`cmake/scripts/install_rootfs.sh` と `cmake/toolchains/ubuntu-aarch64-cross.cmake`、`fetch_deps.cmake` の `_sora_fetch_rootfs` 関数、`SORA_PYTHON_SDK_PLATFORM` の cache バイパス機構を流用する
- 0006 polish 時に「`sora_sdk` と `sora_sdk_rpi` の publish 経路をそれぞれ独立して扱う」「`auditwheel show` で manylinux_2_17 / manylinux_2_35 タグ検証」を解決方法に含める必要がある

## 現状

- `run.py:333-352`（jetson）/ `run.py:353-373`（raspberry-pi-os）/ `run.py:421-424`（RPi の `libcamerac.so` コピー）でクロス用 cmake 引数生成
- `buildbase.py:install_rootfs` (L1074-1118) の L1101-1117 で jetson 系 `libnvbuf_fdmap.so` symlink 補完
- multistrap conf:
  - `multistrap/ubuntu-22.04_armv8_jetson.conf`: `suite=jammy`、`libstdc++-10-dev`、Jetson 用 nvidia リポジトリ (`https://repo.download.nvidia.com/jetson/common` r36.3) + T234 用 (`/jetson/t234` r36.3) 追加。Jetpack 6 / L4T r36 ベース
  - `multistrap/raspberry-pi-os_armv8.conf`: `suite=bookworm`（Debian 12）、`libcamera-dev` を Raspberry Pi 公式リポジトリ (`http://archive.raspberrypi.org/debian` bookworm) から取得
- `setup.py:bdist_wheel.get_tag()` で `jetson` → `manylinux_2_17_aarch64.manylinux2014_aarch64`、`raspberry-pi-os` → `manylinux_2_35_aarch64` を強制
- `setup.py:39` で RPi 用 `additional_files += ["libcamerac.so"]` を `package_data` に追加
- `run.py:267-271` で RPi 時のみ `importlib.metadata.version('sora-sdk-rpi')` を使う（パッケージ名が違うため）
- CI build.yml の RPi 経路で `sed` による `pyproject.toml` の `name` 書き換え（要 `.github/workflows/build.yml` 確認）
- jetson Python 3.10 固定（L4T r36 同梱）。issue 既存 `run.py:351` で `NB_SUFFIX=.cpython-310-aarch64-linux-gnu.so` を hardcode
- 0003 完了時点で `cmake/toolchains/ubuntu-aarch64-cross.cmake` / `cmake/scripts/install_rootfs.sh` / `_sora_fetch_rootfs` / `SORA_PYTHON_SDK_PLATFORM` cache バイパスが利用可能

## 設計方針

### toolchain ファイル

- `cmake/toolchains/jetson-aarch64-cross.cmake` を新設。0003 の `ubuntu-aarch64-cross.cmake` をベースに以下を追加:

  ```cmake
  # 0003 のベース内容を include で再利用するか、別ファイルにコピー
  set(CMAKE_SYSTEM_NAME Linux)
  set(CMAKE_SYSTEM_PROCESSOR aarch64)
  set(CMAKE_C_COMPILER_TARGET aarch64-linux-gnu)
  set(CMAKE_CXX_COMPILER_TARGET aarch64-linux-gnu)
  set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
  set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)
  set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
  set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
  # Jetson 固有の追加情報は CMakeLists.txt 側 (jetson 分岐) で対応するため、
  # toolchain ファイルではターゲットアーキ指定のみ
  ```

- `cmake/toolchains/raspberry-pi-os-aarch64-cross.cmake` も同様の最小内容で新設
- Jetson 固有設定（Tegra/NVIDIA ライブラリパス: `${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/tegra` / `/usr/lib/aarch64-linux-gnu/nvidia`、既存 `CMakeLists.txt:156-159`）は既存の `TARGET_OS=jetson` 分岐内で維持される
- RPi 固有設定（`USE_V4L2=1`、`BUILD_RPATH=$ORIGIN`、既存 `CMakeLists.txt:172-173`）も既存 `TARGET_OS=raspberry-pi-os` 分岐内で維持される
- どちらの toolchain でも `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` / `CMAKE_C_COMPILER` は触らない（`fetch_deps.cmake` で cache 上書き）

### `install_rootfs.sh` への jetson symlink 補完追加

- 0003 で新設した `cmake/scripts/install_rootfs.sh` の symlink 書き換えループ後に、jetson 系の `libnvbuf_fdmap.so` symlink 補完処理を追加する:

  ```bash
  # buildbase.py:1101-1117 相当
  # JetPack 5 系: tegra ディレクトリ
  link="${dest}/usr/lib/aarch64-linux-gnu/tegra/libnvbuf_fdmap.so"
  file="${dest}/usr/lib/aarch64-linux-gnu/tegra/libnvbuf_fdmap.so.1.0.0"
  if [ -f "${file}" ] && [ ! -e "${link}" ]; then
    ln -sf "$(basename "${file}")" "${link}"
  fi
  # JetPack 6 系: nvidia ディレクトリ
  link="${dest}/usr/lib/aarch64-linux-gnu/nvidia/libnvbuf_fdmap.so"
  file="${dest}/usr/lib/aarch64-linux-gnu/nvidia/libnvbuf_fdmap.so.1.0.0"
  if [ -f "${file}" ] && [ ! -e "${link}" ]; then
    ln -sf "$(basename "${file}")" "${link}"
  fi
  ```

  jetson 以外（ubuntu armv8 / RPi）では補完先ファイル自体が存在しないため `[ -f "${file}" ]` で skip される。条件分岐不要

### `_sora_fetch_rootfs` の jetson / RPi 拡張

- 0003 の `fetch_deps.cmake` 末尾の rootfs 取得分岐（0003 で `MATCHES "_armv8$" AND NOT MATCHES "jetson"` だったもの）を以下に書き換える:

  ```cmake
  # multistrap conf が存在する全クロスターゲットを 1 経路で扱う
  set(_conf "${PROJECT_ROOT}/multistrap/${SORA_PYTHON_SDK_PLATFORM}.conf")
  if(EXISTS "${_conf}")
    _sora_fetch_rootfs(
      "${_conf}"
      "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/rootfs"
      "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/.stamps/rootfs"
      "${PROJECT_ROOT}/cmake/scripts/install_rootfs.sh"
    )
    set(CMAKE_SYSROOT        "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/rootfs" CACHE PATH "" FORCE)
    set(CMAKE_FIND_ROOT_PATH "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/rootfs" CACHE PATH "" FORCE)
  endif()
  ```

  multistrap conf ファイルの存在自体を判定基準にすることで、`ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` / `ubuntu-22.04_armv8_jetson` / `raspberry-pi-os_armv8` すべてを統一して扱える。ubuntu native や macOS native では multistrap conf ファイルが無いため安全に skip される。0003 の `MATCHES "_armv8$" AND NOT MATCHES "jetson"` 形式は本 issue で `EXISTS` ベース判定に置き換える

### platform 文字列の認識

- 0001 / 0002 で実装した `SORA_PYTHON_SDK_PLATFORM` 自動検出は `ubuntu` / `Darwin` のみ受け入れ。cross 時は cache 経由 (`-D` override) で渡される
- jetson / RPi では `SORA_PYTHON_SDK_PLATFORM = ubuntu-22.04_armv8_jetson` / `raspberry-pi-os_armv8` を cache に渡す
- 既存 `CMakeLists.txt` の `TARGET_OS` 分岐は `jetson` / `raspberry-pi-os` を独立 OS として扱う。`TARGET_OS` cache 変数も `[[tool.scikit-build.overrides]]` で `cmake.define.TARGET_OS = "jetson"` / `"raspberry-pi-os"` 等を設定する必要がある（既存 `run.py:266` でも `-DTARGET_OS=${platform.target.os}` を渡している）
- 0001 で `TARGET_OS` を `cmake.define` で渡す経路を整備していない場合は本 issue で導入する

### pyproject.toml overrides

- `[[tool.scikit-build.overrides]]` を追加（`wheel.tags` は scikit-build-core に存在しないため指定しない。wheel タグは CI step の `wheel tags` CLI で post-process する）:

  ```toml
  # Jetson は L4T r36 同梱 Python 3.10 固定
  [[tool.scikit-build.overrides]]
  if.env.SORA_SDK_TARGET = "^ubuntu-22\\.04_armv8_jetson$"
  cmake.define.SORA_PYTHON_SDK_PLATFORM = "ubuntu-22.04_armv8_jetson"
  cmake.define.TARGET_OS = "jetson"
  cmake.toolchain-file = "cmake/toolchains/jetson-aarch64-cross.cmake"
  cmake.define.SORA_GEN_PYI = "OFF"

  [[tool.scikit-build.overrides]]
  if.env.SORA_SDK_TARGET = "^raspberry-pi-os_armv8$"
  cmake.define.SORA_PYTHON_SDK_PLATFORM = "raspberry-pi-os_armv8"
  cmake.define.TARGET_OS = "raspberry-pi-os"
  cmake.toolchain-file = "cmake/toolchains/raspberry-pi-os-aarch64-cross.cmake"
  cmake.define.SORA_GEN_PYI = "OFF"
  ```

- jetson は L4T r36 同梱 Python 3.10 固定のため、CI matrix の `python_version` を 3.10 に絞る形で「ホスト Python = ターゲット Python」を保証する（`if.python-version` を override に書かなくても CI matrix 側で限定する。`uv build --wheel` 実行時のホスト venv が Python 3.10 なら自動的に NB_SUFFIX が `.cpython-310-aarch64-linux-gnu.so` になる）
- RPi は Python 3.12 / 3.13 / 3.14 すべてサポート。CI matrix で各 Python バージョンを順に回す
- 0003 同様、env regex に `^...$` アンカーを付ける（scikit-build-core の `re.search` 仕様対応）

### RPi 用 `sora_sdk_rpi` パッケージ名切替

- scikit-build-core の `[[tool.scikit-build.overrides]]` で `metadata.name` 上書きが可能か実装時に検証する:

  ```toml
  [[tool.scikit-build.overrides]]
  if.env.SORA_SDK_TARGET = "^raspberry-pi-os_armv8$"
  metadata.name = "sora_sdk_rpi"
  ```

  scikit-build-core ソース（`SettingsReader` / `WheelMetadata`）で `metadata` 配下の上書きが override 対象か確認する。対象でない場合のフォールバック:
  - (a) `pyproject.toml` の `[project] name` を `sora_sdk` のまま残し、CI step で `uv pip install pkginfo` 等を使い wheel 内 `*.dist-info/METADATA` の `Name:` を書き換える（auditwheel repair と同じレイヤで操作する）
  - (b) RPi 専用 `pyproject_rpi.toml` を別ファイルで持ち、CI step で `cp pyproject_rpi.toml pyproject.toml` してから `uv build --wheel` する
  - (c) 既存 CI の `sed -i 's/name = "sora_sdk"/name = "sora_sdk_rpi"/' pyproject.toml` を踏襲する（最も移行コストが低い）
- 実装方針として (a) → (c) の優先順位で動作確認し、(a) が動かなければ (c) で確定する。0001 〜 0003 で「`run.py` 旧経路を 0006 で削除」と決めているため、(c) の sed 経路は CI step として残しても可（0001 / 0003 で `run.py build` を呼ばない方針と矛盾しない、`uv build --wheel` 直前の `sed` だけ）

### `libcamerac.so` 同梱

- `CMakeLists.txt` の RPi 分岐（既存 `TARGET_OS=raspberry-pi-os`）に以下を追加:

  ```cmake
  if(TARGET_OS STREQUAL "raspberry-pi-os")
    install(FILES "${SORA_DIR}/lib/libcamerac.so" DESTINATION sora_sdk)
  endif()
  ```

- 既存 `CMakeLists.txt:160-173` の RPi 分岐に `BUILD_RPATH "\$ORIGIN"` 設定があり、wheel install 後の `sora_sdk_ext.cpython-3XY-aarch64-linux-gnu.so` と同じディレクトリにある `libcamerac.so` がロードされる
- `[tool.scikit-build.wheel] exclude` から `src/sora_sdk/libcamerac.so` を除外する必要はない（source tree には元々存在しない）

### `Sora C++ SDK` のバージョン取得

- 既存 `run.py:267-271` の `importlib.metadata.version('sora-sdk-rpi')` 分岐は廃止される。新経路では `SORA_PYTHON_SDK_VERSION` を `VERSION` ファイル直読みで取得するため、`sora_sdk` / `sora_sdk_rpi` のどちらでも同じ値が C++ マクロに渡る
- PyPI 上のパッケージ名は異なるが、wheel 内 `*.dist-info/METADATA` の `Name:` だけが違い、C++ 側のバージョン文字列は同じ。これは現状の動作と一致する（`run.py:267-271` も結果として同じ値を取っている）

### CI 再有効化

- 0001 で disable された `build_ubuntu` matrix の `ubuntu-22.04_armv8_jetson` × Python 3.10 / `raspberry-pi-os_armv8` × Python 3.12 / 3.13 / 3.14 entry を再有効化する
- 再有効化 entry の step を `uv build --wheel`（`SORA_SDK_TARGET` env + `_PYTHON_HOST_PLATFORM=linux_aarch64` env 付き）のみに変更
- RPi 用に package name 切替が必要なら、`[[tool.scikit-build.overrides]] metadata.name` 動作確認結果に応じて sed step を追加 / 削除する
- `apt install multistrap binutils-aarch64-linux-gnu` step は 0003 と共通

## 完了条件

- x86_64 Linux ランナー上で以下が成功する:
  - `SORA_SDK_TARGET=ubuntu-22.04_armv8_jetson _PYTHON_HOST_PLATFORM=linux_aarch64 uv build --wheel`（Python 3.10）
  - `SORA_SDK_TARGET=raspberry-pi-os_armv8 _PYTHON_HOST_PLATFORM=linux_aarch64 uv build --wheel`（Python 3.12 / 3.13 / 3.14 それぞれ）
- jetson wheel ファイル名: `sora_sdk-<version>-cp310-cp310-manylinux_2_17_aarch64.manylinux2014_aarch64.whl`
- RPi wheel ファイル名: `sora_sdk_rpi-<version>-cp3XY-cp3XY-manylinux_2_35_aarch64.whl`
- RPi wheel 内 `sora_sdk/` 配下に `sora_sdk_ext.cpython-3XY-aarch64-linux-gnu.so` と `libcamerac.so` が含まれる
- `_deps/<target>/{webrtc,sora,boost,openh264,rootfs}` 配下が生成される。jetson rootfs では `usr/lib/aarch64-linux-gnu/{tegra,nvidia}/libnvbuf_fdmap.so` symlink が補完される
- 2 回目以降の `uv build --wheel` で rootfs 再構築なし
- 0001 ubuntu-24.04 x86_64 native / 0003 ubuntu armv8 cross に regression なし
- CI `build_ubuntu` matrix の jetson / RPi entry が green

## 解決方法

- `cmake/toolchains/jetson-aarch64-cross.cmake` / `cmake/toolchains/raspberry-pi-os-aarch64-cross.cmake` を新設（設計方針の最小内容）
- `cmake/scripts/install_rootfs.sh` に jetson 系 `libnvbuf_fdmap.so` symlink 補完処理を追加（条件付きで JetPack 5 / 6 両対応）
- `cmake/scripts/fetch_deps.cmake`
  - 末尾の rootfs 取得分岐を `if(SORA_PYTHON_SDK_PLATFORM MATCHES "_armv8" OR ... STREQUAL "raspberry-pi-os_armv8")` に拡張
- `CMakeLists.txt`
  - 既存 `TARGET_OS=raspberry-pi-os` 分岐内に `install(FILES ${SORA_DIR}/lib/libcamerac.so DESTINATION sora_sdk)` を追加
  - jetson Python 3.10 固定の `NB_SUFFIX=.cpython-310-aarch64-linux-gnu.so` 設定は 0003 で導入したクロス用 `NB_SUFFIX` 自動算出ロジックで動的に決まる（Python 3.10 venv で実行すれば 310 になる）ため特殊扱い不要
- `pyproject.toml`
  - `[[tool.scikit-build.overrides]]` を 4 件追加（jetson × 3.10、RPi × 3.12 / 3.13 / 3.14）
  - RPi 用 `metadata.name` override が scikit-build-core で動作するかを実装 1 ステップ目で検証。動かない場合は CI step で `sed` 経由に切り替える
- `.github/workflows/build.yml`
  - `build_ubuntu` matrix の `exclude:` から jetson / RPi entry を除く
  - 再有効化 entry の step を `uv build --wheel`（env 付き）に変更
  - RPi entry には `metadata.name` 動作確認結果に応じて `sed` step を追加（フォールバック時）
  - jetson は Python 3.10 専用なので matrix `python_version` を限定する
- 1 ステップ目に実装する検証: `[[tool.scikit-build.overrides]] metadata.name = "sora_sdk_rpi"` を試して `uv build --wheel` 後の `dist-info/METADATA` `Name:` が書き換わるか確認
- `tests/` 変更なし
- `CHANGES.md` 単独エントリは追加しない（0001 の `[CHANGE]` に含意。RPi の `sora_sdk_rpi` 経路は既存挙動の踏襲）
