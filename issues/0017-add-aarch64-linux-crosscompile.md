# ubuntu-24.04 arm64 のクロスコンパイル経路追加（Chromium sysroot）

- Priority: High
- Created: 2026-05-22
- Completed: -
- Model: Composer 2.5
- Branch: feature/add-aarch64-linux-crosscompile

## 目的

0016 で確立した scikit-build-core + `fetch_deps.cmake` 経路に **最小限の差分** で `aarch64-linux-gnu` クロスコンパイル経路を足し、 ubuntu-24.04 x86_64 host から `ubuntu-24.04_armv8` 用 wheel を `uv build --wheel` 一発で生成できる状態にする。 既存 multistrap 経路は本 issue で **使わない**（multistrap は upstream で非推奨）。 代わりに libwebrtc が内部で使っているのと同じ Chromium prebuilt sysroot を `_deps/sysroots/<key>/` に取得する。

本 issue は cross 系統 (0019 ubuntu-22.04 armv8 / 0020 jetson + raspberry-pi-os) の共通基盤として「sysroot 取得 + toolchain + override」 の最小セットを確立する位置付け。

## 優先度根拠

- 後続 issue 0019 / 0020 が本 issue の `_sora_fetch_sysroot` と `cmake/toolchains/aarch64-linux-cross.cmake` を流用する。 本 issue が先行しないと、 0019 / 0020 で同じ仕組みを 2 度書き直すことになる。
- 旧方針 (multistrap + arm64 native runner) は新方針で廃止される。 sysroot ベース cross への移行は他 platform より優先度が高い。
- 0016 の「最小限の差分で済む」 cross 経路（toolchain と sysroot の追加のみ。 OpenH264 / WebRTC / Sora / Boost / LLVM の取得経路は 0016 の `_sora_fetch_archive` をそのまま流用）であり、 cross 系統の中で最も低リスク。

## スコープ

含む:

- `cmake/toolchains/aarch64-linux-cross.cmake` を新設する。 `CMAKE_SYSTEM_NAME=Linux` / `CMAKE_SYSTEM_PROCESSOR=aarch64` / `CMAKE_C_COMPILER_TARGET=aarch64-linux-gnu` / `CMAKE_CXX_COMPILER_TARGET=aarch64-linux-gnu` / `CMAKE_FIND_ROOT_PATH_MODE_*` のみ設定する。 `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` / `CMAKE_C(XX)_COMPILER` は触らず `fetch_deps.cmake` 経由で渡す。
- `fetch_deps.cmake` に `_sora_fetch_sysroot(arch dest_root stamp_path)` を追加する。 WebRTC アーカイブ内 `VERSIONS` から `WEBRTC_SRC_BUILD_URL` / `WEBRTC_SRC_BUILD_COMMIT` を取り出し、 `build` リポジトリを shallow clone した上で `build/linux/sysroot_scripts/install-sysroot.py --arch=arm64` を `Python_EXECUTABLE` で実行する。 取得結果は `<dest_root>/debian_<codename>_arm64-sysroot/` に展開される。 `<key>` は host key（`x86_64-Linux` 等）とは独立に、 chromium の `<commit>+arm64` ベースの stable key にする（後述）。
- `fetch_deps.cmake` の `SORA_PYTHON_SDK_PLATFORM` 自動検出を変更し、 環境変数 `SORA_SDK_TARGET` が設定されている場合は自動検出をスキップしてその値を採用する（既存 `setup.py:69-79` で使われている環境変数名と一致させる）。
- `fetch_deps.cmake` の許容リストに `ubuntu-24.04_armv8` を追加。
- `fetch_deps.cmake` 末尾の出力契約に `CMAKE_SYSROOT` と `CMAKE_FIND_ROOT_PATH` を追加（cross 時のみ FORCE で設定）。 host build 時は両方とも触らない。
- `CMakeLists.txt` の `find_package(Python ...)` 直後に `if(NB_SUFFIX) set_target_properties(sora_sdk_ext PROPERTIES SUFFIX "${NB_SUFFIX}") endif()` を追加する。
- `pyproject.toml` の `[[tool.scikit-build.overrides]]` に `SORA_SDK_TARGET = "^ubuntu-24\\.04_armv8$"` × Python 3.12 / 3.13 / 3.14 の **3 件独立 override** を追加する。 各 override は次を設定する: `cmake.define.CMAKE_TOOLCHAIN_FILE = "${PROJECT_ROOT}/cmake/toolchains/aarch64-linux-cross.cmake"` / `cmake.define.NB_SUFFIX = ".cpython-3XY-aarch64-linux-gnu.so"` / `cmake.define.SORA_GEN_PYI = "OFF"` / `wheel.tags = ["cp3XY-cp3XY-manylinux_2_35_aarch64"]`。
- 0016 で `build_ubuntu` matrix から exclude された `ubuntu-24.04_armv8` を再追加し、 runs_on は `ubuntu-24.04` のまま (x86_64 host で cross-compile)。 step に `env: SORA_SDK_TARGET / _PYTHON_HOST_PLATFORM=linux_aarch64` を渡す。

