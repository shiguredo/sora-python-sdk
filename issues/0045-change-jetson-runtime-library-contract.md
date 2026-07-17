# NVIDIA Jetson wheel の runtime library 解決契約を実機で確定する

- Priority: Medium
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: -
- Model: Opus 4.7
- Branch: feature/change-jetson-runtime-library-contract
- Polished: 2026-07-17

## 目的

0043 が生成する `sora_sdk_jetson` wheel を、build manifest が固定した 1 組の Jetson Linux r36.4 exact version / JetPack 6.x 実機へ install し、`LD_LIBRARY_PATH` を設定しなくても `import sora_sdk` が成功する runtime library 解決契約を確定する。

NVIDIA library は wheel へ複製せず、JetPack が提供する system library を使う。変更前 wheel が system cache だけで解決できる場合は RPATH を追加せず、その結果を E2E gate / README の契約として固定する。解決できない extension の直接依存がある場合だけ、実測した必要最小限の `DT_RUNPATH` を追加する。

## 優先度根拠

- link 時に sysroot 内で library を解決できても、実機 import 時の dynamic linker search path は別契約であり、未検証 artifact を配布できない。
- Jetson は通常 PyPI matrix 外の限定 platform であり、0043 の build artifact が完成するまで着手できないため Medium とする。

## 前提

- 0043 の完了後に実装する。
- 0073 の trusted Jetson E2E dispatcher が default branch へ merge され、runner group / environment 保護設定が完了していることを前提とする。
- 1 build / release が対象にする実機は、0043 build manifest の `nvidia-l4t-core` exact version と一致する Jetson Linux r36.4 point release、および NVIDIA 公式対応表から確定した JetPack 6.x marketing version の 1 組に限定する。JetPack 6.1 / 6.2 全体を 1 回の E2E で対応済みと扱わない。
- NVIDIA proprietary library、CUDA、Tegra multimedia library は wheel へ複製しない。実機の JetPack package を runtime dependency とする。
- 0072 の GitHub Release 配布は、本 issue の全 ABI 実機検証が完了するまで開始しない。

## 現状

legacy `CMakeLists.txt` の Jetson 分岐は、link 時だけ `${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/tegra` と `${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/nvidia` を探索する。`BUILD_RPATH` / `INSTALL_RPATH` は設定せず、wheel install 後に同じ SONAME をどの directory から解決するかを検証していない。

Raspberry Pi OS の `BUILD_RPATH=$ORIGIN` は wheel 同梱の `libcamerac.so` を解決するための設定であり、system 提供の NVIDIA library を参照する Jetson へ転用しない。`$ORIGIN` だけを追加する案は採用しない。

## 設計方針

### 実機で search path を確定する

変更前 artifact について、対象 exact version の実機で次を取得し、PR の検証 log に残す。

- `/etc/nv_tegra_release`、`nvidia-l4t-core`、`nvidia-jetpack` の exact version。
- `/etc/ld.so.conf` / `/etc/ld.so.conf.d/` と `ldconfig -p` の有効 path。
- extension と再帰 dependency graph の `NEEDED` / `RPATH` / `RUNPATH`。
- `LD_DEBUG=libs` で loader が実際に選択した library realpath。
- 選択された NVIDIA library の owning package、epoch を含む exact version、architecture。

標準の `ld.so.cache` で全 edge が正しく解決できる場合、絶対 `RUNPATH` と空の cache variable は追加しない。解決できない extension の直接 `DT_NEEDED` がある場合だけ、次の directory のうち実測で必要なものを `INSTALL_RPATH` に追加する。

- `/usr/lib/aarch64-linux-gnu/tegra`
- `/usr/lib/aarch64-linux-gnu/nvidia`

存在確認していない directory、sysroot の build host path、`_deps`、wildcard は埋め込まない。`CMAKE_INSTALL_RPATH_USE_LINK_PATH` は有効化しない。

### CMake の契約

RPATH が必要な場合だけ、Jetson 分岐に `SORA_JETSON_INSTALL_RPATH` cache variable を追加する。値は CMake の `INSTALL_RPATH` 契約に合わせた semicolon 区切り list とする。

