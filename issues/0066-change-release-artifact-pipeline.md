# publish / GitHub Release の artifact 集約経路を再構築する

- Priority: High
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: -
- Model: GPT-5
- Branch: feature/change-release-artifact-pipeline
- Polished: 2026-07-17

## 目的

scikit-build-core 移行後の全 wheel と専用 sdist artifact を publish 前に一括検証し、PyPI publish 成功後だけ GitHub Release を作成する経路へ再構築する。Ubuntu の publish 対象、macOS の canonical wheel、Raspberry Pi OS の別 distribution を明示し、build / publish / release の集合を一致させる。

## 優先度根拠

- 0001 は旧 publish / release job を削除するため、本 issue が完了するまで正式 release を作成できない。
- artifact の欠落・重複を publish 後に検出しても PyPI file は上書きできない。外部公開前の完全性検査が必要なので High とする。

## 前提

- 0001 〜 0005、0051、0052、0067 の完了後に実装する。
- 0051 の `source-distribution`、0052 の repaired Ubuntu wheel、0067 の `e2e_test` success を入力契約として使う。
- Jetson は 0043 / 0045 完了後も通常 release へ含めず、0072 の専用 GitHub Release で扱う。

## 配布方針

- Ubuntu 22.04 x86_64 wheel は復活させず、Ubuntu 24.04 x86_64 wheel を配布する。
- Ubuntu arm64 は 22.04 / 24.04 の両 manylinux wheel を配布する。
- Raspberry Pi OS は `sora_sdk_rpi` distribution の `linux_aarch64` wheel を配布する。
- macOS は macOS 14.0 を minimum deployment target とする `macos-15_arm64` artifact だけを配布する。`macos-26_arm64` の同等 wheel は validation-only とする。
- Windows は `windows-2025_x86_64` wheel を配布する。
- Python は全 platform で 3.12 / 3.13 / 3.14 を配布する。

## 設計方針

### artifact 名前空間

通常 wheel artifact の既存契約 `<platform>_python-<version>` は維持する。型情報は `type-stubs_python-*`、sdist は `source-distribution`、debug wheel は `debug-wheel-*`、0052 の repair input は `auditwheel-input-*` であり、release wheel pattern と分離する。

tag build だけで動く `prepare_release` を追加し、`needs` に `build_ubuntu` / `repair_ubuntu_arm` / `build_macos` / `build_windows` / `build_sdist` / `e2e_test` を列挙する。`always()` で failure / cancelled / skipped を迂回しない。

### expected manifest

`prepare_release` は build wheel 21 artifact と sdist 1 artifact を別 directory へ download し、静的な expected manifest と完全一致させる。

release wheel 18 件:

- `ubuntu-24.04_x86_64` × 3 ABI。
- `ubuntu-22.04_armv8` × 3 ABI。
- `ubuntu-24.04_armv8` × 3 ABI。
- `raspberry-pi-os_armv8` × 3 ABI。
- `macos-15_arm64` × 3 ABI。
- `windows-2025_x86_64` × 3 ABI。

validation-only wheel 3 件:

- `macos-26_arm64` × 3 ABI。内容を検査するが release bundle へ入れない。

sdist 1 件:

- `sora_sdk-<VERSION>.tar.gz`。

artifact 完全名を primary key とし、各 artifact directory に file が厳密に 1 件あり、distribution、version、Python / ABI tag、platform tag が expected manifest と一致することを検査する。tag 名と `VERSION` も一致させる。未知 artifact、欠落、想定外拡張子、validation-only wheel の release 混入を拒否する。canonical / validation-only macOS artifact の wheel basename 重複は期待値として許可し、release-selected 18 件の集合内だけ duplicate basename を拒否する。

tag run では `auditwheel-input-ubuntu-22.04_armv8_python-<version>` / `auditwheel-input-ubuntu-24.04_armv8_python-<version>` の 6 internal artifact を別 allowlist で完全名・件数検査する。内部構造へ通常 wheel artifact の 1 file 規則を適用せず、release-selected 21 artifact の件数から除外する。それ以外の `auditwheel-input-*` は unknown として拒否し、内部 artifact の file を release staging / PyPI / GitHub Release へ copy しない。

検証済み 18 wheel の basename / SHA-256 manifest と file を `release-wheels`、sdist 1 件を `release-sdist` artifact として upload する。下流 job は元 matrix artifact を直接参照しない。

