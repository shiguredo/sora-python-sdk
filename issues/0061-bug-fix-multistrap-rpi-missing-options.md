# multistrap の raspberry-pi-os_armv8.conf に欠落している noauth / ignorenativearch オプションを追加する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-multistrap-rpi-missing-options

## 目的

`multistrap/raspberry-pi-os_armv8.conf` には `noauth=true` と `ignorenativearch=true` の両方が欠落している。
他の armv8 用 conf (`multistrap/ubuntu-22.04_armv8.conf`, `multistrap/ubuntu-24.04_armv8.conf`) には両方とも記述されており、Raspberry Pi 用だけ揃っていない状態である。
x86_64 ホストから arm64 rootfs を multistrap で構築する際、

- `noauth=true` が無いと apt のリポジトリ署名検証で失敗しうる
- `ignorenativearch=true` が無いと multistrap がネイティブアーキテクチャ (x86_64) で動作していることに対する不整合チェックでエラーになりうる

つまり Raspberry Pi 向けの multistrap 経路に潜在的な失敗経路を抱えているため、これを解消する。

## 優先度根拠

Medium とする。

- 現状、CI では multistrap 経路が動作しているように見えるが、これは「他の構成 (`Deb` セクション・`Rasp` セクション) や apt-get の上書き (`/usr/sbin/multistrap` への `sed` パッチ) によって偶然救われている」可能性が高く、構造的には不安定である。
- 他の armv8 conf と揃っていないこと自体が「壊れた窓」であり、放置すると将来の Debian / Raspberry Pi OS のリポジトリ署名仕様変更や、`/usr/sbin/multistrap` の挙動変更で突然 CI が壊れる潜在原因になる。
- 一方で「現に壊れているわけではない」「PR #302 で sysroot.py 経路への移行が進行中で multistrap 自体が消える可能性がある」ことから High ではなく Medium とする。

## 現状

`multistrap/ubuntu-22.04_armv8.conf` の `[General]` セクションは次の通り。

```ini
[General]
noauth=true
unpack=true
bootstrap=Ports
aptsources=Ports
ignorenativearch=true
```

`multistrap/ubuntu-24.04_armv8.conf` も同様に `noauth=true` / `ignorenativearch=true` を持つ。

これに対し `multistrap/raspberry-pi-os_armv8.conf` の `[General]` セクションは次の通り。

```ini
[General]
unpack=true
bootstrap=Deb Rasp
aptsources=Deb Rasp
```

`noauth=true` と `ignorenativearch=true` の両方が抜けている。
このコンフィグは Debian の本家リポジトリと Raspberry Pi 公式リポジトリの両方を扱うため、本来はむしろ Ubuntu Ports 版より厳しい状況にある。

`.github/workflows/build.yml` の Linux ビルドジョブでは、multistrap 実行前に `/usr/sbin/multistrap` を `sed` で書き換えて `Acquire::AllowInsecureRepositories=true` を強制注入することで動作させている。
これは conf 側の不備を CI スクリプト側で覆い隠している状態で、構造的に望ましくない。

## 設計方針

`multistrap/raspberry-pi-os_armv8.conf` の `[General]` セクションを他の armv8 conf と揃える。

```ini
[General]
noauth=true
unpack=true
bootstrap=Deb Rasp
aptsources=Deb Rasp
ignorenativearch=true
```

合わせて以下も確認する。

- PR #302 で進行中の sysroot.py 経路への移行が完了すると multistrap 自体が不要になる見込みがある。本 issue の対応はその移行完了までの暫定的な健全化として扱い、移行完了時には conf ごと削除する方針を CHANGES.md / commit メッセージで明示する。
- `.github/workflows/build.yml` 内の `Acquire::AllowInsecureRepositories=true` 強制注入は、conf 側に `noauth=true` が入った後も必要かを別途確認し、不要であれば取り除く (本 issue のスコープは conf 修正までだが、確認ログは PR 本文に残す)。

## 完了条件

- `multistrap/raspberry-pi-os_armv8.conf` の `[General]` セクションに `noauth=true` と `ignorenativearch=true` が両方含まれる。
- CI の `build_ubuntu` (raspberry-pi-os_armv8 ターゲット) が引き続き green のまま通る。
- PR 本文に「PR #302 完了後は multistrap 経路ごと不要になる予定」である旨を明記する。