含まない（別 issue で扱う）:

- ubuntu-22.04 armv8 cross（0019。 manylinux_2_31_aarch64 タグおよび 22.04 用 sysroot の追加。 本 issue で確立する仕組みの再利用）。
- jetson / raspberry-pi-os cross（0020。 Tegra / RPi 固有の rootfs と Boost / Sora アーカイブ + libcamerac.so 同梱）。
- macOS arm64 native（0018）/ Windows native（0021）。
- レガシーファイル削除と `build_ubuntu_arm` 完全削除（0022）。
- `auditwheel show` での実シンボル検証（0022）。
- PyPI publish 復活（0022）。 本 issue 完了時点でも `tags/202*` を打たない運用を継続する。
- `cmake/scripts/install_rootfs.sh` の新設（multistrap 経路は新方針で廃止）。

## 現状

- 既存 `run.py:283-318` の armv8 クロス用 cmake 引数 + `buildbase.py:install_rootfs` の multistrap 呼び出しが arm64 sysroot の取得を担っていた。
- 既存 `setup.py:bdist_wheel.get_tag()` が `ubuntu-24.04_armv8 → manylinux_2_35_aarch64` を強制していた。
- multistrap は Debian / Ubuntu でメンテナンスが滞っており、 upstream で非推奨方針。 また `Acquire::AllowInsecureRepositories=true` パッチで multistrap 本体に sed を当てる運用は脆い。
- 一方 libwebrtc (`shiguredo-webrtc-build` で配布される) は内部で Chromium 標準の `build/linux/sysroot_scripts/install-sysroot.py` を使って prebuilt sysroot tarball （commondatastorage.googleapis.com/chrome-linux-sysroot/）を取得している。 同じ sysroot を借用すれば libwebrtc / sora-cpp-sdk ABI と完全に整合する。
- 0016 完了時点で `_deps/<platform>/webrtc/VERSIONS` から `WEBRTC_SRC_BUILD_URL` / `WEBRTC_SRC_BUILD_COMMIT` が取れる（`_sora_fetch_llvm` で既に同じファイルを読んでいる）。 これを `_sora_fetch_sysroot` でも使える。
- 0016 で `_PYTHON_HOST_PLATFORM` は native では設定不要、 cross 時は CI 環境変数で設定する方針を予告済み。

## 設計方針

### レイアウト

| 種別 | パス |
| --- | --- |
| target 別 deps | `_deps/<platform>/{webrtc,sora,boost,openh264}` |
| host 別 LLVM | `_deps/llvm/<host_key>/{clang,libcxx}` |
| **arch 別 sysroot** | **`_deps/sysroots/<sysroot_key>/`** |

`<sysroot_key>` は Chromium が公開する sysroot tarball を一意に指す形式とし、 `_sora_fetch_sysroot` が決める。 内部実装としては `install-sysroot.py` の出力先（`<build clone>/linux/debian_<codename>_arm64-sysroot/`）の親ディレクトリ名（codename + arch、 例 `debian_bookworm_arm64`）を `<sysroot_key>` として採用する。 codename は libwebrtc の `build` リポジトリのバージョンに紐付くため、 WebRTC バージョン更新時に自動追従する。

### toolchain ファイル

`cmake/toolchains/aarch64-linux-cross.cmake`:

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

toolchain ファイル自体では `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` / `CMAKE_C(XX)_COMPILER` を **触らない**。 sysroot は fetch 後にしか確定しないため `fetch_deps.cmake` 末尾の CACHE 上書きに任せる。

### fetch_deps.cmake の cross 対応

