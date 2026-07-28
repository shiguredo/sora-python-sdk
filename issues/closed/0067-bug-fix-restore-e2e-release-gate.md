# E2E workflow を復活して release gate として定義する

- Priority: High
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: 2026-07-28
- Model: GPT-5
- Branch: feature/fix-restore-e2e-release-gate
- Polished: 2026-07-17

## 目的

0001 で一時停止する E2E workflow を scikit-build-core の artifact 契約へ同期して復活させ、build workflow 内の `e2e_test` job を後続 release pipeline の必須 gate として定義する。

build だけの成功通知で E2E failure を見落とさないように、branch build の最終結果と Slack 通知も E2E まで含める。

## 優先度根拠

- E2E を通さず native wheel を外部公開すると、build / import smoke では検出できない signaling・media・hardware 経路の不具合を release し得る。
- 0066 は本 issue の `e2e_test` success を publish 前提にするため、release 再開前の必須 issue として High とする。

## 前提

- 0001 〜 0005、0051、0052 の完了後に実装する。
- Python version matrix の 3.12 / 3.14 追加は 0053 の責務とし、本 issue は現在有効な 3.13 だけを復活させる。
- schedule は無効のまま維持する。
- publish / GitHub Release job 自体は 0066 で追加する。本 issue は名前と結果が安定した gate を先に提供する。

## 現状

0001 は backend 移行中に壊れた release を防ぐため、build.yml の旧 `e2e_test` caller を削除し、`e2e-test.yml` の全 job を `if: false` にする。

既存 E2E matrix には、0001 後に build しない Ubuntu 22.04 x86_64 が残る。macos-15 runner は `macos-15_arm64` artifact を参照するが、0066 の配布方針では macOS 14.0 wheel が canonical になる。artifact 選択も `find ... | head -1` で 0 / 複数件を区別しない。

旧 `slack_notify` は build job だけを `needs` に持つため、E2E の失敗前に success を通知し得る。

## 設計方針

### build workflow の caller

`.github/workflows/build.yml` に reusable workflow caller の `e2e_test` job を追加する。

- `needs: [build_ubuntu, repair_ubuntu_arm, build_macos, build_windows]`。
- `uses: ./.github/workflows/e2e-test.yml`。
- `with: from_build: true`。
- `secrets: inherit`。

E2E secret / `OPENH264_VERSION` は `e2e-test.yml` 側の既存 env を維持し、build.yml に重複定義しない。

### E2E workflow

全 job の一時停止用 `if: false` を除く。trigger は既存の `workflow_dispatch` / `workflow_call` / develop・feature branch の path 制限付き `push` を維持し、comment out 済み schedule は復活させない。

有効 matrix は Python 3.13 と次の wheel artifact に限定する。

- `ubuntu-24.04_x86_64`。
- `ubuntu-22.04_armv8`。
- `ubuntu-24.04_armv8`。
- canonical `macos-15_arm64` wheel を使う macos-15 runner。
- `windows-2025_x86_64`。
- Intel VPL / NVIDIA Video Codec の self-hosted x86_64 runner は `ubuntu-24.04_x86_64` wheel を共有する。
- Apple Video Toolbox の self-hosted macOS runner は `macos-15_arm64` wheel を共有する。
- Raspberry Pi self-hosted runner は `raspberry-pi-os_armv8` wheel を使う。

build しない `ubuntu-22.04_x86_64` と、0072 の専用実機経路で検証する Jetson は含めない。comment out 中の AMD AMF entry と schedule は変更しない。

### artifact 選択

`from_build=true` は caller run の `<wheel_platform>_python-3.13` artifact を取得する。download 後は nullglob / 配列で wheel が厳密に 1 件であることを確認し、basename の distribution / Python ABI / platform tag が matrix entry と一致することを検査する。`find ... | head -1` は廃止する。

直接実行時は既存 `.github/actions/download-whl` を使う。0066 が release fallback pattern を最終配布 tag へ同期するまで、同一 branch の成功 build artifact を優先する。0 件 / 複数件は failure とし、任意の先頭 file を選ばない。

### release gate 契約

`e2e_test` caller job の result を release gate の単一情報源とする。0066 の `prepare_release` は `needs` に `e2e_test` を含め、failure / cancelled / skipped の全てで publish / release を実行しない。`always()` を使って迂回しない。

### 最終結果と Slack

`ci_result` job を `if: always()` で追加し、`build_ubuntu` / `repair_ubuntu_arm` / `build_macos` / `build_windows` / `build_sdist` / `e2e_test` の result を評価して `success` / `failure` / `cancelled` を output する。

`slack_notify` は `needs: [ci_result]` と `if: always()` を持ち、`ci_result.outputs.status` を通知 action の `status` に渡す。0066 は tag release job を追加した時点で同じ集約対象を拡張する。

## 完了条件

- build workflow の全 build job 成功後に `e2e_test` が実行される。
- 有効 matrix が実在する Python 3.13 artifact だけを参照し、Ubuntu 22.04 x86_64 / Jetson を含まない。Jetson は 0072 の専用 release gate だけで扱う。
- macos-15 runner / Apple Video Toolbox が canonical な `macos-15_arm64` wheel を使う。
- GitHub-hosted / self-hosted の全有効 E2E entry が green になる。
- wheel が 0 件 / 複数件 / basename 不一致の場合に test 前に失敗する。
- schedule と AMD AMF entry が無効のままである。
- build または E2E の failure / cancelled が `ci_result` と Slack status に反映される。
- `repair_ubuntu_arm` の failure / cancelled / skipped で E2E / publish へ進まず、`ci_result` と Slack status に反映される。
- 0066 が `needs: [e2e_test]` を直接または `prepare_release` 経由で参照できる安定した job 契約になっている。

## 解決方法

1. build.yml に reusable `e2e_test` caller と `ci_result` を追加する。
2. e2e-test.yml の一時停止を解除し、matrix / artifact 検査を新 build 契約へ同期する。
3. Slack 通知を `ci_result` の最終 status へ接続する。
4. workflow_call、workflow_dispatch、path 制限付き push の各起動経路を確認する。
5. `CHANGES.md` の `## develop` に次を追加する。

```
- [FIX] wheel の E2E テストを release gate として復活する
  - @voluntas
```

## ロールバック

本 issue を revert する場合は E2E failure を無視して publish せず、0066 の publish / release job も停止する。旧「publish だけ継続」の状態へは戻さない。forward fix で E2E を復旧してから release を再開する。

## 解決方法

実装せず closed にする。

前提の 0001 (scikit-build-core 移行) が「実装せず closed」になり、E2E workflow の一時停止 (`if: false`) も実際には行われなかった。本 issue の設計は scikit-build-core の artifact 契約を前提としており、現状の setuptools ベースのビルドシステムと整合しないため破棄する。

E2E を release gate として整備する必要が生じた場合は、現状のビルドシステムを前提とした新しい issue を起票すること。
