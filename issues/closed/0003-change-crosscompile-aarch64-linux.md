# Linux arm64 クロスコンパイル対応と multistrap から sysroot builder への移行

- Priority: High
- Created: 2026-05-21
- Updated: 2026-07-17
- Completed: 2026-07-23
- Model: Composer 2.5
- Branch: feature/change-crosscompile-aarch64-linux
- Polished: 2026-07-23

## 目的

0001 で導入する scikit-build-core + `cmake/scripts/fetch_deps.cmake` 構成を拡張し、 ubuntu-24.04 x86_64 host 上で `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` 向け wheel を `uv build --wheel` で生成できるようにする。

sysroot は `multistrap` ではなく、 webrtc-build の実装を基に `apt-get --download-only` と `dpkg-deb --extract` で生成する。ホストの APT 状態を参照せず、 HTTPS と `signed-by` による署名検証を必須とし、 `--no-auth` 、 `AllowInsecureRepositories` 、 `/usr/sbin/multistrap` の書き換えを廃止する。

## 優先度根拠

- 0004 の Raspberry Pi OS 対応と 0043 の Jetson 対応が、本 issue で導入する `sysroot_builder.py` 、 JSON 設定、 CMake 連携を前提とする。
- `multistrap` は Debian unstable から削除済みで、将来の runner 更新を妨げる。
- 現行経路は HTTP 、 `--no-auth` 、 `AllowInsecureRepositories` を使用しており、依存パッケージの取得経路として維持できない。
- 0001 は arm64 native job とレガシービルドスクリプトを削除するため、本 issue が完了するまで Linux arm64 wheel の生成経路が失われる。

## 前提

- 0001 および 0002 の完了後に実装する。0001 が追加する `_deps/` レイアウト / `fetch_deps.cmake` と、0002 が更新する scikit-build-core 1.x 設定 / `build_macos` job を直接拡張する。
- wheel の compile / link host は ubuntu-24.04 x86_64 のみとし、arm64 native build は復活させない。0052 が auditwheel の architecture 制約により matching AArch64 runner で repair だけを行うことは許可する。
- クロスコンパイラは 0001 が `_deps/llvm/x86_64-Linux/clang` に取得する libwebrtc 同梱 clang を使う。
- 本 issue で生成する wheel の platform tag は `linux_aarch64` とする。manylinux tag の決定と `auditwheel repair` は 0052 で行う。
- 0004 は本 issue の実装を拡張する。 0003 と 0004 を同時実装しない。

## スコープ

含む:

- webrtc-build の `sysroot_builder.py` とユニットテストの移植。
- Ubuntu 22.04 / 24.04 arm64 用 JSON 設定の追加。
- `multistrap/ubuntu-22.04_armv8.conf` / `multistrap/ubuntu-24.04_armv8.conf` の削除。
- 共通 AArch64 toolchain `linux-aarch64-cross.cmake` の追加。
- `fetch_deps.cmake` から sysroot builder を呼び出し、 `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` を設定する処理。
- scikit-build-core の cross override 、 arm64 extension suffix 、 CI matrix の追加。
- Python 3.12 / 3.13 / 3.14 ごとの型情報 artifact を native wheel から生成し、同じ ABI の cross wheel へ `.pyi` / `py.typed` を同梱する経路。
- 設定 validation 、キャッシュ再利用、 ELF architecture を含む検証。

含まない:

- Raspberry Pi OS の sysroot（0004）と Jetson の sysroot（0043）。
- macOS / Windows の native build（0002 / 0005）。
- manylinux tag / `auditwheel repair`（0052）、publish / release（0066）、E2E（0067）。
- arm64 native build の復活。0052 の repair-only job は本 issue の対象外とする。
- WebRTC / Sora / Boost 等の release archive の SHA-256 検証（0070）。sysroot の fingerprint に使う署名鍵の SHA-256 は本 issue に含む。
- CI job 間の dependency cache（0071）。同一 checkout 内の sysroot 再利用は本 issue で検証する。

