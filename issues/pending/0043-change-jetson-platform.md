# NVIDIA Jetson JetPack 6 向けクロスコンパイル対応と sysroot への移行

- Priority: Medium
- Created: 2026-06-23
- Updated: 2026-08-19
- Completed: -
- Model: Opus 4.7
- Branch: feature/change-jetson-platform
- Polished: 2026-07-30

## 目的

0074 で導入した `sysroot_builder.py` と `sysroot/*.json` 構成を拡張し、ubuntu-24.04 x86_64 host から NVIDIA Jetson JetPack 6 向け wheel を Python 3.12 / 3.13 / 3.14 で生成できるようにする。

対象は Jetson Linux r36.4 系、Ubuntu 22.04 rootfs、T234 の Jetson Orin family とする。sysroot の system Python 3.10 を extension ABI の決定に使わず、`run.py` が build 実行時の host CPython から解決する `Python_INCLUDE_DIR` / `Python_EXECUTABLE` と `NB_SUFFIX` を使う。これにより、現行の `python3.10` / `cpython-310` hardcode と `requires-python >= 3.12` の矛盾を解消する。

distribution 名は PyPI の通常 Ubuntu arm64 wheel と衝突しない `sora_sdk_jetson`、import package 名は既存どおり `sora_sdk` とする。本 issue は同一 run 内で入力を固定し、解決した package と digest の由来を追跡可能な Jetson wheel build artifact の生成までを扱う。repository の将来時点まで同一解決結果を再現する APT lock は本 issue の対象外とする。実機での runtime library 解決は 0045、GitHub Release での配布と E2E release gate は後続 issue で扱う。

なお、通常 Ubuntu arm64 wheel は 26.04 / 24.04 のみをサポートし 22.04 は `CHANGES.md` でサポート終了済みだが、本 issue の `ubuntu-22.04_armv8_jetson` という target 名は Jetson Linux r36.4 の Jammy rootfs 由来の互換対象名であり、通常 Ubuntu wheel の対応終了とは矛盾しない。

## 優先度根拠

- README は JetPack 6 を対応 platform としているが、通常 build target には Jetson がなく、残存する Jetson multistrap 分岐は Python 3.10 固定で package metadata と矛盾する。
- 0001 / 0003 / 0004 は実装せず closed され、0074 が `run.py` + `sysroot_builder.py` 経路で Ubuntu arm64 / Raspberry Pi OS の sysroot 置換を完了した。Jetson は 0074 で multistrap 経路のまま残置されたため、本 issue で新構成へ明示的に追加しない限り Jetson build は復元しない。
- Jetson は通常の PyPI release matrix とは分離して配布しており、0074 の一般 Linux arm64 対応より利用範囲が限定されるため Medium とする。

## 前提

- 0074 の完了後に実装する。0074 が追加した `sysroot_builder.py` の `RepositoryConfig.pin_priority` / `install_sysroot()` / `sysroot/*.json` / `sysroot/keyrings/` 構成と、検証付き distribution metadata 書き換えの手順を再利用する。0001 / 0003 / 0004 は scikit-build-core 前提で実装せず closed されており、0070 の依存 archive SHA-256 検証も `fetch_deps.cmake` が存在しないため未実装である。本 issue は `buildbase.py` が提供する archive 取得の既存経路をそのまま使い、archive の SHA-256 検証は別途導入されるまで対象外とする。
- 対象 `DEPS` version について、Sora C++ SDK release が `ubuntu-22.04_armv8_jetson` の Sora / Boost asset を公開済みであることを外部前提とする。asset が無い現行 version のまま generic arm64 asset へ代替せず、0043 の実装を開始しない（本 check は PR 作成前に `DEPS` の `SORA_CPP_SDK_VERSION` に対応する GitHub Release asset の存在で確認する）。
- 0074 の `sysroot_builder.py` を再利用し、Jetson 専用 builder、`sysroot.py`、`install_rootfs.sh`、`cmake/toolchains/` は追加しない。cross compile の compiler / sysroot 設定は 0074 と同様に `run.py` の `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` 直指定を維持する。
- NVIDIA の APT package は、同じ Jetson Linux release の root filesystem と組み合わせることを前提に提供される。Ubuntu Jammy と NVIDIA r36.4 の repository を混在させるのではなく、1 つの Jetson r36.4 sysroot を構成する入力として一体で固定・検証する。
- 0045 は本 issue の wheel を JetPack 6 実機へ install したときの runtime library search path を扱う。本 issue では link 時に必要な library と SONAME の解決までを検証する。

