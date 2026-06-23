# publish_wheel ジョブの matrix に Ubuntu 24.04 系を追加するか「22.04 のみ配布」を明示する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/publish-wheel-ubuntu-24-04

## 目的

`.github/workflows/build.yml` の `build_ubuntu` ジョブは Ubuntu 22.04 と 24.04 の両方の wheel (x86_64 / armv8) を生成して artifact にアップロードする。
一方、PyPI に配布する `publish_wheel` ジョブの matrix には Ubuntu 22.04 系 (`ubuntu-22.04_x86_64` / `ubuntu-22.04_armv8`) しか含まれておらず、Ubuntu 24.04 系の wheel が PyPI には上がらない。

`create-release` ジョブは 22.04 / 24.04 両方を `download` して GitHub Release の assets に並べるので、GitHub Release では両方手に入るが、PyPI 経由 (`pip install sora-sdk` / `uv add sora-sdk`) では 24.04 wheel が手に入らない。

設計意図が明確でない。考えうるパターンは 2 つ。

1. **意図的**: `manylinux_2_31` (= 22.04 ベース) の wheel は `manylinux_2_35` (= 24.04 ベース) のホストでも動くため、22.04 系の wheel だけを PyPI に出せば必要十分という判断。
2. **抜け漏れ**: matrix に追加し忘れている。

どちらにせよ「明示する」必要があり、本 issue ではどちらかを選んで対応する。

## 優先度根拠

Medium とする。

- 現在の配布動作 (PyPI には 22.04 wheel しか上がらない) はユーザーから見ると `pip install` で 22.04 用 wheel が落ちてくることになり、24.04 ホストでも `manylinux_2_31` タグの規約により実行できる。よって即時の機能不良ではない。
- ただし「ビルドはしている wheel が PyPI には上がらない」状態は CI 時間と GitHub Actions storage を浪費し、また「PyPI 側に 24.04 系が無いことを意図的に選んでいるのか」が後から判別できない。リリース運用の透明性として Medium で扱う。
- 即時のユーザー影響が無いので High ではない。

## 現状

`.github/workflows/build.yml:344-365` の `publish_wheel` ジョブ matrix:

```yaml
publish_wheel:
  if: contains(github.ref, 'tags/202')
  # needs:
  #   - e2e_test
  needs:
    - build_ubuntu
    - build_macos
    - build_windows
  strategy:
    fail-fast: false
    matrix:
      platform:
        - name: ubuntu-22.04_x86_64
        - name: ubuntu-22.04_armv8
        - name: macos-15_arm64
        - name: macos-14_arm64
        - name: windows-2025_x86_64
        - name: raspberry-pi-os_armv8
      python_version:
        - "3.12"
        - "3.13"
        - "3.14"
```

一方 `create-release` ジョブ (406-465 行) では:

```yaml
- uses: ./.github/actions/download
  with: { "platform": "ubuntu-24.04_x86_64", "python_version": "3.12" }
- uses: ./.github/actions/download
  with: { "platform": "ubuntu-24.04_x86_64", "python_version": "3.13" }
... (24.04 系を Python 3.12 / 3.13 / 3.14 x x86_64 / armv8 で全部 download)
```

として 24.04 系を GitHub Release に含めている。

## 設計方針

以下 (a) (b) のどちらかを選ぶ。実装時に判断する。

(a) `publish_wheel` matrix に Ubuntu 24.04 系を追加する。

```yaml
- name: ubuntu-22.04_x86_64
- name: ubuntu-22.04_armv8
- name: ubuntu-24.04_x86_64
- name: ubuntu-24.04_armv8
- name: macos-15_arm64
...
```

PyPI に Ubuntu 24.04 系の wheel が並ぶようになり、`manylinux_2_35` タグの環境で本来意図された wheel が選ばれる。

(b) 「意図的に 22.04 系のみ配布する」と明文化する。

- `README.md` / `CHANGES.md` / `docs/` に「PyPI 経由では `manylinux_2_31` (22.04 ベース) wheel のみ配布する。24.04 系の wheel が必要な場合は GitHub Release から手動取得すること」と明記する。
- 加えて `build_ubuntu` から 24.04 系のビルドステップを削るか、`create-release` の download から 24.04 系を削って整合させる。

issue 0006 (CI 整理) と関連が深いため、対応は 0006 とまとめて行うのが望ましい。本 issue ではどちらの方針を採るかの設計判断と、その後のワークフロー編集を扱う。

## 完了条件

- `publish_wheel` の matrix と `create-release` の download / `build_ubuntu` の matrix の関係が論理的に一貫している。
- (a) を選ぶ場合は PyPI に Ubuntu 24.04 系 wheel が並ぶことを次回リリースで確認する。
- (b) を選ぶ場合は README / CHANGES.md / docs のいずれかに「PyPI 経由では 22.04 系のみ配布」が明記される。