- `SORA_PYTHON_SDK_PLATFORM` 自動検出の冒頭に「環境変数 `SORA_SDK_TARGET` が設定されていれば自動検出スキップ」 分岐を追加する:

  ```cmake
  if(NOT SORA_PYTHON_SDK_PLATFORM)
    if(DEFINED ENV{SORA_SDK_TARGET})
      set(SORA_PYTHON_SDK_PLATFORM "$ENV{SORA_SDK_TARGET}" CACHE STRING "" FORCE)
    else()
      # 0016 の /etc/os-release 経由自動検出
    endif()
  endif()
  ```

  `SORA_SDK_TARGET` は既存 `setup.py:69-79` で使われていた環境変数名と一致させる。
- 許容リストに `ubuntu-24.04_armv8` を追加。
- `LLVM_HOST_KEY` は cross 時も `${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}` のまま（host 側 LLVM を流用するため）。
- 新規 `_sora_fetch_sysroot(arch dest_root stamp_path)`:
  - WebRTC アーカイブ展開後の `<platform>/webrtc/VERSIONS` から `WEBRTC_SRC_BUILD_URL` と `WEBRTC_SRC_BUILD_COMMIT` を取り出す（`_sora_fetch_llvm` 内のキー抽出処理を関数化して共用するか、 同じ regex を再利用する）。
  - stamp 値は `"${url}.${commit}.${arch}"` の連結。
  - skip しない場合は `dest_root/build` を `_sora_git_shallow` で clone し、 `${Python_EXECUTABLE}` で `${dest_root}/build/linux/sysroot_scripts/install-sysroot.py --arch=${arch}` を `WORKING_DIRECTORY ${dest_root}/build` で実行する。 出力先は `${dest_root}/build/linux/debian_<codename>_<arch>-sysroot/` に展開される（codename は install-sysroot.py が決める）。
  - 展開ディレクトリを `<sysroot_key>` ディレクトリにリネーム（`get_filename_component` + `file(RENAME)` で固定の参照パスにする）。 失敗時は `<dest_root>` を削除して FATAL_ERROR。
  - `_sora_git_shallow` で clone した `build` リポジトリは sysroot 展開後に削除して容量節約。
  - stamp 書き込みは処理成功後。
- メインスクリプトの呼び出し順序: 0016 の (1)〜(6) に加えて、 cross 時 (`SORA_PYTHON_SDK_PLATFORM` が arm64 系) のみ webrtc fetch 後（VERSIONS を読める状態）に `_sora_fetch_sysroot("arm64" "${DEPS_ROOT}/sysroots" "${SYSROOT_STAMPS_ROOT}/sysroot-arm64")` を呼ぶ。 出力契約に `CMAKE_SYSROOT` と `CMAKE_FIND_ROOT_PATH` を追加し、 取得した sysroot ディレクトリを `set(... CACHE PATH "" FORCE)` する。 native 時は両方とも設定しない。

### pyproject.toml の cross overrides

```toml
[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^ubuntu-24\\.04_armv8$"
if.python-version = "3.12"
cmake.define.CMAKE_TOOLCHAIN_FILE = "${PROJECT_ROOT}/cmake/toolchains/aarch64-linux-cross.cmake"
cmake.define.NB_SUFFIX = ".cpython-312-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"
wheel.tags = ["cp312-cp312-manylinux_2_35_aarch64"]
```

Python 3.13 / 3.14 用にも同じ形で計 3 件記述する（scikit-build-core の override は OR 条件をサポートしないため独立 3 件で書く）。 `${PROJECT_ROOT}` は scikit-build-core が解決するプロジェクトルートプレースホルダ。

`wheel.tags` を 1 要素のみで指定するのは、 scikit-build-core の `WheelTag.compute_best` が `_PYTHON_HOST_PLATFORM` 環境変数も見るため二重指定で確実に platform tag を強制する。 CI 側で `_PYTHON_HOST_PLATFORM=linux_aarch64` を必ず渡す。

### CMakeLists.txt の cross 対応

- `find_package(Python ...)` の直後（既存 L17-47 の後）に次を追加:
  ```cmake
  if(NB_SUFFIX)
    set_target_properties(sora_sdk_ext PROPERTIES SUFFIX "${NB_SUFFIX}")
  endif()
  ```
  既存 `run.py:318, 351, 372` で渡していた `-DNB_SUFFIX` と等価。 native build では `NB_SUFFIX` が未設定なのでこのブロックは入らない。