## 現状

現行の Jetson 分岐には次の問題がある。

- `run.py` が `Python_ROOT_DIR=<rootfs>/usr/include/python3.10` と `NB_SUFFIX=.cpython-310-aarch64-linux-gnu.so` を固定する一方、`pyproject.toml` は Python 3.12 以上だけを対応対象としている。
- `multistrap/ubuntu-22.04_armv8_jetson.conf` は `noauth=true` を使い、Ubuntu Ports を HTTP で参照し、NVIDIA repository の `signed-by` を指定しない（現行 conf は `r36.3` / `libstdc++-10-dev` / `nvidia-jetpack` の旧構成のまま）。
- `nvidia-jetpack`、`nvidia-l4t-camera`、`nvidia-l4t-multimedia` の解決 version と署名鍵が build manifest に残らない。
- `buildbase.py` の `libnvbuf_fdmap.so` compatibility symlink 補正は legacy `install_rootfs()` 内だけにあり、生成形式の契約として test されていない。
- `run.py` の `AVAILABLE_TARGETS` には `ubuntu-22.04_armv8_jetson` が残るが、`install_deps()` は Jetson だけ旧 `multistrap` + `install_rootfs()` 経路のままであり、0074 で導入した署名検証付き sysroot 経路へ移行していない。

0074 は Ubuntu arm64 と Raspberry Pi OS の rootfs 生成を `sysroot_builder.py` へ移行したが、Jetson の `multistrap/ubuntu-22.04_armv8_jetson.conf` と `run.py` / `buildbase.py` の Jetson rootfs 分岐は意図的に残置された。本 issue はそれらを移植せず、0074 後の `run.py` + `sysroot_builder.py` 構成へ Jetson support を新規追加する。

## 設計方針

### target と package

build target は既存契約との互換性のため `ubuntu-22.04_armv8_jetson` とする。target、CMake、sysroot、dependency archive の対応を次に固定する。

| 項目 | 値 |
| --- | --- |
| `SORA_SDK_TARGET` / dependency root | `ubuntu-22.04_armv8_jetson` |
| `TARGET_OS` | `jetson` |
| sysroot config | `sysroot/ubuntu-22.04_armv8_jetson.json` |
| sysroot destination | `_install/ubuntu-22.04_armv8_jetson/rootfs` |
| WebRTC archive platform | `ubuntu-22.04_armv8` |
| Sora / Boost archive platform | `ubuntu-22.04_armv8_jetson` |

`run.py` の `AVAILABLE_TARGETS` / `install_deps()` dispatch と `buildbase.py` の archive 取得 dispatch、CMake の `TARGET_OS` 判定を Jetson target へ拡張する。WebRTC だけは legacy Jetson 契約どおり generic Ubuntu 22.04 arm64 asset を使う。Sora / Boost は Jetson 専用 asset だけを許可し、generic arm64 asset へ fallback しない。archive の SHA-256 検証は 0070 が未実装のため、本 issue では既存の `buildbase.py` 経路の download 検証をそのまま用いる。

- target OS: `jetson`
- architecture: `aarch64`
- Jetson Linux: r36.4 系
- JetPack: 6.1 / 6.2 系（Jetson Linux r36.4 系を使う release）
- SoC repository: `t234`
- Python ABI: `cp312` / `cp313` / `cp314`
- wheel tag: `linux_aarch64`
- distribution: `sora_sdk_jetson`
- import package: `sora_sdk`

