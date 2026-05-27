# SoraVideoDecoderFactory の formats_ 並行アクセスによる abort を修正する

- Priority: High
- Created: 2026-05-27
- Model: Opus 4.7
- Branch: feature/fix-video-decoder-factory-data-race-abort

## 目的

受信トラックのデコーダ生成と再ネゴシエーションが並行で走る状況で、native 拡張 (`sora_sdk_ext`) が `Fatal Python error: Aborted` (SIGABRT / exit code 134) でプロセスごと落ちる事象を解消する。

native レイヤの abort は Python 例外として捕捉できず、プロセス全体を巻き込んで停止させる。マルチコーデックかつ参加者が出入りする通常利用 (多人数セッション) で踏みうるため、SDK の安定性に対する影響が大きい。

## 優先度根拠

High とする。

- プロセスごと落ちる (SIGABRT) ため、利用側のアプリケーションを巻き込んで停止する。Python 側での回避手段がない。
- 「受信中は再ネゴシエーションしない」以外に避ける道がなく、それは多人数セッションでは非現実的な制約。通常利用の範囲内で発生する。
- 後述の再現手順で意図的に高確率 (240 秒あたり約 75%) で再現できることを確認済み。単発の偶発事象ではない。

## 現状

### 失敗内容

`video_codec_type` の指定有無や特定コーデックに依存せず、デコーダ生成経路で abort する。crashing thread の native スタックの中核フレームは以下で共通している。

```
abort+0xdf  (libc)
sora_sdk_ext.cpython-3xx-x86_64-linux-gnu.so, +...
sora::SoraVideoDecoderFactory::Create(const webrtc::Environment&, const webrtc::SdpVideoFormat&)+0x41c
sora_sdk_ext...
...
```

複数の独立した観測 (異なるコーデック・異なる接続タイミング) で `Create(...)+0x41c` まで一致しており、同一バグであることを確認している。

### 環境情報

- sora-python-sdk: 2026.1.0.dev5 / 2026.1.0.dev7 のいずれでも再現 (dev7 でも未修正)
- 依存 native: sora-cpp-sdk `2026.2.0-canary.11` (`DEPS` の `SORA_CPP_SDK_VERSION`)
- Python: cpython 3.14.5
- 実行環境: Linux x86_64 / 2 コア程度の低並列環境で特に再現しやすい

### 根本原因

依存している sora-cpp-sdk の `SoraVideoDecoderFactory` における `formats_` キャッシュの未同期な並行アクセス。`2026.2.0-canary.11` のソース (`src/sora_video_decoder_factory.cpp` / `include/sora/sora_video_decoder_factory.h`) で裏取り済み。

- `formats_` は `mutable std::vector<std::vector<webrtc::SdpVideoFormat>> formats_;` で、保護する mutex を持たない。
- `GetSupportedFormats() const` は呼ばれるたびに `formats_.clear()` してから decoder ごとに `formats_.push_back(...)` で作り直す。クリア中〜再構築途中は `formats_` のサイズが 0〜decoder 数未満の不整合状態になる。
- `Create()` は `formats_[n++]` で添字アクセスし、`formats_.size() == config_.decoders.size()` を暗黙の前提にしている。
- この 2 メソッドは libwebrtc が内部スレッドから呼ぶ。`GetSupportedFormats` は (再)ネゴシエーション時 (signaling thread)、`Create` は受信トラックのデコーダ生成時 (worker/decoder thread)。両者が同一 factory の `formats_` を未同期で並行アクセスし、`Create` が clear / 再構築途中の `formats_[n]` を読むと範囲外・破損アクセス (UB) となり abort (`Create+0x41c`) に至る。

### 利用側で回避できるか

回避できない。`GetSupportedFormats` / `Create` は `webrtc::VideoDecoderFactory` の仮想関数で、SDK 利用者が直接呼ぶものではなく libwebrtc が内部スレッドから任意のタイミングで呼ぶコールバックである。利用者は factory を生成して PeerConnectionFactory に渡すだけで、両呼び出しの並行性を制御する API はない。

## 設計方針

根本原因は依存ライブラリ sora-cpp-sdk 側にあるため、本リポジトリ単独では完結しない。次の順で対応する。

### A. sora-cpp-sdk 側を修正する (本命)

`formats_` はメモ化ではなく (毎回 clear + 再構築するため)、唯一の用途は `GetSupportedFormats` から `Create` へ「decoder ごとの対応フォーマット」を受け渡すことのみ。

- 案 1 (推奨): `Create()` 内で decoder ごとの対応フォーマットをその場で再計算し (`GetSupportedFormats` と同じ分岐)、`formats_` メンバを削除する。共有可変状態が消え競合が根絶される。
- 案 2: `formats_` を mutex で保護する (両メソッドでロック)。共有状態は残る。

sora-cpp-sdk に上記を反映したリリースが出たら、本リポジトリの `DEPS` の `SORA_CPP_SDK_VERSION` を修正版に更新し、再現テストで abort しないことを確認する。

### B. SDK 単体での再現テストを追加する

Sora サーバや E2E 基盤は必須ではない。本質は「1 つの `SoraVideoDecoderFactory` に対し別スレッドから `GetSupportedFormats()` と `Create()` を並行で叩く」こと。`tests/` 配下にマルチスレッドで decoder factory 生成経路を集中的に叩く再現テストを追加し、修正前は abort・修正後は安定して完了することで回帰を防ぐ。

- 再現条件 (E2E で確立済みのレシピ): 単一チャネルに常設の受信接続を複数張り、専用スレッドで受信し続けてデコーダを常時稼働させる。並行して別スレッド群が同一チャネルへ異なる codec で高速に join/leave を繰り返す。各 join で常設接続側に「新規デコーダ生成 (Create)」と「re-offer 処理 (GetSupportedFormats)」が別スレッドで同時に走り、`formats_` の data race を踏む。
- 鍵は「常設受信接続を常時デコードさせたまま、別 codec の参加者を高速に出入りさせて re-offer を集中投下する」点。単一 factory あたりの重なり密度を上げると再現率が大きく上がる。

## 完了条件

- 依存する sora-cpp-sdk 側で `SoraVideoDecoderFactory::Create` の abort が修正され、修正版を `DEPS` に取り込んでいること
- マルチスレッドでデコーダ生成経路を集中的に叩いても abort せずに完了すること (再現テストで確認)
- `CHANGES.md` に `[FIX]` として記載していること

## 解決方法

未着手。
