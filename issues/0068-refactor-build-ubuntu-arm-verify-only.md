# `build_ubuntu_arm` を廃止して x86_64 host の cross build に一本化する

- Priority: Medium
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: -
- Model: Opus 4.7
- Branch: feature/refactor-build-ubuntu-arm-verify-only
- Polished: 2026-07-30

## 目的

`build.yml` の `build_ubuntu_arm` job を削除し、Linux arm64 wheel の生成を ubuntu-24.04 x86_64 host からの cross build (0003 / 0004 が導入) に一本化する。arm64 native runner で wheel を compile / link する経路を廃止する。

旧案にあった「検証 job として残す」案と「native arm wheel の配布元へ切り替える」案は採用しない。

## 優先度根拠

- 0003 / 0004 の cross build が完了し、arm64 native build は冗長になっている。
- native runner の維持コスト (GitHub-hosted arm64 runner の時間) を削減できる。
- 0052 の matching AArch64 runner は cross build 済み wheel の auditwheel repair だけを行う例外として残る。

## 前提

- 0003 / 0004 の cross build が完了し、ubuntu-22.04 / 24.04 arm64 wheel が x86_64 host から生成されていること。
- 0052 の `repair_ubuntu_arm` job が cross build 済み wheel の repair を行うこと。

## 現状

`build.yml` に `build_ubuntu_arm` job がまだ存在し、ubuntu-22.04-arm / ubuntu-24.04-arm の GitHub-hosted runner で native build を実行している。0003 / 0004 の cross build と冗長になっている。

`slack_notify` job の `needs` にも `build_ubuntu_arm` が含まれている。

## 設計方針

- `build.yml` から `build_ubuntu_arm` job の定義を削除する。
- `slack_notify` job の `needs` から `build_ubuntu_arm` を削除する。
- 0052 の `repair_ubuntu_arm` job は cross build 済み raw wheel の auditwheel repair だけを行うため、`build_ubuntu_arm` の削除影響を受けない。`repair_ubuntu_arm` の `needs` が `build_ubuntu` (cross build job) を参照していることを確認する。
- E2E workflow の arm64 entry は cross build + repair 済み wheel を使うため、`build_ubuntu_arm` の削除影響を受けない。
- 本 issue 独自の CHANGES entry は追加せず、`### misc` 配下に CI 変更として記載する。

## 完了条件

- `build.yml` に `build_ubuntu_arm` job が存在しない。
- `slack_notify` の `needs` に `build_ubuntu_arm` が含まれない。
- ubuntu-22.04 / 24.04 arm64 wheel が x86_64 host の cross build + AArch64 repair だけで生成される。
- 既存の E2E テスト (arm64 entry 含む) が通ること。
- CI 実行時間が短縮されること (arm64 native build job がなくなること)。

## 解決方法

1. `build.yml` から `build_ubuntu_arm` job を削除する。
2. `slack_notify` の `needs` から `build_ubuntu_arm` を削除する。
3. `repair_ubuntu_arm` の `needs` が cross build job を正しく参照していることを確認する。
4. CI を実行し、arm64 wheel が cross build + repair で正しく生成されることを確認する。
5. `CHANGES.md` の `## develop` → `### misc` に次を追加する。

```
- [UPDATE] Linux arm64 wheel の生成を x86_64 host の cross build に一本化し、arm64 native build job を廃止する
  - @voluntas
```

## ロールバック

0003 / 0004 に問題があっても `build_ubuntu_arm` を復活させない。Linux arm64 release を一時停止し、cross build を forward fix する。
