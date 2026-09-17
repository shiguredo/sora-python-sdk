# WebRTC-Video-PerSsrcKeyframes の per-SSRC キーフレーム生成を E2E で検証する

- Created: 2026-09-17
- Completed: -
- Branch: feature/test-verify-per-ssrc-keyframes
- Polished: 2026-09-17

## 目的

`WebRTC-Video-PerSsrcKeyframes` フィールドトライアルを有効にすると、PLI を受けた SSRC の映像レイヤだけがキーフレームを生成する。この挙動を実 Sora に対する E2E テストで検証できるようにする。

`tests/test_field_trials.py` のテストは、フィールドトライアル文字列が libwebrtc まで届いていること（不正な文字列で `RuntimeError` になること）と、フィールドトライアル有効時にもキーフレーム要求が機能することしか確認しておらず、per-SSRC 挙動そのものは検証できていない。フィールドトライアルを有効にしても挙動が変わらない不具合を検知できない。

## 現状

- `Sora` に libwebrtc のフィールドトライアルを指定する `field_trials` 引数があり、`WebRTC-Video-PerSsrcKeyframes/Enabled/` を指定できる。指定した文字列は `src/sora_factory.cpp` の `SoraFactory` コンストラクタで `sora::SoraClientContextConfig::field_trials` に設定される。
- `Sora_20241218.RequestKeyFrame` API は `rid` を指定でき、指定した場合はその rid の SSRC にのみ PLI が送られる。`rid` の対応は Sora `2026.2.0-canary.15` で追加されたため、テストを実行する Sora サーバはこれ以降のバージョンが必要である。`tests/api.py` の `request_key_frame_api` は `rid` を送っていない。
- テスト用サーバに対して次の挙動を実測した（VP8 / 3 レイヤのサイマルキャスト、`video_bit_rate` 指定で全レイヤ有効）。
  - フィールドトライアル有効 + `rid=r2`: `keyFramesEncoded` は r2 のみ 2 から 7 に増加し、r0 / r1 は 2 のまま変化しなかった。`pliCount` も r2 のみ 0 から 5 に増加した。
  - フィールドトライアル無効 + `rid=r2`: `keyFramesEncoded` は r0 / r1 / r2 すべて 2 から 7 に増加した。`pliCount` は r2 のみ 0 から 5 に増加した。
  - どちらも送信側の `encoderImplementation` は `SimulcastEncoderAdapter (libvpx, libvpx, libvpx)` であり、レイヤごとに独立したエンコーダが使われている。
- 以前の実測で全レイヤのキーフレームが生成されていたのは、`rid` を指定せず全レイヤに PLI が送られる API 呼び出しを使っていたためである。
- libwebrtc 側の実装は次のとおり。
  - `video/video_send_stream_impl.cc` で `x-google-per-layer-pli` または `WebRTC-Video-PerSsrcKeyframes` の有効時に per-layer PLI が有効になる。
  - `video/encoder_rtcp_feedback.cc` の `EncoderRtcpFeedback::OnReceivedIntraFrameRequest` は、per-layer PLI が有効なときだけ PLI を受けた SSRC のレイヤに `SendKeyFrame(layers)` を呼ぶ。無効なときは全レイヤに `SendKeyFrame()` を呼ぶ。
  - `media/engine/simulcast_encoder_adapter.cc` の `SimulcastEncoderAdapter` は、フィールドトライアルでは separate encoders を強制しない。単一の simulcast 対応エンコーダで bypass mode になる構成では、フレームタイプがそのエンコーダにそのまま渡るため、コーデックの実装によっては全レイヤがキーフレームになる（libvpx の VP8 / VP9 は「いずれかのストリームへの要求で全ストリームを key にする」実装になっている）。

## 設計方針

- `tests/api.py` の `request_key_frame_api` に省略可能な `rid` 引数を追加し、`Sora_20241218.RequestKeyFrame` に `rid` を送れるようにする。
- `tests/test_field_trials.py` に、VP8 / 3 レイヤのサイマルキャスト送信で `rid=r2` のキーフレーム要求を行い、フィールドトライアルの有無で `keyFramesEncoded` の増加を比較するテストを追加する。
  - フィールドトライアル有効: r2 のみ増加し、r0 / r1 は増加しないこと。
  - フィールドトライアル無効: r0 / r1 / r2 すべて増加すること。
  - 実測で確認した `SimulcastEncoderAdapter (libvpx, libvpx, libvpx)` の構成を前提とする。エンコーダ構成が変わると差が出なくなる可能性があるため、コメントで前提を明記する。
- レイヤの有効化に伴う全レイヤのキーフレーム生成（`DynamicH264Encoder` などにある legacy 挙動）と区別できるよう、キーフレーム要求前に統計を取得し、要求後に増加を確認する。
- r0 / r1 が増加しないことの判定は、キーフレーム要求の前後で 3 レイヤすべてが有効（`bytesSent` が 0 より大きい）なままであることを前提とする。レイヤが無効化されたあと再有効化されると、libvpx の `LibvpxVp8Encoder::SetStreamState` がそのレイヤのキーフレーム要求を立てるため、キーフレーム要求に起因しない増加が起こり得る。キーフレーム要求の前後で 3 レイヤが有効なままであることと、`qualityLimitationReason` が `none` であることを確認する。

## 完了条件

- `WebRTC-Video-PerSsrcKeyframes` の有無で `keyFramesEncoded` の増加レイヤが変わることを検証するテストが `tests/` に追加され、実 Sora に対して成功すること。
- フィールドトライアル有効側の接続から `field_trials` の指定を外すと `keyFramesEncoded` は r0 / r1 / r2 すべて増加し、フィールドトライアル有効側の期待（r2 のみ増加）が満たされずテストが失敗すること。フィールドトライアルが効いていない状態をこのテストが検知できることの確認手順とする。