## 現状

現行 `develop` には `run.py` / `buildbase.py` / `setup.py` を使う Ubuntu arm64 クロスビルド経路がある。しかし 0001 はこれらのファイル、 arm64 matrix 、 `build_ubuntu_arm` job を削除し、 ubuntu-24.04 x86_64 native build だけを残す。

現行 rootfs 経路には次の問題がある。

- `buildbase.py:1075-1118` の `install_rootfs()` が `multistrap --no-auth` を実行する。
- CI が `/usr/sbin/multistrap` を `sed` で書き換え、 `Acquire::AllowInsecureRepositories=true` を注入する。
- Ubuntu 用 conf が `http://ports.ubuntu.com` を参照する。
- conf の MD5 だけをキャッシュキーとするため、署名鍵や生成ロジックの変更を検出できない。
- rootfs を出力先へ直接展開するため、失敗時に部分生成物が残り得る。

一方、参照先の webrtc-build には、これらを解消した `sysroot_builder.py` とテストがある。移植元は次の 2 commit に固定する。

- `2c15196`：`apt-get --download-only` + `dpkg-deb --extract` による実装とテスト。
- `59a0ce0`：同実装へ設計意図を説明する日本語コメントを追加。

sora-cpp-sdk の multistrap 移行 issue は同じ移行の設計資料として参照する。ただし、 sora-cpp-sdk の古い実装 branch にある inline `install_sysroot` や、 sora-python-sdk の `origin/feature/change-replace-multistrap-with-sysroot` にある旧 `sysroot.py` は、 APT の隔離と署名検証が不足するため移植しない。 webrtc-rs の `cargo-shiguredo-sysroot` は JSON 構成と CI の参考に留め、 Python / CMake の依存には追加しない。

## 設計方針

### sysroot builder

リポジトリルートへ `sysroot_builder.py` を追加し、 webrtc-build の `59a0ce0` 時点の内容を移植する。動作を合わせるため、次の契約を維持する。

- `SysrootConfig` / `RepositoryConfig` を frozen dataclass とし、 JSON の必須値、重複、使用可能文字を APT 実行前に検証する。
- リポジトリ URL は HTTPS だけを許可し、全リポジトリに `signed_by` を要求する。
- `APT_CONFIG` 、 `Dir::State` 、 `Dir::Cache` 、 `Dir::Etc::*` を一時ディレクトリへ向け、ホストの `/var/lib/apt` と `/etc/apt` を読み書きしない。
- `APT::Architecture=arm64` を設定し、 `apt-get update` 、 `apt-get --download-only install` 、 `dpkg-deb --extract` の順で実行する。 maintainer script と chroot は使わず、 root 権限を要求しない。
- usrmerge link 、 sysroot 内で解決できる絶対 symlink の相対化、 triplet 固有 pkg-config file への互換 link を後処理する。解決不能な `/etc/alternatives` 等の絶対 symlink は変更しない。
- 設定値と署名鍵内容の SHA-256 、 `MANIFEST_VERSION` を manifest に保存する。同一 fingerprint は再利用し、不一致の既存出力は `--force` 無しでは削除しない。
- 同じ親ディレクトリの一時領域で完成させ、 rename によって出力先を入れ替える。失敗時は既存 sysroot を戻す。

manifest 名は cross repository で builder と生成物の形式を識別できる互換名として `.webrtc-build-sysroot.json` を恒久的に維持する。この意図を定数のコメントにも残す。後処理または生成形式を変えた場合は、同じ変更で `MANIFEST_VERSION` と該当テストを更新する。

APT が解決した package version は manifest の `deb_files` に記録するが、 JSON では pin しない。このため、本 issue の「再利用」は同一設定で一度生成した sysroot を固定して使うことを意味し、 repository の時点再現までは保証しない。依存を更新するときは CLI を `--force` 付きで直接実行し、 PR で変更前後の `deb_files` を確認する。

ログとエラーメッセージは英語、コメントとテストの説明は日本語とする。エラーメッセージの末尾にピリオドを付けず、ソースとテストのコメントに issue 番号を書かない。