- 各 entry は absolute path、`/usr/lib/aarch64-linux-gnu/` 配下、allowlist の `tegra` / `nvidia` のいずれかであることを configure 時に検証する。
- duplicate、空 entry、`..`、build tree / sysroot path、`$ORIGIN`、未知 path を拒否する。
- `sora_sdk_ext` の `INSTALL_RPATH` だけに設定し、`BUILD_RPATH` に sysroot path を残さない。
- link option に `-Wl,--enable-new-dtags` を Jetson target だけへ明示し、GNU ld の既定値に依存せず `DT_RUNPATH` を生成する。
- install 済み extension に `DT_RPATH` と `DT_RUNPATH` を混在させない。
- Jetson 以外で variable が指定された場合は configure error にする。

extension から再帰 dependency graph を作り、各 owner ELF の直接 `DT_NEEDED` edge ごとに解決候補を判定する。extension の直接依存は system cache、wheel 内 library、interpreter 標準 library、allowlist 済み `DT_RUNPATH` directory を候補にする。間接依存は各 owner の `RUNPATH` / `RPATH` または system cache で解決し、extension の `DT_RUNPATH` が推移的に適用されるとは扱わない。`LD_DEBUG=libs` の実選択 path と graph の全 edge を照合する。

選択された file の provenance は edge ごとに次の tagged kind へ分類する。

- `wheel`: wheel filename、wheel SHA-256、`.dist-info/RECORD` entry、file SHA-256 を必須とする。
- `interpreter`: canonical Python path、interpreter version / architecture / `SOABI`、file realpath / SHA-256 を必須とする。
- `system-package`: file realpath、`dpkg -S` の owning package、epoch を含む exact version、architecture を必須とする。

NVIDIA の `system-package` だけは 0043 package 一覧との exact 一致も要求する。wheel / interpreter file に `dpkg` ownership を要求しない。どの kind にも分類できない file、複数 kind / 複数 package に該当する file を拒否する。

判定と処置を次に固定する。

| 状態 | 処置 |
| --- | --- |
| 全 edge が許可済み realpath と provenance kind ごとの必須情報を持つ | RPATH を追加せず E2E を通す |
| extension の直接 edge が未解決または不正 path を選択し、allowlist directory に正しい system-package provenance の候補が 1 件だけある | 最小の `DT_RUNPATH` を追加して再 build / 再検証する |
| 間接 edge が未解決または不正 path を選択 | extension の RUNPATH で補正せず E2E を停止する。実機 package / `ld.so.conf` / cache の不整合なら runner を修復し、wheel 同梱 owner の RUNPATH 不備ならその owner target の修正 issue、sysroot package 不足なら 0043 の再実装へ差し戻す |
| 複数候補、由来不明 file、provenance kind ごとの必須情報不一致 | E2E を停止し、候補を自動選択しない |

全 edge が許可済み結果になるまで本 issue と 0072 を完了させない。

### 実機 E2E の起動境界

本 issue の PR 内 workflow を self-hosted runner で直接実行しない。default branch 上の 0073 `dispatch-jetson-e2e.yml` を `workflow_dispatch` し、source commit SHA と `jetson/versions.json` の mapping key を入力する。dispatcher workflow definition SHA と build / E2E 対象の `source_commit_sha` は別 provenance field とし、同じ値であることを要求しない。

0073 の GitHub-hosted preparation / build job は承認対象の 40 桁 source SHA を checkout し、0043 の `scripts/build_pyi_ci.py` で 3 ABI の型情報を生成・検証してから `scripts/build_jetson_ci.py` を呼び、3 ABI wheel artifact を生成する。self-hosted job は同じ SHA から本 issue が追加する `scripts/e2e_jetson_ci.py` を呼び、固定 schema の runtime evidence payload と log を生成する。dispatcher は source 側 workflow を呼ばず、source PR が environment / runner labels / permission / cleanup step を変更できないようにする。

`scripts/e2e_jetson_ci.py` は top-level に `JETSON_CI_CONTRACT = {...}` という literal assignment を厳密に 1 件持つ。contract は schema version、script kind `e2e-jetson`、CLI argument の名前 / 型 / required、runtime evidence payload schema version だけを含み、0043 の 2 script と同じ静的 declaration 規則に従う。0073 は import / execution を行わず `ast` / `ast.literal_eval` で検査する。

dispatcher workflow SHA、source SHA、3 build manifest 内の `source_commit_sha`、download 後に計算した `build_manifest_sha256` を別 field として保存する。3 build manifest の source SHA は source input と完全一致させるが、manifest file digest や dispatcher workflow SHA と比較しない。