Jetson Linux r36.4 の point release は APT が取得した `.deb` filename と version を sysroot manifest に記録する。`nvidia-l4t-core` の exact version を基準 version とし、全 `nvidia-l4t-*` package の Debian upstream version が同じ r36.4 point release であることを検証する。CUDA 等の compute package は L4T version 形式を持たないため「r36.4 系」という文字列検査を行わず、APT が解決した dependency closure と exact `.deb` digest を記録する。JetPack marketing version は 0045 実機の `nvidia-jetpack` package version と NVIDIA 公式対応表から確定する。

3 ABI を同一 job の同一 checkout で順次 build し、最初に生成した 1 つの sysroot を再利用する。release 途中で `--force` による再解決を行わない。r36.5 以降への更新は package version、実機検証、Sora C++ SDK の Jetson asset を同時に更新する別 issue とする。

### sysroot JSON と署名検証

`sysroot/ubuntu-22.04_armv8_jetson.json` を追加する。基本 schema は 0074 の `sysroot/ubuntu-24.04_armv8.json` / `sysroot/raspberry-pi-os_armv8.json`、repository pinning は 0074 の `pin_priority` 拡張を再利用する。

repository は次の 3 件だけを許可する。

| repository | suite | components | pin priority |
| --- | --- | --- | --- |
| `https://ports.ubuntu.com/ubuntu-ports` | `jammy` | `main universe` | 500 |
| `https://repo.download.nvidia.com/jetson/common` | `r36.4` | `main` | 700 |
| `https://repo.download.nvidia.com/jetson/t234` | `r36.4` | `main` | 700 |

Ubuntu repository は runner の `/usr/share/keyrings/ubuntu-archive-keyring.gpg` を使用する。NVIDIA の `jetson-ota-public.asc` は official repository から取得した内容を `sysroot/keyrings/` に vendoring し、JSON では repository 相対 path で `signed_by` を指定する。

vendoring 時に次の値を再確認し、PR の検証 log と test expectation に記録する。

- primary fingerprint: `3C6D1FF3100C8C3ABB0869C0E6543461A9996195`
- encryption subkey fingerprint: `13ADEA72CD3B449D4C77CA7A84F3CEB8E58DF1E8`
- signing subkey fingerprint: `13804AEEB181616F3B4964270D296FFB880FB004`
- vendored `jetson-ota-public.asc` の SHA-256: `576f852981855e5c6cfb9b625ffb51b984ca451f1181b2e70435b005034fad55`

key file は primary key 1 件、encryption subkey 1 件、signing subkey 1 件だけを含むことを `gpg --show-keys --with-colons` で検証する。capability は primary が `sc`、encryption subkey が `e`、signing subkey が `s` を持つことを確認する。未知の primary key / subkey、fingerprint、capability、digest の不一致があれば build を停止する。CI は `gnupg` を明示 install し、`apt-key`、`trusted=yes`、`--allow-unauthenticated`、`AllowInsecureRepositories` は使用しない。

package 集合は legacy conf の意図を維持し、次を明示する。

- `libstdc++-11-dev`
- `libc6-dev`
- `libxext-dev`
- `libdbus-1-dev`
- `nvidia-l4t-core`
- `nvidia-l4t-camera`
- `nvidia-l4t-multimedia`
- `nvidia-l4t-multimedia-utils`
- `nvidia-l4t-jetson-multimedia-api`

`nvidia-jetpack` meta-package は CUDA toolkit、sample、documentation 等の build に不要な大規模 dependency を含むため sysroot package 集合へ入れない。上記 5 NVIDIA package と通常 library の transitive dependency だけを APT で解決する。Sora C++ SDK の再帰 `DT_NEEDED` 検査で不足 package が判明した場合は、SONAME と追加 package の対応根拠を PR に記録して package 名を明示追加する。`nvidia-jetpack` で不足を一括補完しない。