### CLI と CMake 連携

`sysroot_builder.py` 自体に `main()` と `if __name__ == "__main__":` を追加し、 module API と CLI を 1 ファイルにまとめる。 CLI 専用の `sysroot.py` は追加しない。

```text
python sysroot_builder.py --config <json> --dest <rootfs> [--force]
```

CLI は subcommand を設けず、設定を読み込み、 `config.name` と JSON のファイル stem が一致することを検証してから `build_sysroot()` を呼ぶ。 `main(argv: Sequence[str] | None = None) -> int` と argument parser を分離して unit test 可能にする。 `SysrootConfigError` / `SysrootBuildError` / `subprocess.CalledProcessError` / 入出力に伴う `OSError` は英語のエラーを標準エラーへ出して `1` 、成功または再利用は `0` で終了する。想定外の例外は原因調査のため stack trace を維持する。 logging level は `INFO` とする。 `--force` は由来不明または fingerprint 不一致の既存 rootfs を利用者が明示的に置き換える場合だけ使う。

0001 の `cmake/scripts/fetch_deps.cmake` に `_sora_fetch_sysroot(config_path rootfs_dir)` を追加する。

- `SORA_PYTHON_SDK_PLATFORM` が `ubuntu-22.04_armv8` または `ubuntu-24.04_armv8` の場合だけ呼び出す。
- `${Python_EXECUTABLE} ${CMAKE_SOURCE_DIR}/sysroot_builder.py --config ... --dest ...` を `execute_process()` で実行し、失敗時は `FATAL_ERROR` にする。
- rootfs は `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/rootfs` に生成する。
- CMake 独自の MD5 stamp は作らない。再利用判定は builder の manifest に一本化する。
- CMake からは `--force` を渡さない。 fingerprint 不一致時は安全側で configure を失敗させ、エラーに表示された config / dest を使って利用者が CLI を `--force` 付きで直接実行してから build を再実行する。
- 成功後に `CMAKE_SYSROOT` と `CMAKE_FIND_ROOT_PATH` を rootfs へ `CACHE PATH FORCE` で設定する。
- 0001 が取得処理全体に設定する `${DEPS_ROOT}/.fetch.lock` の内側で実行し、同一 checkout の並列 configure を直列化する。
- 最初の `project()` が言語を有効化する前に走る `CMAKE_PROJECT_TOP_LEVEL_INCLUDES` 上で、 platform 確定、 sysroot 生成、依存取得、 compiler cache 設定の順に完了させる。 CMake の compiler check 後に `CMAKE_SYSROOT` を変更しない。

`SORA_PYTHON_SDK_PLATFORM` の cache 値と `SORA_SDK_TARGET` 環境変数の両方が設定され、値が異なる場合は `FATAL_ERROR` とする。同じ値なら明示 target として扱い、片方だけならその値を使う。どちらも未設定の場合だけ 0001 の host 自動検出を使う。全経路で最後に許容リストを検証し、不明な値を受け入れない。

### JSON 設定

`sysroot/ubuntu-22.04_armv8.json` と `sysroot/ubuntu-24.04_armv8.json` を追加する。共通値は次の通り。

```json
{
    "name": "<ファイル stem>",
    "arch": "arm64",
    "triplet": "aarch64-linux-gnu",
    "packages": ["<後述>"],
    "repositories": [
        {
            "url": "https://ports.ubuntu.com/ubuntu-ports",
            "suite": "<jammy または noble>",
            "components": ["main", "universe"],
            "signed_by": "/usr/share/keyrings/ubuntu-archive-keyring.gpg"
        }
    ]
}
```

パッケージは現行 conf と同じ集合を維持する。

| target | suite | packages |
| --- | --- | --- |
| `ubuntu-22.04_armv8` | `jammy` | `libstdc++-11-dev`, `libc6-dev`, `libxext-dev`, `libdbus-1-dev` |
| `ubuntu-24.04_armv8` | `noble` | `libstdc++-13-dev`, `libc6-dev`, `libxext-dev`, `libdbus-1-dev` |

