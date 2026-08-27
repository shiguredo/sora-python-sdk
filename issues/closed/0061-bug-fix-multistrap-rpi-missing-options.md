# Raspberry Pi OS の insecure な multistrap 経路を 0004 で廃止する

- Priority: Medium
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: 2026-07-23
- Model: Opus 4.7
- Branch: feature/fix-multistrap-rpi-missing-options
- Polished: 2026-07-17

## 目的

本 issue を個別実装せず、0004 の Raspberry Pi OS Trixie sysroot 移行で `multistrap/raspberry-pi-os_armv8.conf` と insecure な CI patch を経路ごと削除する。

旧案の `noauth=true` 追加は署名検証を無効化する方向であり、問題の修正にならない。`ignorenativearch=true` を追加して legacy 経路を延命する必要もない。0004 の実装 PR で本 issue を同時に close し、独立 branch / commit は作らない。

## 優先度根拠

Medium とする。

- 現行 CI は `/usr/sbin/multistrap` を書き換えて `Acquire::AllowInsecureRepositories=true` を注入し、署名検証を迂回している。
- 一方、本 issue だけを直すと廃止予定の conf を延命し、0004 と競合する変更になる。
- 0004 は High priority で同じ rootfs 経路を HTTPS + `signed_by` の sysroot builder へ置き換えるため、本 issue はその PR で close するのが最短かつ完全な解決になる。

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

`noauth=true` と `ignorenativearch=true` の両方が無い。しかし、`noauth=true` を追加することは APT repository の認証を無効にするため、安全な修正ではない。

`.github/workflows/build.yml` の Linux ビルドジョブでは、multistrap 実行前に `/usr/sbin/multistrap` を `sed` で書き換えて `Acquire::AllowInsecureRepositories=true` を強制注入することで動作させている。
これは conf 側の不足を補うのではなく、repository authentication を CI 全体で無効化する構成である。

## 設計方針

0004 の設計を唯一の解決方針とする。

- `multistrap/raspberry-pi-os_armv8.conf` を削除する。
- `multistrap` package install、`/usr/sbin/multistrap` patch、`--no-auth`、`AllowInsecureRepositories` を CI から削除する。
- Debian / Raspberry Pi repository を HTTPS と `signed_by` で検証し、署名鍵 digest を sysroot manifest fingerprint に含める。
- 0004 の実装を先に commit し、次の commit で本 issue file を `issues/closed/` へ移動する。これにより実装 commit の issue list と close commit を分離する。

本 issue の branch `feature/fix-multistrap-rpi-missing-options` は作成しない。CHANGES entry も本 issue では追加せず、0004 の sysroot 移行 entry に含める。

## 完了条件

- 0004 の完了条件がすべて満たされる。
- repository authentication を無効にする `noauth=true` を追加していない。
- Raspberry Pi OS の legacy multistrap conf と insecure CI patch が残っていない。
- 0004 の実装 PR の close commit で本 issue が `issues/closed/` へ移動される。
- 本 issue 単独の branch、実装 commit、CHANGES entry が作られない。

## 解決方法

実装せず closed にする。

0004 前提の衛星 issue だったが、0004 は 0074 に置き換えた。
insecure な multistrap 経路の削除は 0074 の完了条件に含め、本 issue 単独では扱わない。

## ロールバック

0004 を revert する場合も insecure な multistrap 経路は復活させない。Raspberry Pi OS build を一時停止し、安全な署名検証付き sysroot 経路を forward fix する。