APT の download 前に `--print-uris` と package metadata から package 数 / download bytes / installed size を集計し、job summary と build manifest に記録する。runner の開始時空き容量から download、展開、一時領域を差し引いて 5 GiB 以上残らない見積もりなら download 前に失敗する。workflow timeout は 60 分とし、超過時に timeout を延ばす前に package 集合を再調査する。

APT が architecture 不一致、未署名 package、release metadata の不一致、依存解決不能を報告した場合は失敗させる。package script、chroot、QEMU、root 権限は使わず、0074 と同じく download した `.deb` を `dpkg-deb --extract` する。

### Jetson 後処理

0074 の汎用 symlink 相対化後に、Jetson sysroot だけ次を検証する。

- `usr/lib/aarch64-linux-gnu/tegra` または `usr/lib/aarch64-linux-gnu/nvidia` に `libnvbuf_fdmap.so.1.0.0` がある。
- 同じ directory の `libnvbuf_fdmap.so` が無い場合だけ、basename を target とする相対 symlink を作る。
- link が既に存在する場合は、sysroot 内の実在する同一 SONAME を指すことを検証する。異なる target、dangling link、通常 file の上書きは拒否する。

この後処理は config 名を文字列比較する場当たり的な分岐にせず、JSON の allowlist 済み `postprocess` 値 `jetson-r36` で選択する。未知値は config validation で拒否し、fingerprint に含める。生成形式が変わるため、`sysroot_builder.py` の `MANIFEST_VERSION` を `1` から `2` へ更新し、Ubuntu / Raspberry Pi OS の後処理が変わらない regression test を追加する。

### Python ABI と CMake

sysroot の `/usr/include/python3.10` は使用しない。cross build 用 Python 情報は 0074 と同様に `run.py` の host Python 解決契約をそのまま使う。

- `pypath.get_python_include_dir()` / `pypath.get_python_version()` と `sys.executable` を host program / build input として解決する。
- `Python_ROOT_DIR` を Jetson sysroot へ向けない（`run.py` の Jetson 分岐から `Python_ROOT_DIR=.../python3.10` の hardcode を削除する）。
- `run.py` の `install_deps()` と CMake 呼び出しで `TARGET_OS=jetson` を明示し、`NB_SUFFIX` を Python version から動的に `".cpython-{XY}-aarch64-linux-gnu.so"` として組み立てる（例: 3.12 → `312`）。
- `SORA_GEN_PYI` は cross では host 上で実行できないため付与せず、型情報は 0074 と同様に native `build_pyi` で生成した `sora_sdk/py.typed` / `sora_sdk/sora_sdk_ext.pyi` を manifest / SHA-256 検証後に `src/sora_sdk/` へ配置して同梱する。

`CMakeLists.txt` の Jetson 分岐は NVIDIA library の link directory を sysroot 内の `tegra` / `nvidia` に限定する。どちらか一方しか存在しない場合は存在する directory だけを追加し、両方無い場合は configure error にする。host の `/usr/lib/aarch64-linux-gnu` や `LD_LIBRARY_PATH` へ fallback しない。

0045 が runtime RPATH を確定するため、本 issue では wheel 内への NVIDIA proprietary library の複製と RPATH の追加を行わない。

### dependency archive の検証

0070 は `fetch_deps.cmake` が存在しないため未実装であり、本 issue では `buildbase.py` の既存 archive 取得をそのまま使う。Jetson 用 Sora / Boost は `ubuntu-22.04_armv8_jetson` platform の専用 asset だけを許可し、generic `ubuntu-22.04_armv8` asset へ fallback しない。WebRTC は legacy 契約どおり generic `ubuntu-22.04_armv8` asset を使う。Jetson 専用 Sora / Boost asset のいずれかが存在しない `DEPS` version では generic package を流用せず、本 issue を block して対応 asset の release を待つ。将来 0070 相当の SHA-256 検証が導入された際は、`SORA_SHA256_UBUNTU_22_04_ARMV8_JETSON` と `BOOST_SHA256_UBUNTU_22_04_ARMV8_JETSON` の 2 key を必須集合へ追加し、WebRTC は既存 key を再利用する。

