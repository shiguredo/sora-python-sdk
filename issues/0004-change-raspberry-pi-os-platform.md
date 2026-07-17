# Raspberry Pi OS Trixie 向けクロスコンパイル対応と sysroot への移行

- Priority: High
- Created: 2026-05-21
- Updated: 2026-07-17
- Completed: -
- Model: Composer 2.5
- Branch: feature/change-raspberry-pi-os-platform
- Polished: 2026-07-17

## 目的

0003 で導入する `sysroot_builder.py` 、 JSON 設定、共通 AArch64 toolchain を拡張し、 ubuntu-24.04 x86_64 host から `raspberry-pi-os_armv8` 向け wheel を Python 3.12 / 3.13 / 3.14 で生成できるようにする。

Raspberry Pi OS は README のサポート対象に合わせて Trixie 64-bit とする。 Debian / Raspberry Pi の署名付き APT repository から sysroot を生成し、現行の Bookworm / HTTP / multistrap 経路を削除する。 distribution 名は `sora_sdk_rpi` 、 import package 名は `sora_sdk` を維持する。

## 優先度根拠

- 0001 完了後は現行 `run.py` / `setup.py` と Raspberry Pi OS 用 CI entry が削除され、本 issue が完了するまで Raspberry Pi OS wheel の生成経路が失われる。
- 現行 `multistrap/raspberry-pi-os_armv8.conf` は README と異なる Bookworm を参照し、 HTTP と署名検証を回避する CI patch に依存している。
- 0066 / 0067 / 0071 は、本 issue で確定する wheel tag、artifact 名、sysroot 入力を前提とする。

## 前提

- 0001 と 0003 の完了後に実装する。
- build host は ubuntu-24.04 x86_64 とし、 arm64 native runner でビルドしない。
- 0003 の `sysroot_builder.py` 自体を CLI として利用する。 CLI 専用の `sysroot.py` や `install_rootfs.sh` は追加しない。
- compiler と target search policy は 0003 の共通 AArch64 toolchain `linux-aarch64-cross.cmake` を再利用する。 Raspberry Pi OS 専用 toolchain は追加しない。
- Python はプロジェクトのサポート方針どおり 3.12 / 3.13 / 3.14 とする。
- 本 issue で生成する `sora_sdk_rpi` wheel の platform tag は `linux_aarch64` とする。libcamera / Raspberry Pi OS 固有依存を持つため 0052 の auditwheel 対象外とし、publish は 0066、実機 E2E は 0067 で扱う。`.pyi` / `py.typed` は 0003 の artifact 契約を再利用して本 issue で同梱する。
- Jetson 実装は 0043 / 0045 で扱う。

## スコープ

含む:

- `sysroot_builder.py` に repository pinning を追加する。
- Raspberry Pi OS 用 JSON `raspberry-pi-os_armv8.json` と Raspberry Pi archive keyring を追加する。
- Raspberry Pi OS 用 multistrap conf を削除する。
- 0003 の `_sora_fetch_sysroot()` と許容 platform 一覧を Raspberry Pi OS へ拡張する。
- `CMakeLists.txt` の既存 Raspberry Pi OS 分岐を新経路から有効化し、 `libcamerac.so` を wheel へ同梱する。
- `pyproject.toml` に Raspberry Pi OS × Python 3 バージョンの override を追加する。
- CI で distribution 名を `sora_sdk_rpi` へ切り替え、 wheel 、 sysroot 、 target ELF を検証する。
- 0003 の型情報 artifact を検証し、同じ Python ABI の `.pyi` / `py.typed` を wheel へ同梱する。

含まない:

- Jetson 向け sysroot / wheel（0043）。
- Ubuntu arm64 sysroot の導入（0003）。
- macOS / Windows native build（0002 / 0005）。
- publish（0066）、実機 E2E（0067）。Raspberry Pi OS wheel へ manylinux tag を付ける変更は対象外とする。
- WebRTC / Sora / Boost archive の SHA-256 検証（0070）と CI job 間の cache（0071）。

## 現状

現行 `develop` には次の Raspberry Pi OS 経路がある。

