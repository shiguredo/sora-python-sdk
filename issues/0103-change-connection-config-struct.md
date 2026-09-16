# 接続設定を構造体ベースへ変更し残差 API を実装する

- Created: 2026-09-16
- Completed: -
- Branch: feature/change-connection-config-struct
- Polished: {YYYY-MM-DD}

## 目的

`Sora.create_connection` の 49 引数を構造体ベースへ変更し、引数の機械同期をなくす。あわせて接続設定と残差 API を sora-rust-sdk で再現する。

## 現状

- `Sora.create_connection` は 49 引数を持つ。`src/sora.h` の宣言、`src/sora.cpp` の定義、`src/sora_sdk_ext.cpp` の `.def("create_connection", ...)` の 3 箇所で同じ引数リストを機械同期している。
- 引数の内訳は、接続の識別 (`signaling_urls` / `role` / `channel_id` / `client_id` / `bundle_id`)、メタデータ (`metadata` / `signaling_notify_metadata`)、メディア (`audio_source` / `video_source` / `audio_frame_transformer` / `video_frame_transformer` / `audio` / `video`)、符号化 (`audio_codec_type` / `video_codec_type` / `video_bit_rate` / `audio_bit_rate` / `video_vp9_params` / `video_av1_params` / `video_h264_params` / `video_h265_params` / `audio_opus_params`)、同時配信と注視 (`simulcast` / `spotlight` / `spotlight_number` / `simulcast_rid` / `simulcast_request_rid` / `spotlight_focus_rid` / `spotlight_unfocus_rid`)、転送 (`forwarding_filter` / `forwarding_filters`)、DataChannel (`data_channels` / `data_channel_signaling` / `ignore_disconnect_websocket` / `data_channel_signaling_timeout`)、待ち上限 (`disconnect_wait_timeout` / `websocket_close_timeout` / `websocket_connection_timeout`)、言語 (`audio_streaming_language_code`)、接続仲介と証明書 (`insecure` / `client_cert` / `client_key` / `ca_cert` / `proxy_url` / `proxy_username` / `proxy_password` / `proxy_agent`)、劣化 (`degradation_preference`)、その他 (`user_agent`) である。
- sora-rust-sdk の `SoraConnectionBuilder` は 30 のビルダーメソッドを持つ。識別、メタデータ、可否、同時配信と注視、転送、待ち上限、接続仲介と証明書、`user_agent` は対応する受け口がある。
- 符号化は `Audio` / `Video` の enum (`Bool` / `Opus` / `Vp8` / `Vp9` / `H264` / `H265` / `AV1`) と `AudioOpusParams` / `VideoVP9Params` / `VideoH264Params` / `VideoH265Params` / `VideoAV1Params` が `sora_sdk` にある。
- DataChannel は `ConnectDataChannel`、転送は `ForwardingFilter` / `ForwardingFilterRule` が `sora_sdk` にある。
- `degradation_preference` / `audio_streaming_language_code` / `spotlight_number` / 送信側 `simulcast_rid` に対応する受け口が sora-rust-sdk に無い。`simulcast_request_rid` は受信側として要求する rid であり、送信側の rid 設定ではない。
- `on_disconnect` / `on_set_offer` / `on_rpc` / `on_switched` の引数の受け口が無い。
- `SoraSignalingErrorCode` は 0 から 8 の終了符号である。
- `Sora.VideoCodecCapability` 系 (`SoraVideoCodecCapability` / `SoraVideoCodecPreference` / `get_video_codec_capability` / `create_video_codec_preference_from_implementation`) と `SoraDegradationPreference` も現行の公開面である。

## 設計方針

- `docs/migration-to-sora-rust-sdk.md` の決定事項に従う。後方互換は考慮しない。
- `Sora.create_connection` の 49 引数を `SoraConnectionConfig` 相当のデータクラスへ置き換える。引数の 3 箇所同期をなくす。
- 上流に対応する受け口がある設定は `SoraConnectionBuilder` へ写像する。`Audio` / `Video` / `ConnectDataChannel` / `ForwardingFilter` は上流の型を使う。
- 上流に受け口が無い 4 設定 (`degradation_preference` / `audio_streaming_language_code` / `spotlight_number` / 送信側 `simulcast_rid`) は、上流の依頼 (F) が受理されるまで設定として公開しない。受理されない場合は `SoraConnectionConfig` に含めない。
- `on_disconnect` / `on_set_offer` / `on_rpc` / `on_switched` の引数は上流の依頼 (A / B / C / D) が受理されるまで実装できない。受理されない場合は該当のコールバックを公開 API から削除する。`SoraSignalingErrorCode` は依頼 (A) が受理された時点で上流の型から変換する。
- 転送フィルターは現行の `forwarding_filter` (単体) と `forwarding_filters` (配列) の両方から `ForwardingFilter` の配列へ正規化する。
- `SoraDegradationPreference` は依頼 (F) が受理されるまで公開しない。`SoraVideoCodecCapability` 系は上流の `VideoCodecCapability` / `VideoCodecPreference` / `SoraVideoEncoderFactory` へ写像する。

## 完了条件

- `Sora.create_connection` の引数が構造体ベースになり、49 引数の機械同期がなくなっていること。
- 上流に受け口がある接続設定がすべて指定できること。
- `forwarding_filter` / `forwarding_filters` / `data_channels` / 証明書 / プロキシ / 各待ち上限が動作すること。
- `SoraSignalingType` / `SoraSignalingDirection` / `SoraLoggingSeverity` と `rtc_log` / `enable_libwebrtc_log` が動作すること。
- `SoraVideoCodecCapability` 系が動作すること。
- 実 Sora に対する接続で、設定した内容が接続に反映されることを確認する pytest が通ること。

## 依存

- 先行: ビルド基盤を maturin へ置き換える issue、コールバック中継の issue。
- 上流: sora-rust-sdk への切断結果 (A)、受信 offer (B)、受信 RPC (C)、切替内容 (D)、送信設定 4 項目 (F) の追加依頼。
- 後続: テスト移行、既存 issue の処遇、ドキュメント追従の各 issue が本 issue に依存する。

## 解決方法