0071 の cache は正しさの前提にしない。0071 は 2026-07-23 に closed 済みで `sysroot/*.json` / `sysroot_builder.py` を cache key に含む。本 issue では Jetson JSON 追加に合わせて cache key を更新するが、Jetson の取得時間が問題になる場合は、0043 完了後に別 issue で cache 戦略を再検討する。

### CI

`.github/workflows/build-jetson.yml` を `workflow_dispatch`（必要に応じて `workflow_call`）で追加し、通常 push / pull request の必須 matrix には含めない。0073 の trusted dispatcher が存在する場合は本 workflow を dispatcher から呼ぶ形を優先し、PR 内の workflow 改変で self-hosted runner を直接起動できない境界を維持する。ログ / エラーは英語、コメント / test 説明は日本語とする。

先行する `build_pyi` job は既存 `.github/workflows/build.yml` の `build_pyi` と同じ手順で ubuntu-24.04 x86_64 上で Python 3.12 / 3.13 / 3.14 の型情報 artifact `sora_sdk_3.12` / `sora_sdk_3.13` / `sora_sdk_3.14` を生成する。本 workflow 内で再実装する場合は `uv run python run.py build ubuntu-24.04_x86_64` + `.pyi` / `py.typed` 抽出の同一手順を用い、同一 workflow run / source SHA に 3 artifact を生成する。Jetson build job は `needs: [build_pyi]` で開始し、3 artifact の存在と SHA を検証する。

Jetson build は 1 つの ubuntu-24.04 x86_64 job 内で Python 3.12、3.13、3.14 を順次 build し、workspace と sysroot を共有する。ABI ごとの matrix job には分割しない。「同一 job」の契約は Jetson cross build 3 ABI に適用し、先行する native `build_pyi` job とは分離する。1 つの sysroot を 3 ABI で再利用することで、同一 fingerprint / package 集合での再現性を担保する。

Jetson build loop の開始前に、0074 の契約を使って `pyproject.toml` の distribution 名を `sora_sdk` から `sora_sdk_jetson` へ 1 回だけ検証付きで変更する。変更前の値が 1 件、変更後の値が 1 件であることを確認する。各 ABI の build 前は変更後の値が 1 件であることだけを再検証し、再置換しない（0074 の Raspberry Pi OS と同じ検証手順）。

ABI ごとに loop 内で次を行う（0074 の `build_ubuntu` と同じ `run.py` 経路を用い、scikit-build-core の `uv build --python` 形式は使わない）。

1. 対応 `sora_sdk_<version>` artifact の `py.typed` / `sora_sdk_ext.pyi` を SHA-256 検証後に `src/sora_sdk/` へ配置する。前 ABI の file が残っていれば除去してから配置し、配置後の file SHA-256 が artifact と一致することを確認する。
2. 対応 Python version の `uv` toolchain で `SORA_SDK_TARGET=ubuntu-22.04_armv8_jetson uv run python run.py build ubuntu-22.04_armv8_jetson` と `uv build` を実行する（`uv build --out-dir` ではなく `dist/` 固定。ABI ごとに `dist/` を空にしてから build し、生成物が 1 件だけであることを確認してから staging へ退避する）。
3. 各 build 直後に wheel filename / extension suffix / `METADATA` / `WHEEL` が指定 ABI と `sora_sdk_jetson` に一致することを検証する。次 ABI の build 前に `_build` と `dist` / `src/sora_sdk/*.so` が前 ABI の混入無しであることを確認する。

生成物は次の完全名で ABI ごとに分離する。

- `jetson-build-python-3.12`
- `jetson-build-python-3.13`
- `jetson-build-python-3.14`