repository へ 0073 の保護設定済み runner が無い場合は本 issue を完了扱いにせず、0072 も開始しない。native code を install / import する前に、3 build manifest の source SHA、run ID、artifact 完全名、manifest SHA-256、wheel SHA-256、ABI、dependency digest、sysroot fingerprint、package 集合 digest を検証する。不一致 artifact を実行してから upload 前に失敗する順序を禁止する。

runner 管理側は Python 3.12 / 3.13 / 3.14 の AArch64 CPython を次の canonical path に事前配置する。workflow input / environment variable で別 path へ差し替えない。

- `/opt/sora-python/cp312/bin/python`
- `/opt/sora-python/cp313/bin/python`
- `/opt/sora-python/cp314/bin/python`

workflow から Python を install / update しない。preflight で各 path の realpath が `/opt/sora-python/<ABI>/` 内に留まること、root 所有で group / other writable ではないこと、version、AArch64、`SOABI`、free-threaded ではないこと、`venv` の利用可否を検証し、対応 wheel ABI と 1 対 1 に一致させる。

### JetPack / Jetson Linux version mapping

repository に `jetson/versions.json` を追加し、E2E / release が許可する exact version の組を machine-readable に固定する。各 entry は次を持つ。

- JetPack marketing version。
- epoch を含む `nvidia-jetpack` exact Debian version。
- epoch を含む `nvidia-l4t-core` exact Debian version。
- Jetson Linux release、SoC `t234`、APT suite `r36.4`。
- NVIDIA の根拠 URL。

unknown key、duplicate version pair、部分一致、version range を拒否する。workflow は入力、実機 package、build manifest を 1 entry と完全一致させ、mapping file の SHA-256 を fixed dispatcher attestation に記録する。外部 Web page を workflow 実行時に scrape しない。対応 version を増やす場合は根拠 URL と実機 E2E を同じ PR で追加する。

各 ABI は専用 temporary directory / virtual environment で次を行う。

1. `LD_LIBRARY_PATH`、`LD_PRELOAD`、`PYTHONPATH` を unset する。
2. 対応 wheel 1 件だけを install する。
3. `python -c "import sora_sdk; print(sora_sdk.__version__)"` を実行する。
4. extension から再帰した全 `DT_NEEDED` edge と `LD_DEBUG=libs` の実選択を突合する。
5. build host、sysroot、`_deps`、別 JetPack release の path が選択されていないことを確認する。

cleanup、environment approval、concurrency、ephemeral runner supervisor の unregister / re-image / health marker は 0073 の変更不能な dispatcher が保証する。固定 `if: always()` cleanup は補助処理とする。`scripts/e2e_jetson_ci.py` 自体も正常 / 失敗の両方で test process と専用 temporary directory を終了する。

### package provenance、runtime evidence、attestation

`LD_DEBUG` で選択された全 NVIDIA library を `dpkg -S` で owning package へ対応付け、package 名、epoch を含む exact version、architecture を 0043 build manifest の package 一覧と照合する。由来不明 file、複数 package ownership、不一致を拒否する。全 `nvidia-l4t-*` owning package は基準 `nvidia-l4t-core` と同じ upstream point release であることも検証する。

3 ABI の検証後、self-hosted job は source の `scripts/e2e_jetson_ci.py` が生成する `jetson-e2e-payload.json` と 3 ABI の `readelf` / `LD_DEBUG` log だけを固有名 artifact へ upload する。fresh GitHub-hosted `attest` job が、source 実行前に upload 済みの immutable preflight artifact と runtime artifact を検証し、`jetson-e2e-attestation.json` を別生成して、最終 `jetson-e2e-results` artifact を 1 件 upload する。

payload は runtime evidence だけを持つ。

- 3 ABI ごとの Python executable contract、version、architecture、`SOABI`、wheel filename / SHA-256、import / API smoke。
- 実機の JetPack / Jetson Linux exact version と、選択された NVIDIA library の absolute path / SONAME / owning package / exact version / architecture。
- 再帰 dependency graph、各 edge の選択 realpath、provenance kind、最終 `RUNPATH` validation result。

attestation は source script の自己申告や self-hosted workspace を使わず、fresh GitHub-hosted `attest` job が payload / log digest と trusted metadata を結合して生成する。

- source commit SHA、dispatcher run ID / run attempt `1`、workflow path / definition SHA、GitHub-hosted build job ID、self-hosted E2E job ID。
- dispatcher definition SHA の blob から取得した trusted runner mapping file SHA-256 / selected entry digest、runner lifecycle request `ephemeral`、runner preflight health result。
- `jetson_versions_sha256`、選択 entry の JetPack marketing version、`nvidia-jetpack` / `nvidia-l4t-core` exact version、Jetson Linux release、SoC、suite、根拠 URL。
- build artifact 名、wheel filename / SHA-256、build manifest SHA-256、dependency digest、sysroot fingerprint、package 集合 digest。
- runtime evidence payload と各 log の SHA-256。

