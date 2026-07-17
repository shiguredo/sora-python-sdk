# NVIDIA Jetson JetPack 6 向けクロスコンパイル対応と sysroot への移行

- Priority: Medium
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: -
- Model: Opus 4.7
- Branch: feature/change-jetson-platform
- Polished: 2026-07-17

## 目的

0003 で導入する `sysroot_builder.py`、JSON 設定、共通 AArch64 toolchain を拡張し、ubuntu-24.04 x86_64 host から NVIDIA Jetson JetPack 6 向け wheel を Python 3.12 / 3.13 / 3.14 で生成できるようにする。

対象は Jetson Linux r36.4 系、Ubuntu 22.04 rootfs、T234 の Jetson Orin family とする。sysroot の system Python 3.10 を extension ABI の決定に使わず、scikit-build-core の build environment が提供する対象 CPython の header と ABI suffix を使う。これにより、現行の `python3.10` / `cpython-310` hardcode と `requires-python >= 3.12` の矛盾を解消する。

distribution 名は PyPI の通常 Ubuntu arm64 wheel と衝突しない `sora_sdk_jetson`、import package 名は既存どおり `sora_sdk` とする。本 issue は同一 run 内で入力を固定し、解決した package と digest の由来を追跡可能な Jetson wheel build artifact の生成までを扱う。repository の将来時点まで同一解決結果を再現する APT lock は本 issue の対象外とする。実機での runtime library 解決は 0045、GitHub Release での配布と E2E release gate は後続 issue で扱う。

## 優先度根拠

- README は JetPack 6 を対応 platform としているが、現行 `develop` の通常 build target には Jetson がなく、残存する cross 設定は Python 3.10 固定で package metadata と矛盾する。
- 0001 は legacy `run.py` / `buildbase.py` と到達不能な Jetson multistrap 分岐を削除するため、本 issue で新構成へ明示的に追加しない限り Jetson build は復活しない。
- Jetson は通常の PyPI release matrix とは分離して配布しており、0003 / 0004 の一般 Linux arm64 対応より利用範囲が限定されるため Medium とする。

## 前提

- 0001、0003、0004、0070 の完了後に実装する。0004 が追加する repository pinning と検証付き distribution metadata 書き換えを再利用する。
- 対象 `DEPS` version について、Sora C++ SDK release が `ubuntu-22.04_armv8_jetson` の Sora / Boost asset を公開済みであることを外部前提とする。asset が無い現行 version のまま generic arm64 asset へ代替せず、0043 の実装を開始しない。
- 0003 の `sysroot_builder.py` と `cmake/toolchains/linux-aarch64-cross.cmake` を再利用し、Jetson 専用 builder、`sysroot.py`、`install_rootfs.sh` は追加しない。
- NVIDIA の APT package は、同じ Jetson Linux release の root filesystem と組み合わせることを前提に提供される。Ubuntu Jammy と NVIDIA r36.4 の repository を混在させるのではなく、1 つの Jetson r36.4 sysroot を構成する入力として一体で固定・検証する。
- 0045 は本 issue の wheel を JetPack 6 実機へ install したときの runtime library search path を扱う。本 issue では link 時に必要な library と SONAME の解決までを検証する。

## 現状

現行の legacy Jetson 分岐には次の問題がある。

- `run.py` が `Python_ROOT_DIR=<rootfs>/usr/include/python3.10` と `NB_SUFFIX=.cpython-310-aarch64-linux-gnu.so` を固定する一方、`pyproject.toml` は Python 3.12 以上だけを対応対象としている。
- `multistrap/ubuntu-22.04_armv8_jetson.conf` は `noauth=true` を使い、Ubuntu Ports を HTTP で参照し、NVIDIA repository の `signed-by` を指定しない。
- `nvidia-jetpack`、`nvidia-l4t-camera`、`nvidia-l4t-multimedia` の解決 version と署名鍵が build manifest に残らない。
- `buildbase.py` の `libnvbuf_fdmap.so` compatibility symlink 補正は legacy `install_rootfs()` 内だけにあり、生成形式の契約として test されていない。
- Jetson target は通常 branch の `AVAILABLE_TARGETS` に存在せず、古い分岐だけが残る dead code になっている。

0001 は legacy multistrap conf と dead code を削除する。本 issue はそれらを移植せず、0003 後の scikit-build-core / sysroot builder 構成へ Jetson support を新規追加する。

## 設計方針