### publish

`publish_wheel` / `publish_sdist` は `needs: [prepare_release]` とし、`startsWith(github.ref, 'refs/tags/202')` の tag だけで実行する。

- `environment: pypi`。
- job-level `permissions`: `contents: read` / `id-token: write`。
- `publish_wheel` は `release-wheels`、`publish_sdist` は `release-sdist` だけを取得する。
- upload 前に prepare manifest と file の件数 / basename / SHA-256 を再照合する。
- 部分公開後の rerun を可能にするため `skip-existing: true` を使う。ただし既存 file と期待 hash の不一致を skip せず failure にする。

Raspberry Pi OS wheel は `sora_sdk_rpi` project、その他 wheel / sdist は `sora_sdk` project へ同じ release tag で公開する。

### GitHub Release

`create-release` は `needs: [prepare_release, publish_wheel, publish_sdist]` と `permissions: contents: write` を持つ。両 PyPI job が成功した後だけ `release-wheels` / `release-sdist` の 19 file と manifest を GitHub Release へ upload する。

PyPI publish failure 時に GitHub Release だけを作成しない。GitHub Release upload failure の rerun では PyPI の既存 file を hash 照合後に skip して再試行する。

### direct E2E download

`.github/actions/download-whl/action.yml` の GitHub Release fallback を配布方針と一致させる。

| platform input | release wheel pattern |
| --- | --- |
| `ubuntu-24.04_x86_64` | `manylinux_2_39_x86_64` |
| `ubuntu-22.04_armv8` | `manylinux_2_35_aarch64` |
| `ubuntu-24.04_armv8` | `manylinux_2_39_aarch64` |
| `raspberry-pi-os_armv8` | `sora_sdk_rpi-*-linux_aarch64` |
| `macos-15_arm64` | `macosx_14_0_arm64` |
| `windows-2025_x86_64` | `win_amd64` |

macOS E2E runner は canonical な `macos-15_arm64` input を使用する。download 後に wheel が 0 件または複数件なら失敗し、`find ... | head -1` は使用しない。

### notification

0067 の `ci_result` に `prepare_release` / publish 2 job / `create-release` を追加する。非 tag では release job の skipped を正常として扱い、tag ではいずれかの failure / cancelled を Slack の final status に反映する。

## 完了条件

- `prepare_release` が build wheel 21 件と sdist 1 件を過不足なく検査する。
- release bundle が wheel 18 件 + sdist 1 件で、macos-26 validation-only wheel を含まない。
- Ubuntu 22.04 x86_64 / Jetson / debug / type-stubs artifact が publish / release 対象に入らない。
- `auditwheel-input-*` は期待する内部 6 artifact だけが存在し、release bundle / PyPI / GitHub Release に混入しない。
- PyPI publish は `e2e_test` と全 build / sdist / prepare の成功後だけ実行される。
- GitHub Release は wheel / sdist の PyPI publish 成功後だけ作成される。
- `sora_sdk` と `sora_sdk_rpi` の期待 file が同じ version で公開される。
- direct E2E download が表の 6 pattern で厳密に 1 wheel を選ぶ。
- README の対応 platform から Ubuntu 22.04 x86_64 を削除し、Ubuntu / Raspberry Pi OS の tag と macOS canonical wheel を記載する。
- tag / non-tag の両方で `ci_result` と Slack status が pipeline の最終結果を表す。

## 解決方法

1. `prepare_release` と expected manifest 検査を追加する。
2. trusted publishing の `publish_wheel` / `publish_sdist` を追加する。
3. publish 成功後の `create-release` を追加する。
4. `download-whl`、README、`ci_result` / Slack を新しい artifact 契約へ同期する。
5. `actionlint` と artifact 集約 script の実 file test を実行する。
6. `CHANGES.md` の `## develop` へ CHANGE を先に追加する。

```
- [CHANGE] Ubuntu 22.04 x86_64 wheel の配布を終了する
  - Ubuntu 24.04 x86_64 wheel を配布する
  - @voluntas
```

## ロールバック

外部公開前なら本 issue の squash commit を `git revert <squash-commit>` し、publish / release を停止する。

PyPI へ 1 file でも公開済みなら同じ version を再利用しない。問題の file / version を PyPI で yank し、GitHub Release は削除せず問題と後継 version を注記する。修正版 version を発行する forward fix を必須とする。