- `multistrap/raspberry-pi-os_armv8.conf` は Debian Bookworm と Raspberry Pi Bookworm を HTTP で参照し、 `libstdc++-11-dev` を取得する。
- `.github/workflows/build.yml` は `multistrap` を install し、 `/usr/sbin/multistrap` へ `Acquire::AllowInsecureRepositories=true` を注入する。
- `run.py` は `SORA_SDK_TARGET=raspberry-pi-os_armv8` を解釈し、 `libcamerac.so` を `sora_sdk` package へコピーする。
- `setup.py` は distribution 名の CI 上の書き換えを前提に `sora_sdk_rpi` wheel を作り、 manylinux tag を手動設定する。
- `CMakeLists.txt` の `TARGET_OS=raspberry-pi-os` 分岐は `USE_V4L2` と `BUILD_RPATH=$ORIGIN` を設定する。
- README は Raspberry Pi OS Trixie 64-bit をサポート対象としているため、 Bookworm sysroot と一致していない。

0001 は `run.py` / `buildbase.py` / `setup.py` と既存 Raspberry Pi OS CI entry を削除する。 0003 は安全な sysroot builder と Ubuntu arm64 用 JSON / CI を追加するが、 Raspberry Pi OS 用 JSON 、 keyring 、 package 名切替、 `libcamerac.so` 同梱は追加しない。

webrtc-build の Raspberry Pi OS 用 JSON は builder と keyring の参照元にはできるが、 Bookworm / `libstdc++-11-dev` のため JSON 自体はコピーしない。 webrtc-rs の Trixie 設定は package version の参考に留め、 HTTP や署名鍵未指定の repository 設定は移植しない。

## 設計方針

### 共通 toolchain

0003 が追加する共通 AArch64 toolchain `linux-aarch64-cross.cmake` を Ubuntu arm64 と Raspberry Pi OS で共有する。 compiler target と検索 mode は両 target で同じであり、 Raspberry Pi OS 固有処理は `TARGET_OS=raspberry-pi-os` を受ける `CMakeLists.txt` に置く。

toolchain は library / include / package を sysroot だけから検索し、 host への fallback を許可しない。 host Python / nanobind と、 sysroot 外の target 用 Sora / WebRTC / Boost / OpenH264 は 0003 が定める明示 path だけを許可する。

### repository pinning

Raspberry Pi repository の overlay package を Debian repository より優先し、 Raspberry Pi OS 向けに調整された `libcamera-dev` / `libc6-dev` 等を確実に選ぶため、 `RepositoryConfig` に optional な `pin_priority: int | None` を追加する。

- 未指定時は APT の既定 priority を変更しない。
- 指定可能範囲は `1..1000` とし、 `bool` は拒否する。
- pin 対象は repository URL の hostname とし、 `urllib.parse.urlsplit()` で取得する。 userinfo 、 query 、 fragment 、 hostname 不在の URL を拒否する validation を本 issue で追加する。
- pin が 1 件以上あれば一時 work directory に `preferences` を生成し、 `_apt_options()` の `Dir::Etc::preferences` をそのファイルへ向ける。 `preferencesparts` は空の隔離 directory へ向け、 host の APT preferences を参照しない。
- stanza は `Package: *` / `Pin: origin "<hostname>"` / `Pin-Priority: <value>` とする。
- pin は hostname 全体へ作用するため、同じ hostname を持つ repository 間では `None` と数値の混在を含め、異なる `pin_priority` を validation error とする。
- repository object の未知 key を拒否し、 `pin_priority` の綴り間違いを黙って無視しない。
- `pin_priority` が指定された repository だけ fingerprint payload に同 field を追加する。未指定 repository へ `null` を追加せず、0003 と同じ pin 無し schema の fingerprint を変えない。 manifest 自体の schema は変えないため `MANIFEST_VERSION` は更新しない。

Raspberry Pi repository は `pin_priority: 990` とする。 Debian repository は pin しない。

### Raspberry Pi OS Trixie の JSON

Raspberry Pi OS 用 JSON を次の内容で追加する。

```json
{
    "name": "raspberry-pi-os_armv8",
    "arch": "arm64",
    "triplet": "aarch64-linux-gnu",
    "packages": [
        "libc6-dev",
        "libstdc++-14-dev",
        "libasound2-dev",
        "libpulse-dev",
        "libudev-dev",
        "libexpat1-dev",
        "libnss3-dev",
        "libxext-dev",
        "libxtst-dev",
        "libcamera-dev"
    ],
    "repositories": [
        {
            "url": "https://deb.debian.org/debian",
            "suite": "trixie",
            "components": ["main"],
            "signed_by": "keyrings/debian-archive-keyring.gpg"
        },
        {
            "url": "https://archive.raspberrypi.com/debian",
            "suite": "trixie",
            "components": ["main"],
            "signed_by": "keyrings/raspberrypi-archive-keyring.asc",
            "pin_priority": 990
        }
    ]
}
```