### target と package

build target は既存契約との互換性のため `ubuntu-22.04_armv8_jetson` とする。target、CMake、sysroot、dependency archive の対応を次に固定する。

| 項目 | 値 |
| --- | --- |
| `SORA_SDK_TARGET` / dependency root | `ubuntu-22.04_armv8_jetson` |
| `TARGET_OS` | `jetson` |
| sysroot config | `sysroot/ubuntu-22.04_armv8_jetson.json` |
| sysroot destination | `${DEPS_ROOT}/ubuntu-22.04_armv8_jetson/rootfs` |
| WebRTC archive platform | `ubuntu-22.04_armv8` |
| Sora / Boost archive platform | `ubuntu-22.04_armv8_jetson` |

`fetch_deps.cmake` の platform allowlist、`_sora_fetch_sysroot()` dispatch、target OS mapping を Jetson target へ拡張する。WebRTC だけは legacy Jetson 契約どおり generic Ubuntu 22.04 arm64 asset と 0070 の既存 digest key を使う。Sora / Boost は Jetson 専用 asset だけを許可し、generic arm64 asset へ fallback しない。

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

`sysroot/ubuntu-22.04_armv8_jetson.json` を追加する。基本 schema は 0003、repository pinning は 0004 の拡張を再利用する。

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

APT が architecture 不一致、未署名 package、release metadata の不一致、依存解決不能を報告した場合は失敗させる。package script、chroot、QEMU、root 権限は使わず、0003 と同じく download した `.deb` を `dpkg-deb --extract` する。

### Jetson 後処理

0003 の汎用 symlink 相対化後に、Jetson sysroot だけ次を検証する。

- `usr/lib/aarch64-linux-gnu/tegra` または `usr/lib/aarch64-linux-gnu/nvidia` に `libnvbuf_fdmap.so.1.0.0` がある。
- 同じ directory の `libnvbuf_fdmap.so` が無い場合だけ、basename を target とする相対 symlink を作る。
- link が既に存在する場合は、sysroot 内の実在する同一 SONAME を指すことを検証する。異なる target、dangling link、通常 file の上書きは拒否する。

この後処理は config 名を文字列比較する場当たり的な分岐にせず、JSON の allowlist 済み `postprocess` 値 `jetson-r36` で選択する。未知値は config validation で拒否し、fingerprint に含める。生成形式が変わるため、0003 の `MANIFEST_VERSION` を更新し、Ubuntu / Raspberry Pi OS の後処理が変わらない regression test を追加する。

### Python ABI と CMake

sysroot の `/usr/include/python3.10` は使用しない。cross build 用 Python 情報は 0003 の host Python discovery 契約をそのまま使う。

- scikit-build-core の isolated build environment にある `Python_EXECUTABLE`、`Python_INCLUDE_DIR`、nanobind CMake directory を host program / build input として解決する。
- `Python_ROOT_DIR` を Jetson sysroot へ向けない。
- 全 Python override で `inherit.cmake.define = "append"` と `cmake.define.TARGET_OS = "jetson"` を明示し、0001 の基底値 `ubuntu` を上書きする。
- Python version ごとに `NB_SUFFIX=.cpython-3XY-aarch64-linux-gnu.so` と `wheel.tags=["cp3XY-cp3XY-linux_aarch64"]` を明示する。
- `SORA_GEN_PYI=OFF` とし、AArch64 extension を x86_64 host 上で実行しない。
- 0003 の `type-stubs_python-<version>` artifact を manifest / SHA-256 検証後に同梱する。

`CMakeLists.txt` の Jetson 分岐は NVIDIA library の link directory を sysroot 内の `tegra` / `nvidia` に限定する。どちらか一方しか存在しない場合は存在する directory だけを追加し、両方無い場合は configure error にする。host の `/usr/lib/aarch64-linux-gnu` や `LD_LIBRARY_PATH` へ fallback しない。

0045 が runtime RPATH を確定するため、本 issue では wheel 内への NVIDIA proprietary library の複製と RPATH の追加を行わない。

### dependency archive の検証

0070 の必須集合へ `SORA_SHA256_UBUNTU_22_04_ARMV8_JETSON` と `BOOST_SHA256_UBUNTU_22_04_ARMV8_JETSON` の 2 key を追加する。WebRTC は既存の `WEBRTC_SHA256_UBUNTU_22_04_ARMV8` を再利用し、重複 key を追加しない。Jetson 専用 Sora / Boost asset のいずれかが存在しない version では generic package を流用せず、本 issue を block して対応 asset の release を待つ。

