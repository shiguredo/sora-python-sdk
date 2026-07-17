# `build_ubuntu_arm` を廃止して x86_64 host の cross build に一本化する

- Priority: Medium
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: -
- Model: Opus 4.7
- Branch: feature/refactor-build-ubuntu-arm-verify-only
- Polished: 2026-07-17

## 目的

本 issue を個別実装せず、0001 で artifact を生成しない `build_ubuntu_arm` job を削除する。0003 / 0004 は ubuntu-24.04 x86_64 host から署名検証済み sysroot を使う cross build を追加し、arm64 native build は復活させない。0052 の matching AArch64 runner は cross build 済み wheel の auditwheel repair だけを行う例外とする。

旧案にあった「検証 job として残す」案と「native arm wheel の配布元へ切り替える」案は採用しない。

## 設計方針

- 本 issue の branch は作成しない。
- 0001 の実装 commit 後、別の close commit で本 issue file を `issues/closed/` へ移動する。
- 0003 / 0004 は cross wheel の AArch64 ELF、extension suffix、dependency、host contamination を x86_64 host 上で機械検証する。
- 実行時 import は各 target の E2E issue で検証し、native build の成功を cross artifact の代替検証にしない。
- CI cost 改善は 0071 の dependency cache で扱い、native runner を追加しない。
- 本 issue 独自の CHANGES entry は追加せず、0003 の arm64 cross build entry に native runner 廃止を記載する。

## 完了条件

- 0001 の完了条件が満たされ、`build_ubuntu_arm` とその `slack_notify.needs` entry が存在しない。
- 0003 / 0004 の Linux arm64 wheel 生成が ubuntu-24.04 x86_64 host に統一される。
- arm64 native runner で wheel を compile / link しない。0052 の repair-only job は raw cross wheel の provenance を検証してから最終 artifact を生成する。
- 本 issue 単独の実装 branch / commit がない。
- 0001 の close commit で本 issue が `issues/closed/` へ移動される。

## ロールバック

0001 / 0003 / 0004 に問題があっても `build_ubuntu_arm` を復活させない。Linux arm64 release を一時停止し、cross build を forward fix する。
