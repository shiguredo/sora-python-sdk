# SoraConnection::OnSetOffer で AddTrack 失敗時にエラーログを出力する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-on-set-offer-add-track-no-log

## 目的

`src/sora_connection.cpp` の `OnSetOffer` は、PeerConnection の `AddTrack` 失敗時に `audio_result.ok()` / `video_result.ok()` の `else` 節を持たず、エラーを完全に握りつぶしている。`AddTrack` は SDP の不整合・トランシーバ枯渇・既に同方向の sender が存在するなどの理由で失敗しうる API だが、現状ではユーザに何も通知されず、結果として「映像/音声が一切流れない」だけの不可解な障害になる。本 issue では `AddTrack` の失敗を libwebrtc のログ規約に合わせて `RTC_LOG(LS_ERROR)` で記録し、最低限の運用切り分け情報を残す。

## 優先度根拠

Medium とする。

- 失敗の検知漏れにより「メディアが流れない」という症状だけが出る状態で、サポート問い合わせと再現確認の負荷が高い。
- 修正は `else` 節を 2 つ追加し `RTC_LOG(LS_ERROR)` を呼ぶだけで、リスクは極めて小さい。
- バグというより観測性 (observability) の欠落だが、流れない原因をユーザが特定できない以上、放置は不適切なため High ではなく Medium 相当として潰す。

## 現状

`src/sora_connection.cpp` の `OnSetOffer` は以下の通り。

```cpp
void SoraConnection::OnSetOffer(std::string offer) {
  gil_scoped_acquire acq;
  std::string stream_id = webrtc::CreateRandomString(16);
  if (audio_source_) {
    webrtc::RTCErrorOr<webrtc::scoped_refptr<webrtc::RtpSenderInterface>>
        audio_result = conn_->GetPeerConnection()->AddTrack(
            audio_source_->GetTrack(), {stream_id});
    if (audio_result.ok()) {
      // javascript でいう replaceTrack を実装するために webrtc::RtpSenderInterface の参照をとっておく
      audio_sender_ = audio_result.value();
      if (audio_sender_frame_transformer_) {
        audio_sender_->SetFrameTransformer(audio_sender_frame_transformer_);
      }
    }
  }
  if (video_source_) {
    webrtc::RTCErrorOr<webrtc::scoped_refptr<webrtc::RtpSenderInterface>>
        video_result = conn_->GetPeerConnection()->AddTrack(
            video_source_->GetTrack(), {stream_id});
    if (video_result.ok()) {
      video_sender_ = video_result.value();
      if (video_sender_frame_transformer_) {
        video_sender_->SetFrameTransformer(video_sender_frame_transformer_);
      }
    }
  }
  ...
}
```

- `audio_result.ok()` / `video_result.ok()` の `if` だけが書かれており、失敗時の `else` 節がない。
- `webrtc::RTCErrorOr<T>` は失敗時に `error()` から `webrtc::RTCError` を取り出せ、`message()` / `type()` から失敗理由を取得できるが、現状はこの情報を取り出すコードがどこにもない。
- 同種のロガー呼び出しは libwebrtc 側で `RTC_LOG(LS_ERROR)` の慣用句があり、本リポジトリでも他の経路 (本ファイル内・他ファイル) で利用されている。`OnSetOffer` だけ抜け落ちている形。

## 設計方針

- `audio_result.ok()` / `video_result.ok()` それぞれに `else` 節を追加し、`RTC_LOG(LS_ERROR) << "Failed to add audio track: " << audio_result.error().message();` のように失敗内容を英語メッセージで出力する。
- ログメッセージは libwebrtc のスタイル (`<モジュール名>: <現象>: <理由>` 程度) に揃える。AGENTS.md の規約に従い英語で書く。
- 失敗時に例外を投げるか単にログだけにするかは、本リポジトリの既存方針 (どこまでユーザにエラーを伝えるか) に合わせる。`OnSetOffer` は libwebrtc 内部スレッドからのコールバック経路にあるため、例外を投げると上位で扱えず落ちる可能性がある。最初のステップではログのみとし、必要なら `on_disconnect_` などへの通知も検討する。
- video / audio で同じパターンになるため、必要なら共通のローカルヘルパに切り出してもよいが、まずは素直に 2 箇所追記する方針で十分。

## 完了条件

- `AddTrack` 失敗時に `RTC_LOG(LS_ERROR)` で失敗内容 (track 種別・`webrtc::RTCError::message()` の中身) がログに残ること。
- 正常系の挙動が一切変わらないこと。
- 既存の e2e テスト・ユニットテストが引き続き通ること。
- 可能であれば `AddTrack` を意図的に失敗させて手元再現し、ログが期待通りに出ることを確認する (再現が難しければ運用上の確認で代替してよい)。