0071 の cache は正しさの前提にしない。0071 が先に完了している場合も、本 issue では Jetson target を cache 対象へ追加せず、cache 未使用で build する。Jetson の取得時間が問題になる場合は、0043 完了後に 0071 と同じ検証契約で別の performance issue を起票する。

### CI

`.github/workflows/build-jetson.yml` を `workflow_call` / `workflow_dispatch` の両方に対応させて追加し、通常 push / pull request の必須 matrix には含めない。

型情報 producer は `scripts/build_pyi_ci.py`、Jetson build は `scripts/build_jetson_ci.py` の明示 CLI に集約し、workflow YAML に同じ shell 手順を複製しない。前者は source root、Python version、artifact staging directory、後者は source root、output root、Python version、型情報 artifact / manifest、artifact staging directory を引数に取る。`build-jetson.yml` と 0073 の trusted dispatcher は両 CLI を同じ checkout 済み source SHA から順に呼ぶ。ログ / エラーは英語、コメント / test 説明は日本語とする。

両 script は top-level に `JETSON_CI_CONTRACT = {...}` という literal assignment を厳密に 1 件持つ。contract は schema version、script kind `build-pyi` / `build-jetson`、CLI argument の名前 / 型 / required、output manifest schema version だけを含み、値は Python literal とする。import や関数呼び出しを必要とする式、unknown key、重複 assignment は許可しない。0073 は script を実行せず `ast` / `ast.literal_eval` でこの declaration を検査する。

先行する `build_pyi` job は 0003 と同じ native ubuntu-24.04 x86_64 build を Python 3.12 / 3.13 / 3.14 で行い、同じ workflow run / source SHA に `type-stubs_python-3.12` / `type-stubs_python-3.13` / `type-stubs_python-3.14` を生成する。Jetson build job は `needs: [build_pyi]` で開始し、3 artifact の manifest / SHA-256 を検証する。standalone dispatch と 0073 trusted dispatcher の direct CLI 経路の両方で producer を省略しない。

Jetson build は 1 つの ubuntu-24.04 x86_64 job 内で Python 3.12、3.13、3.14 を順次 build し、workspace と sysroot を共有する。ABI ごとの matrix job には分割しない。「同一 job」の契約は Jetson cross build 3 ABI に適用し、先行する native `build_pyi` job とは分離する。

Jetson build loop の開始前に、0004 の契約を使って distribution 名を `sora_sdk` から `sora_sdk_jetson` へ 1 回だけ検証付きで変更する。変更前の値が 1 件、変更後の値が 1 件であることを確認する。各 ABI の build 前は変更後の値が 1 件であることだけを再検証し、再置換しない。

ABI ごとに空の出力 directory を作り、次の形式で interpreter と出力先を明示する。

```
SORA_SDK_TARGET=ubuntu-22.04_armv8_jetson uv build --wheel --python <3.12|3.13|3.14> --out-dir <ABI 固有 directory>
```

各 build の直後に wheel が 1 件だけであること、filename / extension suffix / `METADATA` / `WHEEL` が指定 ABI と `sora_sdk_jetson` に一致することを検証してから artifact staging directory へ移す。次 ABI の build 前に build-dir と出力 directory の target / ABI が一致し、前 ABI の wheel が混入していないことを確認する。生成物は次の完全名で ABI ごとに分離する。

ABI loop の各回で、対応する `type-stubs_python-<version>` の manifest / file SHA-256 を再検証する。前 ABI の `.pyi` / `py.typed` を staging source から除去してから対象 ABI の 2 file を `src/sora_sdk/` へ配置し、wheel 内 file の SHA-256 が型情報 manifest と一致することを確認する。Jetson build manifest に型情報 artifact 名、manifest SHA-256、`.pyi` / `py.typed` の SHA-256 を記録する。

- `jetson-build-python-3.12`
- `jetson-build-python-3.13`
- `jetson-build-python-3.14`

各 artifact は wheel 1 件と `jetson-build-manifest.json` 1 件だけを含む。0043 は `sysroot_builder.py` の manifest schema を拡張し、正規化済み package 一覧へ package 名、epoch を含む exact version、architecture、`.deb` filename / SHA-256、origin URL / suite を記録する。

