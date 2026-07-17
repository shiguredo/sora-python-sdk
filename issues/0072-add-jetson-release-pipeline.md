# NVIDIA Jetson artifact の GitHub Release 配布経路を追加する

- Priority: Medium
- Created: 2026-07-17
- Updated: 2026-07-17
- Completed: -
- Model: GPT-5
- Branch: feature/add-jetson-release-pipeline
- Polished: 2026-07-17

## 目的

0043 が生成し、0045 が JetPack 6 実機で検証した `sora_sdk_jetson` wheel 3 件を、通常 PyPI release と分離した GitHub Release で安全に配布する。

release tag、対象 JetPack / Jetson Linux、Python ABI、artifact digest、実機 E2E 結果を 1 つの manifest で固定し、通常の `sora_sdk` / `sora_sdk_rpi` PyPI publish や 0066 の release artifact へ Jetson wheel を混入させない。

## 優先度根拠

- README は Jetson package binary の配布を案内しているが、0066 は未実装 Jetson を意図的に除外している。
- build と実機 import が成功しても、artifact 選択・version 対応・digest 検証の無い手動 upload では誤配布を防げない。
- 0043 / 0045 が完了するまで利用できず、通常 PyPI release の blocker にはしないため Medium とする。

## 前提

- 0043 と 0045 の完了後に実装する。
- 0066 の通常 release pipeline は Jetson を除外したまま維持する。
- `sora_sdk_jetson` は PyPI へ publish しない。
- 対象 hardware / OS は 0043 / 0045 と同じ T234 Jetson Orin family、JetPack 6、Jetson Linux r36.4 系とする。

## 設計方針

### workflow と権限

`.github/workflows/release-jetson.yml` を `workflow_dispatch` 専用で追加する。入力は SDK version、JetPack version、Jetson Linux version、artifact revision、0073 dispatcher run ID とする。0043 build artifact と 0045 E2E result は同じ trusted dispatcher run から取得する。

- workflow 全体の既定権限は `contents: read` とする。
- artifact 準備・検証 job だけ `actions: read` / `contents: read` を持ち、secret と write 権限を持たない。
- GitHub Release 作成 job だけ `contents: write` と protected environment `jetson-release` を使い、`actions: read` を持たない。検証済み staging artifact だけを受け取る。
- PyPI token、`id-token: write`、package publish action は使用しない。
- release 作成 job は全検証 job を `needs` に持ち、`if: success()` を明示する。

SDK version は `pyproject.toml` / built wheel metadata と完全一致させる。JetPack version と Jetson Linux version は 0045 実機 log の `nvidia-jetpack` / `nvidia-l4t-core` package version と対応表で照合する。自由記述の version をそのまま tag や release title に使わず、許容文字と正規化後の完全一致を検証する。

### release tag

既存の Jetson release naming policy を維持し、tag を次の形式に固定する。

```
<sdk-version>-jetson-jetpack-<jetpack-version>.<artifact-revision>
```

`artifact-revision` は 0 以上の整数とし、同じ SDK / JetPack version で wheel、release manifest、または検証済み Jetson Linux exact version / runtime contract が変わる場合に増やす。release body / manifest / README は、その revision が表す JetPack / Jetson Linux exact version の 1 組を明記する。既存 tag がある場合は asset を上書きせず failure にする。release や tag の削除・再作成で異なる file / runtime contract を同じ revision として配布しない。

### artifact manifest

GitHub API で run の repository、workflow path `.github/workflows/dispatch-jetson-e2e.yml`、event `workflow_dispatch`、run attempt `1`、protected `develop` から到達可能な workflow definition SHA、conclusion `success` を検証する。その dispatcher run から 0043 が定義する Python 3.12 / 3.13 / 3.14 の完全名 build artifact と `jetson-e2e-results` を run ID 指定で取得する。rerun された run、branch 最新 run、artifact 名の部分一致は使わない。

release manifest は少なくとも次を含む。

- SDK version、distribution `sora_sdk_jetson`。
- JetPack version、Jetson Linux version、T234 / Orin support。
- source commit SHA、dispatcher run ID / run attempt `1`、dispatcher workflow path / definition SHA、direct build job ID、self-hosted E2E job ID。
- dispatcher definition SHA の blob から取得した trusted runner mapping file SHA-256 / selected entry digest、runner lifecycle request `ephemeral`、preflight health result。
- wheel 3 件の完全 filename、size、SHA-256、Python ABI、platform tag。
- 0043 build manifest の config fingerprint、NVIDIA keyring digest、解決済み `nvidia-l4t-*` package versions / `.deb` SHA-256。0045 runtime evidence payload の実機 `nvidia-jetpack` / `nvidia-l4t-core` exact version。
- 0045 の 3 ABI import 結果、`DT_NEEDED` / `RUNPATH` validation result。
- `jetson_versions_sha256`、選択 mapping entry の全 exact value、根拠 URL。