各 artifact は wheel 1 件と `jetson-build-manifest.json` 1 件だけを含む。本 issue で `sysroot_builder.py` の manifest に正規化済み package 一覧（package 名、epoch を含む exact version、architecture、`.deb` filename / SHA-256、origin URL / suite）を追加し、fingerprint 対象も拡張する。旧 sysroot は `MANIFEST_VERSION=1` のまま拒否される。

build manifest は source commit SHA、workflow run ID、Python version / ABI、wheel filename / size / SHA-256、WebRTC / Sora / Boost の archive 入手元（URL と `DEPS` version、将来 SHA-256 検証が入れば digest も含む）、sysroot manifest filename / SHA-256 / fingerprint、NVIDIA keyring digest、基準 `nvidia-l4t-core` exact version、正規化済み package 一覧、package 集合 digest、package 数、download bytes、installed size を持つ。sysroot manifest 自体を配布 artifact に含めず、後続が必要とする非機密 metadata を build manifest へ複製する。3 artifact の sysroot fingerprint、sysroot manifest SHA-256、package 集合 digest、`nvidia-l4t-core` exact version が完全一致しなければ upload 前に失敗する。

次を機械検証する。

- wheel filename が `sora_sdk_jetson-*-cp3XY-cp3XY-linux_aarch64.whl` である。
- extension suffix が `sora_sdk_ext.cpython-3XY-aarch64-linux-gnu.so` である。
- extension が AArch64 ELF であり、x86_64 object / library を含まない。
- 対応 ABI の `.pyi` / `py.typed` が各 1 件だけある。
- extension を root として、wheel 同梱 library、Sora / WebRTC / Boost dependency、Jetson sysroot 内の AArch64 ELF を再帰走査し、全 `DT_NEEDED` SONAME が 1 か所だけで解決できる。cycle は inode / normalized path の visited set で停止し、glibc、dynamic loader、libgcc、libstdc++ も sysroot 内の実 file まで解決する。host library への fallback と同一 SONAME の複数候補を拒否する。
- link command、compile command、CMake cache に未許可の host include / library / package config がない。
- CMake cache の `TARGET_OS` が `jetson` であり、sysroot / archive platform の対応が上表と一致する。
- sysroot manifest に config fingerprint、keyring digest、APT が解決した全 `.deb` filename がある。
- `nvidia-l4t-core` と全 `nvidia-l4t-*` package が同じ exact r36.4 point release であり、別 minor / point release が混入しない。
- `libnvbuf_fdmap.so` compatibility link と target が sysroot 内で完結する。
- 3 ABI の build manifest が同じ source SHA、sysroot fingerprint、sysroot manifest SHA-256、package 集合 digest、基準 `nvidia-l4t-core` exact version を持つ。

cross wheel は x86_64 host へ install せず、pytest や import を実行しない。実機 import は 0045 の acceptance test とする。0073 が存在する場合の `workflow_call` 経路でも同一検証を通す。

## テスト

`tests/sysroot_builder/test_sysroot_builder.py` に、network、mock、stub を使わず次を追加する。現行 0074 の unit test は `pytest --confcutdir=tests/sysroot_builder` で実行し、親 `tests/conftest.py` の `sora_sdk` import を回避する運用を維持する。

- `postprocess` の省略、`jetson-r36`、未知値の validation と fingerprint 差分。
- temporary sysroot fixture に対する `libnvbuf_fdmap.so` link の作成、正しい既存 link の再利用、誤 target / dangling link / 通常 file の拒否。
- Jetson JSON の load、HTTPS、repository、pin、package、keyring path の validation。
- Ubuntu / Raspberry Pi OS config に Jetson 後処理が適用されない regression test。
- `apt-get --print-uris` / package metadata の正常・異常形式、epoch を含む Debian version、architecture、origin / suite の正規化。
- 小さな実 `.deb` fixture の SHA-256 一致 / 不一致、package 順序に依存しない集合 digest、duplicate package / filename / origin ambiguity の拒否。
- package 数 / download bytes / installed size の計算、未知 size、整数 overflow、5 GiB 空き容量境界。
- 拡張 manifest の read / reuse、旧 `MANIFEST_VERSION` の拒否。