build manifest は source commit SHA、workflow run ID、Python version / ABI、wheel filename / size / SHA-256、0070 の WebRTC / Sora / Boost digest、sysroot manifest filename / SHA-256 / fingerprint、NVIDIA keyring digest、基準 `nvidia-l4t-core` exact version、正規化済み package 一覧、package 集合 digest、package 数、download bytes、installed size を持つ。sysroot manifest 自体を配布 artifact に含めず、後続が必要とする非機密 metadata を build manifest へ複製する。3 artifact の sysroot fingerprint、sysroot manifest SHA-256、package 集合 digest、`nvidia-l4t-core` exact version が完全一致しなければ upload 前に失敗する。

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
- 3 ABI の build manifest が同じ source SHA、dependency digest、sysroot fingerprint、sysroot manifest SHA-256、package 集合 digest、基準 `nvidia-l4t-core` exact version を持つ。
- standalone / 0073 direct CLI の両経路で、同一 run / source SHA の 3 ABI 型情報 artifact が生成・検証される。

cross wheel は x86_64 host へ install せず、pytest や import を実行しない。実機 import は 0045 の acceptance test とする。

## テスト

`tests/test_sysroot_builder.py` に、network、mock、stub を使わず次を追加する。

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

- `sysroot.py` や Jetson 専用 builder を追加せず、0003 の `sysroot_builder.py` と共通 AArch64 toolchain を再利用している。
- Jetson JSON が Jammy / NVIDIA r36.4 common / t234 の HTTPS repository と `signed_by` を使用し、署名検証を迂回する option が無い。
- NVIDIA keyring 内容が検証されて sysroot fingerprint に含まれる。解決済み package version / `.deb` SHA-256 は正規化 package 一覧と package 集合 digest に記録・検証される。
- Python 3.10 hardcode がなく、Python 3.12 / 3.13 / 3.14 ごとに ABI と wheel tag が一致する。
- `sora_sdk_jetson` wheel 3 件が生成され、AArch64 ELF、型情報、dependency、host contamination の検査を通る。
- `nvidia-jetpack` meta-package を sysroot へ展開せず、必要 package の closure、容量、download bytes が build manifest に記録される。
- Jetson 固有 symlink 後処理が安全かつ再現可能で、他 platform の sysroot 生成を変えない。
- WebRTC は generic Ubuntu 22.04 arm64、Sora / Boost は Jetson 専用 asset という dependency mapping を維持し、0070 の SHA-256 必須検証付きで cache 無しに build できる。
- 0045 の実機検証に渡せる build artifact と manifest が保存される。
- legacy Jetson multistrap conf、`run.py` / `buildbase.py` の Jetson rootfs 分岐、`python3.10` / `cpython-310` hardcode が復活しない。

## 解決方法

1. NVIDIA r36.4 repository key と package metadata を一次資料・実 repository で確認する。
2. Jetson JSON、vendored keyring、`postprocess=jetson-r36` とテストを追加する。
3. scikit-build-core override、CMake link directory、distribution 名変更を追加する。
4. 0070 の許可済み `(dependency, archive platform)` pair 集合へ Jetson 用 Sora / Boost の 2 pair を追加する。
5. Python 3.12 / 3.13 / 3.14 の手動 CI build と artifact 検査を行う。
6. `CHANGES.md` の `## develop` に次を追加する。

```
- [ADD] NVIDIA Jetson JetPack 6 向けビルドに対応する
  - @voluntas
```

## ロールバック

0045 / 0072 が未実装なら、Jetson target、JSON、keyring、scikit-build-core override、手動 CI job を 1 つの squash commit として revert する。0045 / 0072 が実装済みなら新規 Jetson release を停止し、0072、0045、0043 の逆順で revert または workflow を無効化する。0003 / 0004 の共通 builder、toolchain、通常 Linux arm64 build は巻き戻さない。公開済み artifact は利用停止を明示し、修正版が実機検証を通るまで再配布しない。

## 参考資料

- [NVIDIA Jetson Linux r36.4 Developer Guide](https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/)
- [Software Packages and the Update Mechanism](https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html)
- [JetPack 6.1 / Jetson Linux 36.4](https://developer.nvidia.com/embedded/jetpack-sdk-61)
- [JetPack 6.2 / Jetson Linux 36.4.3](https://developer.nvidia.com/embedded/jetpack-sdk-62)
- [NVIDIA Jetson APT repository](https://repo.download.nvidia.com/jetson/)