3 build manifest と fixed dispatcher attestation の source commit SHA、build manifest SHA-256、dependency digest、sysroot fingerprint、package 集合 digest、基準 `nvidia-l4t-core` exact version を突合する。build artifact / attestation と source runtime evidence payload の wheel SHA-256 / payload digest を突合し、payload の ABI / wheel identity と build manifest を一致させる。attestation の payload / log digest、run / workflow / job metadata、build artifact digest を GitHub API と取得物から再計算して照合し、source payload 内の trusted field を採用しない。ABI ごとに payload へ記録された NVIDIA owning package 名 / exact version / architecture が build manifest の package 一覧と一致することも再検証する。

dispatcher workflow definition SHA から `jetson/trusted-runners.json` の blob を取得し、attestation の file SHA-256 / selected entry digest と一致させる。release input の JetPack / Jetson Linux exact version は source commit の `jetson/versions.json`、trusted mapping の selected entry、runtime evidence payload の実機 package exact version に完全一致させる。全項目が一致した場合だけ release manifest を生成する。

release 実行時の current protected `develop` から dispatcher workflow file と trusted mapping の同じ selected entry を再取得する。current workflow file SHA-256 と current canonical selected entry digest が attestation の pin 済み値と一致しない場合は、成功済み run であっても撤回済みとして release に使用しない。current head 自体や trusted mapping file 全体の digest は一致を要求しない。

期待する wheel は `cp312` / `cp313` / `cp314` 各 1 件、合計 3 件に固定する。余分な wheel、欠落、duplicate ABI、`sora_sdk` / `sora_sdk_rpi` distribution、x86_64 ELF、`manylinux` tag、通常 Ubuntu arm64 artifact が 1 件でもあれば failure にする。

manifest 自体の SHA-256 も job summary と release body に記載する。artifact を取得後に再計算した wheel digest が build manifest と一致しない場合は release を作成しない。

### GitHub Release

release asset は検証済み wheel 3 件と JSON manifest 1 件だけにする。sysroot、NVIDIA `.deb`、keyring、NVIDIA proprietary library、build log は asset に含めない。

release body は次を明記する。

- 対応 JetPack / Jetson Linux / Orin family。
- Python 3.12 / 3.13 / 3.14 の対応 wheel 一覧と SHA-256。
- install command は利用者の Python ABI に一致する 1 wheel を明示 path で指定すること。
- JetPack 標準 runtime package が必要で、通常 PyPI package ではないこと。
- 0045 で確認した runtime 前提と README の該当 section。

draft release を作成してから asset を追加し、全 asset の server-side name / size を再取得して manifest と照合した後に publish する。途中 failure では draft のまま残し、自動削除や既存 release の上書きをしない。

### 通常 release との分離

0066 の expected manifest と 0067 の E2E matrix は Jetson を含めない。Jetson release workflow から `release.yml` / PyPI publish job を呼ばず、通常 release workflow から Jetson release workflow を自動起動しない。

`.github/actions/download-whl` の通常 platform allowlist に Jetson を追加しない。Jetson workflow 内で run ID と完全 artifact 名を指定して取得する。

## 完了条件

- `workflow_dispatch` の明示入力と protected environment approval 無しに Jetson release が作られない。
- trusted dispatcher run の build / E2E source commit SHA が一致し、current checkout とも一致する。
- Python 3.12 / 3.13 / 3.14 の検証済み wheel が過不足なく 3 件だけ release される。
- wheel / manifest の SHA-256、JetPack / Jetson Linux package versions、sysroot fingerprint、実機 E2E 結果が release manifest に残る。
- PyPI、0066 の通常 GitHub Release、通常 E2E matrix に Jetson artifact が混入しない。
- 既存 tag / release / asset を上書きせず、途中 failure は draft release のまま停止する。
- release asset に NVIDIA package、keyring、proprietary library、sysroot を含めない。
- README の Jetson install 案内が新 tag 形式と artifact 選択方法に一致する。

## 解決方法

1. Jetson release manifest schema と validation script を追加する。
2. read-only の artifact 取得・検証 job を追加する。
3. protected environment を使う draft release 作成・asset 再検証・publish job を追加する。
4. 欠落、余剰、digest 不一致、run SHA 不一致、既存 tag の failure test を実 artifact で行う。
5. README の Jetson 配布 section を更新する。
6. `CHANGES.md` の `## develop` に次を追加する。

```
- [ADD] NVIDIA Jetson 向け wheel の GitHub Release 配布に対応する
  - @voluntas
```

## ロールバック

workflow と manifest validation を revert し、Jetson の新規 release を停止する。既に公開した正しい digest の release は削除・上書きせず、重大な問題がある場合は release body で利用停止を明示し、artifact revision を増やした修正版を新しい tag で公開する。