Ubuntu archive keyring は repository に複製せず、 CI で `ubuntu-keyring` を明示的に install して system keyring を使う。設定変更または runner の keyring 更新で fingerprint が変わった場合は、 CLI を `--force` 付きで直接実行して再生成する。

### toolchain と CMake

`linux-aarch64-cross.cmake` を共通 AArch64 toolchain として追加する。

```cmake
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_CXX_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
```

compiler は 0001 の `_SORA_CLANG_DIR` 、 sysroot は `fetch_deps.cmake` が確定するため、 toolchain file に絶対パスを重複記載しない。通常の library / include / package 探索は sysroot のみに限定する。 host Python discovery の間だけ検索 mode を退避して `NEVER` にし、終了後は元の `ONLY` へ戻す。 `PROGRAM` は host tool を探すため `NEVER` のままとする。

sysroot 外にある target 用 Sora / WebRTC / Boost / OpenH264 は、 0001 が確定する `SORA_DIR` / `Boost_ROOT` / `WEBRTC_*` / `OPENH264_DIR` だけを使う。 `find_package()` が必要な Sora / Boost はそれぞれの絶対 root を `PATHS` へ渡し、 `NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH` で限定する。 WebRTC は `${SORA_DIR}/share/cmake` の既存 module path に限定して `NO_CMAKE_FIND_ROOT_PATH` で探す。 host 側で必要な nanobind は、 `Python_EXECUTABLE -m nanobind --cmake_dir` の結果だけを `PATHS` に渡し、 `NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH` で探す。それ以外の host package / header / library への fallback は認めない。

configure 後に `compile_commands.json` 、 link command 、 `CMakeCache.txt` の絶対 path を検査する。許可するのは rootfs 、 `_deps/<platform>/` 、 `_deps/llvm/x86_64-Linux/` 、 build isolation 環境の Python / nanobind 、 host program の path だけとし、それ以外の host include / library / package config が含まれたら失敗させる。

`CMakeLists.txt` では `nanobind_add_module(sora_sdk_ext ...)` より後で、 `NB_SUFFIX` が設定されている場合に `sora_sdk_ext` の `SUFFIX` をその値へ設定する。 target 作成前に `set_target_properties()` を呼ばない。 cross build は `SORA_GEN_PYI=OFF` とし、 target binary を host 上で実行しない。

### pyproject.toml

`cmake.toolchain-file` と `wheel.tags` を利用する。0002 が更新した build requirement `scikit-build-core>=1.0,<2`、`minimum-version = "1.0"` を維持し、0.12 系へ downgrade しない。`cmake.define` は override すると base table を置き換えるため、全 block に `inherit.cmake.define = "append"` を指定して 0001 の `TARGET_OS = "ubuntu"` を維持する。

`SORA_SDK_TARGET` 2 種類と Python 3.12 / 3.13 / 3.14 の組み合わせごとに、次の 6 block を追加する。