Debian keyring は Debian Trixie の `debian-archive-keyring` 2025.1 package から `debian-archive-keyring.gpg` を移植する。 package の SHA-256 は `9ea7778e443144ca490668737a8ab22dd3e748bb99e805e22ec055abeb3c7fac` 、 keyring file の SHA-256 は `506b815cbb32d9b6066b4a2aa524071e071761e7e7f68c3ac74f3061ba852017` とする。 Trixie archive / security / stable key の fingerprint は次の 3 件を確認する。

- `04B54C3CDCA79751B16BC6B5225629DF75B188BD`
- `5E04A1E3223A19A20706E20F9904613D4CCE68C6`
- `41587F7DB8C774BCCF131416762F67A0B2C39DE4`

Raspberry Pi archive keyring は webrtc-build の `2c15196` から移植する。 PR では公式配布元 `https://archive.raspberrypi.com/debian/raspberrypi.gpg.key` 、 OpenPGP fingerprint `CF8A1AF502A2AA2D763BAE7E82B129927FA3303E` 、 SHA-256 `76603890d82a492175caf17aba68dc73acb1189c9fd58ec0c19145dfa3866d56` を確認して記録する。 Ubuntu runner の system Debian keyring は Trixie key を含まないため使用しない。

### CMake と依存 archive

`_sora_fetch_sysroot()` は `raspberry-pi-os_armv8` の場合に上記 JSON を `sysroot_builder.py` へ渡す。 rootfs は 0003 と同じ `${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/rootfs` とし、 manifest による再利用と `--force` の扱いも変えない。

platform 許容一覧へ `raspberry-pi-os_armv8` を追加し、その値から WebRTC / Sora / Boost の同名 platform archive の URL と出力先を組み立てる。 OpenH264 は 0001 の Git ref 取得をそのまま再利用する。 `TARGET_OS` cache 変数の説明と許容値へ `raspberry-pi-os` を追加し、既存の `USE_V4L2` 分岐を有効にする。

Sora archive の `${SORA_DIR}/lib/libcamerac.so` が存在しない場合は configure を失敗させる。存在する場合は CMake の `install(FILES ...)` で extension と同じ `sora_sdk` package directory へ配置する。 Raspberry Pi OS 分岐では既存の `BUILD_RPATH=$ORIGIN` を維持し、 `INSTALL_RPATH=$ORIGIN` を追加する。 `libcamerac.so` の target architecture と、install 後の extension の `DT_NEEDED` / `RUNPATH` を CI で検査する。

### pyproject.toml

`SORA_SDK_TARGET=raspberry-pi-os_armv8` と Python 3.12 / 3.13 / 3.14 の組み合わせごとに 3 block を追加する。各 block は次を明示する。

- `inherit.cmake.define = "append"`
- `build-dir = "_build/raspberry-pi-os_armv8/{wheel_tag}"`
- `cmake.toolchain-file = "cmake/toolchains/linux-aarch64-cross.cmake"`
- `cmake.define.TARGET_OS = "raspberry-pi-os"`
- `cmake.define.NB_SUFFIX = ".cpython-3XY-aarch64-linux-gnu.so"`
- `cmake.define.SORA_GEN_PYI = "OFF"`
- `cmake.define.CMAKE_EXPORT_COMPILE_COMMANDS = "ON"`
- `wheel.tags = ["cp3XY-cp3XY-linux_aarch64"]`

`if.python-version` は `==3.12.*` / `==3.13.*` / `==3.14.*` とする。 `_PYTHON_HOST_PLATFORM` や wheel 生成後の `wheel tags` は使用せず、 `wheel.tags` を単一情報源にする。

### distribution 名

scikit-build-core override では PEP 621 の `project.name` を target ごとに変更できないため、 Raspberry Pi OS の CI job だけ `pyproject.toml` の完全一致行を次の順で書き換える。

1. `name = "sora_sdk"` が 1 件だけ存在することを確認する。
2. `sed` で `name = "sora_sdk_rpi"` へ置換する。
3. 置換前の値が 0 件、置換後の値が 1 件であることを確認する。

