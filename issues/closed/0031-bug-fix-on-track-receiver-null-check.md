# SoraConnection::OnTrack で transceiver->receiver() の null チェックを追加し SEGV を防ぐ

- Priority: Medium
- Created: 2026-06-23
- Completed: 2026-07-16
- Model: Opus 4.7
- Branch: feature/fix-on-track-receiver-null-check

## 目的

`src/sora_connection.cpp` の `OnTrack` コールバックでは、`transceiver->receiver()` の戻り値をそのまま `SoraMediaTrack` のコンストラクタへ渡している。`SoraMediaTrack` のコンストラクタは内部で `receiver->track()` を呼ぶ実装になっており、`transceiver->receiver()` が `nullptr` を返した場合に SEGV を引き起こす経路が存在する。`OnTrack` は libwebrtc 側のシグナリングや transceiver 構成によっては receiver が未確定のまま発火する場合があり、防御コードが必要である。本 issue では `receiver` の null チェックを入れ、不正な状態でも安全にフォールバックできるようにする。

## 優先度根拠

Medium とする。

- nullptr 経路に入った場合のクラッシュは確実に SEGV へ繋がり、Python プロセスごと落ちるためユーザ影響は大きい。
- 一方で `transceiver->receiver()` が `nullptr` を返すケースは libwebrtc の通常運用ではまれであり、再現頻度は低い。
- 防御 1 行で深刻度の高い障害を回避できるため、放置せず Medium として優先的に潰す。

## 現状

`src/sora_connection.cpp` の `OnTrack` は以下の通り。

```cpp
void SoraConnection::OnTrack(
    webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) {
  gil_scoped_acquire acq;
  if (on_track_) {
    auto receiver = transceiver->receiver();
    nb::ref<SoraMediaTrack> track = new SoraMediaTrack(this, receiver);
    call_python(on_track_, track);
  }
}
```

- `transceiver->receiver()` は `webrtc::scoped_refptr<webrtc::RtpReceiverInterface>` を返すが、libwebrtc の API 仕様上、特定のタイミングや transceiver 構成 (送信専用 transceiver など) で `nullptr` を返す可能性がある。
- `SoraMediaTrack` のコンストラクタは内部で `receiver_->track()` を呼ぶ。`receiver_` が `nullptr` の場合は null ポインタ参照で SEGV になる。
- `if (on_track_)` の防御はあるが、`receiver` 側の null チェックはない。`transceiver` 自体の null チェックも不在。
- 同種の防御コードが `OnRemoveTrack` 等の周辺コールバックでも漏れている可能性があるため、本 issue の修正と合わせて点検する。

## 設計方針

- `auto receiver = transceiver->receiver();` の直後に `if (receiver == nullptr) { ... return; }` のガードを置く。null の場合は libwebrtc 側のログ規約に合わせ `RTC_LOG(LS_WARNING) << "OnTrack received transceiver with null receiver";` を出力した上で `return` する。
- 安全側に倒すなら `transceiver` 自体の null チェックも併せて行う。libwebrtc のシグネチャ上はあり得ない想定だが、防御として無害である。
- `OnRemoveTrack` 等の関連コールバックも点検し、同様の null 経路があれば併せて修正する。

## 完了条件

- `transceiver->receiver()` が `nullptr` を返すケースで SEGV せず、ログを出して安全に何もしないこと。
- 正常系 (`receiver` が非 null) の挙動が従来と変わらないこと。
- 既存の e2e テスト・ユニットテストが引き続き通ること。
- 可能であれば null receiver を模した低レベルテストで防御が効くことを確認する (難しい場合はコメントで再現条件を残す)。

## 解決方法

`src/sora_connection.cpp` の `SoraConnection::OnTrack` で、`SoraMediaTrack` 構築前に `transceiver` と `receiver` の null チェックを追加した。null の場合は `RTC_LOG(LS_WARNING)` で英語の警告を出し、Python コールバックを呼ばずに return する。

```cpp
void SoraConnection::OnTrack(
    webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) {
  gil_scoped_acquire acq;
  if (on_track_) {
    if (transceiver == nullptr) {
      RTC_LOG(LS_WARNING) << "OnTrack received null transceiver";
      return;
    }
    auto receiver = transceiver->receiver();
    if (receiver == nullptr) {
      RTC_LOG(LS_WARNING)
          << "OnTrack received transceiver with null receiver";
      return;
    }
    nb::ref<SoraMediaTrack> track = new SoraMediaTrack(this, receiver);
    call_python(on_track_, track);
  }
}
```

`OnRemoveTrack` は `receiver` を参照しない空実装 (`TODO(tnoho): 要実装`) のままであるため、同種の null 経路は無く追加修正は不要だった。

null receiver を模した低レベルテストは、モック・スタブ禁止かつ Python から `OnTrack` を注入できないため追加しなかった。代わりにコードコメントへ再現条件（送信専用 transceiver / receiver 未確定タイミング）とテスト省略理由を残した。`macos_arm64` 向けビルドと `tests/test_version.py` は通過した。既存 e2e は CI で確認する。

あわせて `CHANGES.md` の `## develop` に `[FIX]` エントリを追記した。