```toml
[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^ubuntu-22\\.04_armv8$"
if.python-version = "==3.12.*"
inherit.cmake.define = "append"
build-dir = "_build/ubuntu-22.04_armv8/{wheel_tag}"
cmake.toolchain-file = "cmake/toolchains/linux-aarch64-cross.cmake"
cmake.define.NB_SUFFIX = ".cpython-312-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"
cmake.define.CMAKE_EXPORT_COMPILE_COMMANDS = "ON"
wheel.tags = ["cp312-cp312-linux_aarch64"]

[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^ubuntu-22\\.04_armv8$"
if.python-version = "==3.13.*"
inherit.cmake.define = "append"
build-dir = "_build/ubuntu-22.04_armv8/{wheel_tag}"
cmake.toolchain-file = "cmake/toolchains/linux-aarch64-cross.cmake"
cmake.define.NB_SUFFIX = ".cpython-313-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"
cmake.define.CMAKE_EXPORT_COMPILE_COMMANDS = "ON"
wheel.tags = ["cp313-cp313-linux_aarch64"]

[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^ubuntu-22\\.04_armv8$"
if.python-version = "==3.14.*"
inherit.cmake.define = "append"
build-dir = "_build/ubuntu-22.04_armv8/{wheel_tag}"
cmake.toolchain-file = "cmake/toolchains/linux-aarch64-cross.cmake"
cmake.define.NB_SUFFIX = ".cpython-314-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"
cmake.define.CMAKE_EXPORT_COMPILE_COMMANDS = "ON"
wheel.tags = ["cp314-cp314-linux_aarch64"]

[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^ubuntu-24\\.04_armv8$"
if.python-version = "==3.12.*"
inherit.cmake.define = "append"
build-dir = "_build/ubuntu-24.04_armv8/{wheel_tag}"
cmake.toolchain-file = "cmake/toolchains/linux-aarch64-cross.cmake"
cmake.define.NB_SUFFIX = ".cpython-312-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"
cmake.define.CMAKE_EXPORT_COMPILE_COMMANDS = "ON"
wheel.tags = ["cp312-cp312-linux_aarch64"]

[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^ubuntu-24\\.04_armv8$"
if.python-version = "==3.13.*"
inherit.cmake.define = "append"
build-dir = "_build/ubuntu-24.04_armv8/{wheel_tag}"
cmake.toolchain-file = "cmake/toolchains/linux-aarch64-cross.cmake"
cmake.define.NB_SUFFIX = ".cpython-313-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"
cmake.define.CMAKE_EXPORT_COMPILE_COMMANDS = "ON"
wheel.tags = ["cp313-cp313-linux_aarch64"]

[[tool.scikit-build.overrides]]
if.env.SORA_SDK_TARGET = "^ubuntu-24\\.04_armv8$"
if.python-version = "==3.14.*"
inherit.cmake.define = "append"
build-dir = "_build/ubuntu-24.04_armv8/{wheel_tag}"
cmake.toolchain-file = "cmake/toolchains/linux-aarch64-cross.cmake"
cmake.define.NB_SUFFIX = ".cpython-314-aarch64-linux-gnu.so"
cmake.define.SORA_GEN_PYI = "OFF"
cmake.define.CMAKE_EXPORT_COMPILE_COMMANDS = "ON"
wheel.tags = ["cp314-cp314-linux_aarch64"]
```

manylinux tag は指定しない。 `_PYTHON_HOST_PLATFORM` との二重指定も行わず、 wheel tag の単一情報源を override にする。 target 名を `build-dir` に含め、同じ Python ABI で Ubuntu 22.04 / 24.04 を切り替えても CMake cache を共有しない。

`sysroot_builder.py` を ty の対象へ追加する。 `pytest-timeout~=2.4.0` を test dependency group と `uv.lock` に追加する。

### テスト

`tests/test_sysroot_builder.py` は webrtc-build のテストを移植し、少なくとも次をネットワーク接続、 mock 、 stub 無しで検証する。

- 相対 keyring path の解決、必須値、重複、 HTTPS 、 `signed_by` の validation 。
- checkout path に依存しない fingerprint 。
- `_apt_options()` と `_write_apt_files()` が APT の state / cache / sources / preferences を一時ディレクトリへ隔離し、 HTTPS + `signed-by` の sources.list を生成すること。
- 解決可能な絶対 symlink の相対化と、解決不能 link の維持。
- pkg-config 互換 link 。
- manifest 一致時の再利用。
- 古い manifest 、由来不明 directory 、壊れた symlink の `--force` 無しでの拒否。
- `_install_completed_sysroot()` が完成済み directory を入れ替えることと、存在しない `new_root` で配置に失敗した場合に既存 directory を復元すること。
- CLI における config name とファイル stem の不一致拒否。
- CLI の argument parser が `--force` を正しく解釈すること。 APT 呼び出しへの伝播は integration test で確認する。