各 matrix entry は独立した checkout を使うため他 target の metadata を変更しない。 wheel の distribution 名は `sora_sdk_rpi` 、 wheel 内の package / import 名は `sora_sdk` のままとする。ローカル再現でも CI と同じ検証付き metadata 書き換えを `uv build --wheel` の直前に行う。 `SORA_SDK_TARGET` だけを指定した直接 build は公式 Raspberry Pi OS artifact の生成手順に含めない。

### テスト

`tests/test_sysroot_builder.py` に次を追加する。ネットワーク、 mock 、 stub は使用しない。

- `pin_priority` の正常値、範囲外、 `bool` 、同一 hostname の競合。
- userinfo / query / fragment / hostname 不在の URL と repository object の未知 key の拒否。
- pin 有無を区別する fingerprint 。pin 無しの互換性 test は temporary keyring を使う deterministic fixture と、変更前アルゴリズムで計算した固定 fingerprint を用い、 host の system keyring 内容に依存させない。
- host APT preferences を参照せず、期待する `preferences` stanza を生成すること。
- 実 Ubuntu JSON の load / validation smoke は Ubuntu CI で行い、 pin を持たない既存 schema の挙動が変わらないこと。

実 repository への接続と package 解決は CI の wheel build を integration test とする。

### CI

0003 後の `.github/workflows/build.yml` の `build_ubuntu` matrix に `raspberry-pi-os_armv8` を追加し、 Python 3.12 / 3.13 / 3.14 の 3 entry を ubuntu-24.04 x86_64 runner で実行する。

cross entry は `ca-certificates` と `binutils-aarch64-linux-gnu` を install する。 keyring は repository に同梱した固定内容だけを使い、 system Debian keyring は使用しない。 builder 呼び出し前に vendored Debian / Raspberry Pi keyring の SHA-256 を固定値と照合する。 `multistrap` は install しない。 `uv sync --no-install-project` を完了してから、 wheel build の直前に distribution 名を検証付きで変更する。書き換え後に lockfile を更新せず、 `SORA_SDK_TARGET=raspberry-pi-os_armv8 uv build --wheel` を実行する。

同じ Python version の `type-stubs_python-<version>` artifact を取得し、manifest の Python version、相対 path、SHA-256 を検証してから `.pyi` / `py.typed` を `src/sora_sdk/` へ配置する。`SORA_GEN_PYI=OFF` を維持し、target extension を host 上で実行しない。

次を機械検証する。

- wheel filename が `sora_sdk_rpi-*-cp3XY-cp3XY-linux_aarch64.whl` である。
- wheel 内に `sora_sdk/sora_sdk_ext.cpython-3XY-aarch64-linux-gnu.so` と `sora_sdk/libcamerac.so` がある。
- wheel 内に対応 ABI の `.pyi` / `py.typed` が各 1 件だけある。
- 両 ELF が AArch64 である。
- extension の `DT_NEEDED` に `libcamerac.so` があり、 `RUNPATH` が `$ORIGIN` を含む。
- `libcamerac.so` の `DT_NEEDED` にある `libcamera.so.*` / `libcamera-base.so.*` の各 SONAME が sysroot 内で解決できる。
- manifest の `name` / `arch` / `triplet` / `fingerprint` / `deb_files` が有効である。
- C++ 14 の `vector` header 、 `libcamera/libcamera/camera.h` 、既存 conf が要求していた ALSA / PulseAudio / udev / expat / NSS / Xext / Xtst の代表 header または library が sysroot に存在する。
- manifest の `deb_files` に `libcamera-dev_*+rpt*_arm64.deb` と一致する entry が 1 件だけある。
- manifest の `deb_files` に `libc6-dev_*+rpt*_arm64.deb` と一致する entry が 1 件だけあり、 Raspberry Pi overlay の優先が libcamera 以外にも適用されている。
- 0003 の allowlist と同じ基準で compile command 、 link command 、 CMake cache に未許可の host include / library / package config が含まれない。
- 同じ JSON で builder を 2 回呼び、 2 回目に manifest と代表 header の mtime が変わらない。

cross wheel は x86_64 host へ install せず、 pytest を実行しない。 native ubuntu-24.04 x86_64 entry の wheel install と pytest は回帰確認として維持する。