wheel / build manifest digest が 0043 artifact と一致しない場合は upload 前に失敗する。mock、stub、QEMU 上の import は実機 E2E の代替にしない。

### README

Jetson section に次を明記する。

- E2E 済み Jetson Linux exact version / JetPack marketing version の組と SoC family。未検証の JetPack 6.x 全体を対応対象と書かない。
- `sora_sdk_jetson` は通常 PyPI package ではなく専用 artifact から install すること。
- JetPack 標準 package / dynamic linker 設定を runtime dependency とし、NVIDIA library を wheel に同梱しないこと。
- `LD_LIBRARY_PATH` の手動設定を通常手順として要求しないこと。

## 完了条件

- build manifest と一致する 1 組の JetPack / Jetson Linux exact version 実機で Python 3.12 / 3.13 / 3.14 の全 wheel を import できる。
- 再帰 dependency graph の全 edge が実機 loader の選択結果と一致し、別 JetPack release や build host の library を読まない。
- `DT_RUNPATH` は実測で必要な JetPack 標準 directory だけを含むか、system cache だけで十分なら存在しない。
- 選択された全 NVIDIA library の owning package / exact version / architecture が build manifest と一致する。
- wheel に NVIDIA proprietary library を追加していない。
- 0073 の trusted dispatcher だけが専用・承認制・単一実行・無 secret の ephemeral self-hosted runner を使用し、実行前 provenance 検証、supervisor の unregister / re-image / health marker、補助 cleanup を保証する。
- source runtime evidence payload と fixed dispatcher attestation が分離され、両者の digest 結合により 3 ABI の input / runtime provenance と binary metadata を保持する。
- 0073 の `jetson-e2e` environment / selected-workflow runner group 保護、canonical Python path、`jetson/versions.json` の exact mapping が検証される。
- default branch の trusted dispatcher から本 issue の exact source SHA を指定した E2E が完了する。merge 直前に maintainer 2 名が、現在の PR head SHA、dispatcher input SHA、attestation の source SHA、再計算した payload / log digest と attestation field、run URL、attestation digest の一致を確認して PR に記録する。GitHub の自動 required check とは呼ばない。
- README が検証済み exact version、配布方法、runtime dependency を明記する。
- Ubuntu、Raspberry Pi OS、macOS、Windows wheel の RPATH / RUNPATH が変わらない。

## 解決方法

1. 変更前 artifact の dynamic linker 解決結果と package provenance を実機で採取する。
2. 必要な場合だけ `SORA_JETSON_INSTALL_RPATH` と validation を追加する。
3. `scripts/e2e_jetson_ci.py` と version / provenance validation を追加し、0073 dispatcher から exact source SHA を指定して実行する。
4. 3 ABI の実機 E2E と他 platform の binary metadata regression test を行う。
5. README の Jetson runtime 前提を更新する。
6. `CHANGES.md` の `## develop` に次を追加する。

```
- [CHANGE] NVIDIA Jetson の runtime library 解決契約を実機 E2E で検証する
  - @voluntas
```

## ロールバック

RPATH または E2E workflow に regression が出た場合は新規 Jetson release を停止する。0072 が実装済みなら先に 0072 workflow を revert または無効化し、その後に本 issue の squash commit を revert する。0043 の build workflow は runtime regression の影響を受けない限り維持してよい。公開済み artifact は 0072 の方針で利用停止を明示し、`LD_LIBRARY_PATH` の追加を恒久回避策として案内せず、実機の `ldconfig` と SONAME を再調査して forward fix する。

## 参考資料

- [CMake `INSTALL_RPATH`](https://cmake.org/cmake/help/latest/prop_tgt/INSTALL_RPATH.html)
- [GNU ld `--enable-new-dtags`](https://sourceware.org/binutils/docs/ld.html)
- [NVIDIA Jetson Linux r36.4 Developer Guide](https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/)
- [JetPack 6.1 / Jetson Linux 36.4](https://developer.nvidia.com/embedded/jetpack-sdk-61)
- [JetPack 6.2 / Jetson Linux 36.4.3](https://developer.nvidia.com/embedded/jetpack-sdk-62)