これらは APT 実行前の早期 return / error だけを通し、 unit test から実ネットワークへ接続しない。実際の APT download は CI の wheel build で integration test する。

検証コマンド:

```bash
uv run --no-sync ruff check sysroot_builder.py tests/test_sysroot_builder.py
uv run --no-sync ruff format --check sysroot_builder.py tests/test_sysroot_builder.py
uv run --no-sync ty check
uv run --no-sync pytest tests/test_sysroot_builder.py --timeout=10
```

### 型情報の生成と同梱

0001 で一旦削除する `build_pyi` job を Python 3.12 / 3.13 / 3.14 の matrix として復活させる。ubuntu-24.04 x86_64 の native wheel を `uv build --wheel` で生成し、標準 library の `zipfile` で展開して `sora_sdk/sora_sdk_ext.pyi` と `sora_sdk/py.typed` が各 1 件あることを確認する。

Python version、2 file の相対 path と SHA-256 を manifest に記録し、`type-stubs_python-<version>` artifact として upload する。source tree に残った file は artifact に使わない。

各 cross entry は同じ Python version の artifact を download し、manifest の version / path / SHA-256 を検証してから 2 file を `src/sora_sdk/` へ配置する。cross CMake は `SORA_GEN_PYI=OFF` を維持し、target extension を host 上で実行しない。生成 wheel を展開し、`.pyi` / `py.typed` が各 1 件だけ含まれることを確認する。0004 の Raspberry Pi OS entry も本 artifact 契約を再利用する。

### CI

0001 後の `.github/workflows/build.yml` の `build_ubuntu` matrix に、 ubuntu-24.04 x86_64 runner で動く次の 2 target を追加する。 Python 3.12 / 3.13 / 3.14 と組み合わせ、計 6 entry とする。

- `ubuntu-22.04_armv8`
- `ubuntu-24.04_armv8`

`build_ubuntu` は `needs: [build_pyi]` を持つ。cross entry は `ca-certificates` 、 `ubuntu-keyring` 、 `binutils-aarch64-linux-gnu` を install する。 `multistrap` は install しない。対応する型情報 artifact を検証・配置してから、`SORA_SDK_TARGET=${{ matrix.platform.target }}` を渡して `uv build --wheel` を実行する。

cross wheel は x86_64 host へ install せず、 pytest も実行しない。代わりに `unzip -p <wheel> 'sora_sdk/sora_sdk_ext.*.so' | file -` で `.so` を標準入力経由で検査し、 `ELF 64-bit LSB shared object, ARM aarch64` を確認する。 wheel filename が `cp3XY-cp3XY-linux_aarch64.whl` であることも確認する。

sysroot は次を確認する。

- manifest の `format_version` / `name` / `arch=arm64` / `triplet=aarch64-linux-gnu` / `deb_files` が有効である。
- 共通で `usr/include/stdio.h` 、 `usr/lib/aarch64-linux-gnu/libXext.so` 、 `usr/include/dbus-1.0/dbus/dbus.h` が存在する。
- Ubuntu 22.04 は `usr/include/c++/11/vector` 、 Ubuntu 24.04 は `usr/include/c++/13/vector` が存在する。
- `compile_commands.json` 、 `ninja -C <build-dir> -t commands sora_sdk_ext` の出力、 `CMakeCache.txt` の dependency path を realpath 化して検査する。 rootfs 、 target 用 `_deps/<platform>/` 、 LLVM の `_deps/llvm/x86_64-Linux/` 、 build isolation 環境の Python / nanobind 以外の include / library / package config を拒否する。 host program は検査対象外とする。

同じ設定で builder を 2 回実行し、 2 回目の英語ログが cache reuse を示し、 manifest と代表 header の mtime が変わらないことを integration test に含める。さらに代表 1 target で manifest の fingerprint を意図的に不一致にし、通常実行が既存 rootfs を維持して失敗した後、 CLI の `--force` 付き直接実行で置換できることを確認する。 CI job 間では workspace を共有しないため、 job をまたぐ cache reuse は本 issue の完了条件にしない。