## 完了条件

- `sysroot.py` 、 `install_rootfs.sh` 、 Raspberry Pi OS 専用 toolchain を追加せず、 `sysroot_builder.py` と共通 `linux-aarch64-cross.cmake` を再利用している。
- Raspberry Pi OS 用 JSON が Trixie 、 HTTPS 、 `signed_by` 、 repository pinning を使用する。
- vendored Debian / Raspberry Pi keyring の配布元、 fingerprint 、 SHA-256 が確認され、両 file の内容が sysroot fingerprint に含まれる。
- Raspberry Pi OS 用 multistrap conf と設定 directory が削除され、 CI の package install 、実行ファイル呼び出し、 `/usr/sbin/multistrap` patch 、 `--no-auth` 、 `AllowInsecureRepositories` が残らない。 sysroot builder の設計説明にある「multistrap に依存しない」という記述は許可する。
- `ruff check` / `ruff format --check` / `ty check` / `pytest tests/test_sysroot_builder.py --timeout=10` が成功する。
- ubuntu-24.04 x86_64 host で Python 3.12 / 3.13 / 3.14 の `sora_sdk_rpi` wheel build が成功する。
- wheel tag 、 distribution / import 名、 extension suffix 、 AArch64 ELF 、 `libcamerac.so` 、 `$ORIGIN` RUNPATH が設計どおりである。
- 対応 ABI の型情報 artifact が検証され、wheel に `.pyi` / `py.typed` が各 1 件だけ含まれる。
- 実 sysroot が Raspberry Pi 版 `libcamera` と必要な header / library を含み、 `libcamerac.so` の要求する SONAME を解決でき、未許可の host dependency が混入しない。
- 同一設定の 2 回目実行が sysroot を再生成せず、 0003 の Ubuntu sysroot も回帰しない。
- native ubuntu-24.04 x86_64 build と smoke test が引き続き成功する。

## 解決方法

1. `sysroot_builder.py` の repository schema 、 fingerprint 、 APT preferences 、テストを先に拡張する。
2. Raspberry Pi OS Trixie JSON と archive keyring を追加し、実 sysroot を生成して package 解決を確認する。
3. dependency fetch component 、 CMake 構成、 project metadata を Raspberry Pi OS 対応にする。
4. CI matrix と distribution 名切替を追加し、 wheel / ELF / sysroot / host path を検証する。
5. Raspberry Pi OS 用 multistrap conf を削除し、 CI の旧実行経路が残らないことを確認する。
6. `CHANGES.md` の `## develop` にある既存 `[CHANGE]` 群へ、 `[UPDATE]` より前に次を追加する。

```text
- [CHANGE] Raspberry Pi OS wheel の生成を Trixie sysroot のクロスコンパイルへ切り替える
  - @voluntas
```

## 関連 issue への影響

- 0043 は Jetson 向け sysroot 、 Python metadata 、 package 名、 CI を単独で扱う内容へ全面改稿する。旧 Jetson multistrap conf は 0001 のレガシー経路削除で先に削除する。
- 0045 は Jetson の runtime library 解決契約と実機 E2E を扱い、0043 / 0073 の成果物と起動境界へ同期する。
- 0061 は本 issue で対象 conf 自体を削除するため、本 issue の PR で解決理由と完了日を追記するコミットと、移動だけを行う closed コミットに分けて closed にする。
- 0071 の Raspberry Pi OS cache key は `sysroot_builder.py` 、 JSON 、 vendored Debian / Raspberry Pi keyring の SHA-256 を含める。

## ロールバック

問題が発生した場合は 0004 の squash commit を `git revert` し、 0003 完了時点の Ubuntu arm64 / native build だけへ戻す。旧 conf がファイルとして戻っても CI の multistrap 経路は復活させず、 Raspberry Pi OS wheel の生成を一時停止して forward fix する。

## 参照（一次資料）

- Raspberry Pi repository `https://archive.raspberrypi.com/debian/dists/trixie/` の Trixie Release / InRelease 。
- Debian Trixie arm64 の `libstdc++-14-dev` package index 。
- Debian `debian-archive-keyring` 2025.1 package と Debian 13 archive signing key 一覧。
- webrtc-build `2c15196` の sysroot builder と Raspberry Pi archive keyring 。
- webrtc-rs の Raspberry Pi OS Trixie 用 sysroot 設定。
