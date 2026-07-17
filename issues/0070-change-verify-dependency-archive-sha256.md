# 依存 archive の SHA-256 検証を必須化する

- Priority: High
- Created: 2026-07-17
- Updated: 2026-07-17
- Completed: -
- Model: GPT-5
- Branch: feature/change-verify-dependency-archive-sha256
- Polished: 2026-07-17

## 目的

`fetch_deps.cmake` が取得する WebRTC / Sora C++ SDK / Boost archive を、`DEPS` に固定した SHA-256 と照合してから展開する。download 元の改ざん、壊れた転送、release asset の意図しない差し替えを configure 時に検出し、既存の正常な dependency 一式を壊さず失敗させる。

## 優先度根拠

- 取得した native library は wheel へ直接 link・同梱されるため、検証しない archive は供給 chain 上の重大な未検証入力になる。
- 0001 は SHA-256 引数の受け口だけを用意し、値と検証を後続 issue へ委譲している。通常リリース再開前に必須化する必要があるため High とする。

## 前提

- 0001 〜 0005 の完了後に実装し、追加済みの全 archive platform を同じ PR で対象にする。
- sysroot の repository signature / keyring / manifest fingerprint は 0003 / 0004 が扱う。本 issue は WebRTC / Sora / Boost の release archive だけを扱う。
- OpenH264 は Git ref から取得するため本 issue の archive SHA-256 対象に含めない。

## 現状

0001 の `_sora_fetch_archive` は `SHA256` keyword を parse するが値を受け取らず、download 後の digest を検証しない。stamp は URL だけで再利用を判定するため、次の状態を検出できない。

- 同じ URL の asset 内容が変わった。
- local archive が破損・改変された。
- dependency version は同じまま期待 digest だけを更新した。

また、archive、展開先、stamp は別 path にあるため、更新途中の process kill / CI cancellation に対する復旧契約が無い。

## 設計方針

### DEPS の key

`DEPS` の `KEY=value` と shell の `source DEPS` 互換を維持し、次の形式で SHA-256 を追加する。

```
<DEPENDENCY>_SHA256_<NORMALIZED_PLATFORM>=<64 桁の小文字 hex>
```

- `<DEPENDENCY>` は `WEBRTC` / `SORA` / `BOOST` の 3 種。
- `<NORMALIZED_PLATFORM>` は archive platform 名を大文字化し、英数字以外を `_` に置換した値。
- 0001 〜 0005 完了時点の対象 platform は `UBUNTU_24_04_X86_64` / `MACOS_ARM64` / `UBUNTU_22_04_ARMV8` / `UBUNTU_24_04_ARMV8` / `RASPBERRY_PI_OS_ARMV8` / `WINDOWS_X86_64` の 6 種。
- macos-15 / macos-26 は同じ `macos_arm64` archive を使うため key を共有する。

必須集合は platform と dependency の無条件な直積ではなく、`fetch_deps.cmake` が解決可能な `(dependency, archive platform)` pair の allowlist とする。0001 〜 0005 完了時点は 6 platform × 3 dependency の 18 pair である。0043 は WebRTC に既存 `UBUNTU_22_04_ARMV8` を再利用し、Sora / Boost だけ `UBUNTU_22_04_ARMV8_JETSON` を追加するため、0043 完了後は既存 18 key + Jetson 2 key の合計 20 key とする。存在しない `WEBRTC_SHA256_UBUNTU_22_04_ARMV8_JETSON` は追加しない。

欠落、重複、空値、64 桁小文字 hex 以外、`*_SHA256_*` namespace の未知 pair を configure error にする。target から dependency ごとに解決した archive platform と SHA allowlist は同じ mapping table を単一の情報源として使い、片方だけを更新できない構造にする。値は `fetch_deps.cmake` が組み立てる HTTPS URL の release asset を取得して算出し、依存 version の更新と同じ PR で更新する。

### download と再利用

`_sora_fetch_archive` の `SHA256` を必須引数にする。通常の release archive 取得で検証を省略する option は設けない。

再利用は次の 3 条件が全て一致する場合だけ許可する。