- 既存 `CMakeLists.txt:21-38` の `if(CMAKE_CROSSCOMPILING)` 分岐（Python find のクロス対応）はそのまま流用する。

### CI 影響

- `build_ubuntu` matrix の `exclude` から `ubuntu-24.04_armv8` の 1 行を削除する（残るは `ubuntu-22.04_x86_64` / `ubuntu-22.04_armv8` / `raspberry-pi-os_armv8` の 3 件で 0019 / 0020 / 0022 が順次外す）。
- armv8 用 step を `if: ${{ matrix.platform.name == 'ubuntu-24.04_armv8' }}` で追加（既存 armv8 step は multistrap install を含んでいたが、 本 issue では削除して `uv build --wheel` のみにする）:
  ```yaml
  - if: ${{ matrix.platform.name == 'ubuntu-24.04_armv8' }}
    env:
      SORA_SDK_TARGET: ${{ matrix.platform.target }}
      _PYTHON_HOST_PLATFORM: linux_aarch64
    run: uv build --wheel
  ```
- 既存 `if: ${{ matrix.platform.arch == 'armv8' }}` の multistrap install step は本 issue では触らない（0019 で `ubuntu-22.04_armv8` も sysroot ベースに移行した時点でまとめて削除）。
- `slack_notify` の `needs:` は `[build_ubuntu]` のまま（matrix 内の追加 entry も自動的に対象になる）。

## 完了条件

- ubuntu-24.04 x86_64 host で `SORA_SDK_TARGET=ubuntu-24.04_armv8 _PYTHON_HOST_PLATFORM=linux_aarch64 uv build --wheel` が Python 3.12 / 3.13 / 3.14 の 3 通りで成功し、 wheel タグが `cp3XY-cp3XY-manylinux_2_35_aarch64` になる。
- 生成 wheel 内 `.so` のアーキテクチャが ARM aarch64 であることを `unzip -p dist/*.whl 'sora_sdk/sora_sdk_ext.*.so' | file -` で確認 → `ELF 64-bit LSB shared object, ARM aarch64` を出力する。
- 2 回目以降の build で `_deps/ubuntu-24.04_armv8/{webrtc,sora,boost,openh264}` と `_deps/sysroots/<sysroot_key>/` が再生成されない（mtime 不変）。
- pytest はクロスなのでホストで実行しない。 実シンボル検証は 0022 で `auditwheel show` を導入時に行う。
- CI で `build_ubuntu` matrix の `ubuntu-24.04_armv8` × 3 Python entry が green になる。

## 解決方法

- **cmake/toolchains/aarch64-linux-cross.cmake**: 「設計方針 → toolchain ファイル」の CMake コードで新設する。
- **cmake/scripts/fetch_deps.cmake**: 「設計方針 → fetch_deps.cmake の cross 対応」の方針で `SORA_SDK_TARGET` 分岐追加 + 許容リスト拡張 + `_sora_fetch_sysroot` 新設 + メインスクリプトに cross 時のみの呼び出し追加 + 出力契約に `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` 追加 を行う。
- **pyproject.toml**: 「設計方針 → pyproject.toml の cross overrides」の 3 件 override を末尾に追加。
- **CMakeLists.txt**: `find_package(Python)` 直後に `if(NB_SUFFIX)` ブロック追加。
- **.github/workflows/build.yml**: matrix `exclude` から `ubuntu-24.04_armv8` を削除、 cross 用 step を追加。
- **CHANGES.md** `## develop` の `[CHANGE]` グループに追加:

```
- [CHANGE] Linux arm64 wheel を ubuntu-24.04 x86_64 host からのクロスコンパイル (Chromium sysroot) で生成するように切り替える
  - @voluntas
```

旧 `build_ubuntu_arm` （arm64 native runner）廃止と multistrap 廃止の旨は 0022 でまとめて記載する。

## ロールバック

revert は `_sora_fetch_sysroot` の根本設計（Chromium build リポジトリ shallow clone + install-sysroot.py 実行 + sysroot 配置）に起因する不具合で追加コミットでは修正できない場合に選ぶ。 toolchain / override / matrix step の単発不具合は revert ではなく追加コミットで前進させる。

手順: `git revert -m 1 <merge-commit>` で revert PR 作成、 `build_ubuntu` matrix から `ubuntu-24.04_armv8` 再 exclude を確認、 `_deps/sysroots/` は残留しても無害。