parser / manifest test は local metadata と小さな実 `.deb` fixture を使用し、network、mock、stub を使わない。実 APT repository への接続、package 解決、archive 取得、wheel build は手動 CI job の integration test とする。

## 完了条件

- `sysroot.py` や Jetson 専用 builder、`cmake/toolchains/` を追加せず、0074 の `sysroot_builder.py` を再利用している。
- Jetson JSON が Jammy / NVIDIA r36.4 common / t234 の HTTPS repository と `signed_by` を使用し、署名検証を迂回する option が無い。
- NVIDIA keyring 内容が検証されて sysroot fingerprint に含まれる。解決済み package version / `.deb` SHA-256 は正規化 package 一覧と package 集合 digest に記録・検証される。
- Python 3.10 hardcode がなく、Python 3.12 / 3.13 / 3.14 ごとに ABI と wheel tag が一致する。
- `sora_sdk_jetson` wheel 3 件が生成され、AArch64 ELF、型情報、dependency、host contamination の検査を通る。
- `nvidia-jetpack` meta-package を sysroot へ展開せず、必要 package の closure、容量、download bytes が build manifest に記録される。
- Jetson 固有 symlink 後処理が安全かつ再現可能で、他 platform の sysroot 生成を変えない。
- WebRTC は generic Ubuntu 22.04 arm64、Sora / Boost は Jetson 専用 asset という dependency mapping を維持し、0070 相当の SHA-256 検証が未導入の間は既存 `buildbase.py` の取得検証のまま build できる。
- 0045 の実機検証に渡せる build artifact と manifest が保存される。
- legacy Jetson multistrap conf、`run.py` / `buildbase.py` の Jetson rootfs 分岐、`python3.10` / `cpython-310` hardcode が復活しない。

## 解決方法

1. NVIDIA r36.4 repository key と package metadata を一次資料・実 repository で確認する。
2. Jetson JSON、vendored keyring、`postprocess=jetson-r36` とテストを追加する。（同時に `multistrap/ubuntu-22.04_armv8_jetson.conf` を削除する）。
3. `run.py` の Jetson 分岐と `CMakeLists.txt` の link directory 限定、distribution 名変更を追加する。
4. `buildbase.py` の Jetson 専用 Sora / Boost 取得分岐を追加し、generic fallback を禁止する（将来 0070 相当の SHA-256 検証が入れば allowlist へ Jetson 2 pair を追加する）。
5. Python 3.12 / 3.13 / 3.14 の手動 CI build と artifact 検査を行う。
6. `CHANGES.md` の `## develop` に次を追加する。

```
- [ADD] NVIDIA Jetson JetPack 6 向けビルドに対応する
  - @voluntas
```

## ロールバック

0045 / 0072 が未実装なら、Jetson target、JSON、keyring、`run.py` の Jetson 対応、手動 CI job を 1 つの squash commit として revert する。0045 / 0072 が実装済みなら新規 Jetson release を停止し、0072、0045、0043 の逆順で revert または workflow を無効化する。0074 の共通 builder、通常 Linux arm64 build は巻き戻さない。公開済み artifact は利用停止を明示し、修正版が実機検証を通るまで再配布しない。

## 参考資料

- [NVIDIA Jetson Linux r36.4 Developer Guide](https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/)
- [Software Packages and the Update Mechanism](https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html)
- [JetPack 6.1 / Jetson Linux 36.4](https://developer.nvidia.com/embedded/jetpack-sdk-61)
- [JetPack 6.2 / Jetson Linux 36.4.3](https://developer.nvidia.com/embedded/jetpack-sdk-62)
- [NVIDIA Jetson APT repository](https://repo.download.nvidia.com/jetson/)

## pending にした理由

Jetson 対応を一旦保留する方針になったため pending にする。対応を再開するときは reopened にしてから実装を進める。