- stamp の URL。
- stamp の SHA-256。
- final archive を再計算した SHA-256。

いずれかが不一致なら再取得する。final archive が不一致でも先に削除せず、同じ filesystem の一時 path へ download する。`file(DOWNLOAD ... EXPECTED_HASH SHA256=<value>)` と明示的な `file(SHA256 ...)` の両方で一時 file を検証してから、一時 directory へ展開し、0001 の期待 layout を検査する。

### transaction と中断復旧

archive、展開先、stamp の 3 path を更新する前に transaction marker を一時 file から atomic rename で作る。marker は dependency 名、URL、SHA-256、変更前の各 path の存在有無、temporary / backup / final path を記録する。

配置順は次に固定する。

1. 検証済み一時 archive と完成済み一時展開先を用意する。
2. marker を配置する。
3. 既存 archive / 展開先 / stamp を同じ親 directory の backup 名へ rename する。
4. 一時 archive / 一時展開先を final 名へ rename する。
5. URL と SHA-256 を持つ新 stamp を最後に配置する。
6. 全配置成功後だけ backup と marker を削除する。

通常の error はその場で rollback する。process kill / CI cancellation の場合は次回の `_sora_fetch_archive` 冒頭で marker を検出し、変更前の存在有無に従って partial final を除去して backup を戻してから再取得する。変更前に無かった path は除去する。marker が無い孤立 backup は由来を判断できないため自動削除せず FATAL_ERROR にする。

### テスト

network、mock、stub を使わず、test 用の実 archive file と CMake script で次を検証する。

- 正しい SHA-256 の取得・展開・stamp 保存・再利用。
- SHA-256 の欠落、形式不正、不一致。
- final archive 改変後の再取得。
- URL または SHA-256 変更時の再取得。
- download / hash / 展開失敗時に既存 3 path が変わらないこと。
- 各 rename 直前で test 専用 failpoint を発生させ、同一実行の rollback と次回実行の marker recovery の両方で変更前の 3 path が復元されること。
- Windows `.zip` とそれ以外の `.tar.gz` の両形式。

test 専用 failpoint は test 実行時にだけ明示的に有効化でき、通常 configure から指定された場合は拒否する。

## 完了条件

- `DEPS` に実装時点の許可済み `(dependency, archive platform)` pair の SHA-256 が過不足なく存在する。0001 〜 0005 完了時点は 18 key、0043 完了後は 20 key である。
- 全 release archive 取得が期待 SHA-256 を必須とし、未指定で configure できない。
- 同じ入力の 2 回目 build は archive を download / 展開せず再利用する。
- archive 改変、期待値変更、URL 変更を検出して再取得する。
- 不一致や各処理段階の失敗で既存の正常な archive / 展開先 / stamp を壊さない。
- process kill 相当の全中断位置から次回実行で変更前の一式へ復旧できる。
- ubuntu-24.04 x86_64、macOS arm64、Ubuntu arm64 2 種、Raspberry Pi OS arm64、Windows x86_64 の通常 wheel build が SHA-256 検証付きで green になる。

## 解決方法

1. `DEPS` parser に SHA-256 key の正規化・必須集合・形式検証を追加する。
2. `_sora_fetch_archive` に一時 download、digest 検証、transaction marker、rollback / recovery を実装する。
3. 18 archive の SHA-256 を公式 release asset から算出して `DEPS` へ記録する。
4. CMake script test と全 platform の通常 wheel build を実行する。
5. `CHANGES.md` の `## develop` に次を追加する。

```
- [ADD] 依存アーカイブの SHA-256 検証を導入する
  - @voluntas
```

## ロールバック

問題が digest 値 1 件の誤りなら正しい値へ forward fix する。transaction / recovery の根本設計を revert する場合は、SHA-256 検証無しの新しい release を行わず publish を停止する。0043 が実装済みなら Jetson release を停止し、0072、0045、0043 の逆順で revert または workflow を無効化してから、本 issue の squash commit を `git revert <squash-commit>` する。通常 platform も修正版が入るまで publish を再開しない。