native x86_64 entry の wheel install + pytest は維持する。`slack_notify.needs` は 0002 の `build_macos` dependency を維持して `[build_ubuntu, build_macos]` とし、arm64 専用 job は新設しない。

## 完了条件

- `multistrap` 、 `--no-auth` 、 `AllowInsecureRepositories` 、 `install_rootfs.sh` を新経路が使用しない。
- Ubuntu 用 2 conf が削除され、非 issue / 変更履歴の Ubuntu arm64 build 用 multistrap 参照が残らない。 Jetson 用 conf は 0001 で削除し、 Raspberry Pi OS 用 conf は 0004 まで残してよい。
- sysroot の APT state が一時ディレクトリへ隔離され、 HTTPS + `signed-by` 以外の repository 設定を拒否する。
- unit test 、 ruff 、 ty が完走する。
- ubuntu-24.04 x86_64 host で 2 target × Python 3.12 / 3.13 / 3.14 の wheel build が成功する。
- wheel tag が `cp3XY-cp3XY-linux_aarch64` 、 extension が `sora_sdk/sora_sdk_ext.cpython-3XY-aarch64-linux-gnu.so` 、 ELF architecture が AArch64 である。
- 各 cross wheel に対応 ABI の `.pyi` / `py.typed` が各 1 件だけ含まれ、target extension を host 上で実行しない。
- `CMAKE_EXPORT_COMPILE_COMMANDS=ON` で生成した compile command 、 Ninja の link command 、 CMake cache に、許可していない host の include / library / package config が含まれない。
- 2 回目の同一設定 build が sysroot を再生成しない。 fingerprint 不一致の既存 sysroot は `--force` 無しで拒否する。
- 同一 checkout での並列 configure は 0001 の `${DEPS_ROOT}/.fetch.lock` によって直列化され、同じ rootfs 出力を同時更新しない。
- APT download / deb 展開 / 後処理が失敗した段階では既存 sysroot に触れず、完成した出力だけに manifest が存在する。最終 rename の失敗時は既存 sysroot を復元する。
- native ubuntu-24.04 x86_64 build と smoke test が引き続き成功する。
- CI が `multistrap` を install せず、wheel の compile / link に arm64 native runner を使用しない。

## 解決方法

実装せず closed にする。

本 issue は scikit-build-core（0001）前提の文面だったため、現行 `run.py` 経路向けの 0074 に置き換える。
Ubuntu arm64 と Raspberry Pi OS の multistrap → sysroot 切り替えは 0074 で扱う。

## 関連 issue への影響

- 0004 は `install_rootfs.sh` / multistrap を前提とする現行案を破棄し、 `sysroot_builder.py` / JSON 設定を拡張する内容へ全面改稿する。
- 0004 完了時に Raspberry Pi OS 用 multistrap conf も削除されるため、0061 は 0004 の実装 PR で解決理由と完了日を記録して closed にする。
- 0071 の cache key は `multistrap/*.conf` ではなく `sysroot/*.json` / `sysroot_builder.py` を対象にする。system keyring の SHA-256 は `hashFiles()` で取得できないため、cache restore 前に step output として算出し key に含める。

## ロールバック

問題が発生した場合は 0003 の squash commit を `git revert` し、 0001 完了時点の ubuntu-24.04 x86_64 native entry のみに戻す。 `multistrap` 経路と arm64 native runner は復活させず、 Linux arm64 wheel の生成を一時停止して forward fix する。

## 参照（一次資料）

- webrtc-build `2c15196` / `59a0ce0`: `sysroot_builder.py` と `tests/test_sysroot_builder.py` 。
- scikit-build-core 公式 Cross-compiling guide: `cmake.toolchain-file` と manual cross compilation 。
- scikit-build-core 公式 Config Reference: override 専用の `cmake.toolchain-file` と `wheel.tags` 。
- scikit-build-core 公式 Overrides: version / environment 条件と `inherit.cmake.define = "append"` 。
