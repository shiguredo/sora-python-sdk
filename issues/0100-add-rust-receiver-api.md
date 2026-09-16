# 受信系 API を Rust ベースで実装する

- Created: 2026-09-16
- Completed: -
- Branch: feature/add-rust-receiver-api
- Polished: {YYYY-MM-DD}

## 目的

現行 `sora_sdk` の受信系公開 API を sora-rust-sdk + PyO3 で再現し、recvonly の利用を置き換え可能にする。

## 現状

- 受信系の公開面は `src/sora_sdk/sora_sdk_ext.pyi` の `SoraAudioSinkImpl` / `SoraAudioStreamSinkImpl` / `SoraVideoSinkImpl` / `SoraAudioFrame` / `SoraVideoFrame` / `SoraTrackInterface` / `SoraMediaTrack` と `SoraConnection.on_track` である。
- `SoraAudioSinkImpl` は `read(frames, timeout)` で numpy 配列を取り出し、`on_data` と `on_format` のコールバックを持つ。`output_frequency` / `output_channels` を指定するとリサンプルする。
- `SoraAudioStreamSinkImpl` は `on_frame` で `SoraAudioFrame` を渡し、`samples_per_channel` / `num_channels` / `sample_rate_hz` / `absolute_capture_timestamp_ms` / `data` を持つ。
- `SoraVideoSinkImpl` は `on_frame` で `SoraVideoFrame` を渡し、`data` は ARGB の numpy 配列である。
- `src/sora_sdk/__init__.py` は C++ 側で track を `shared_ptr` 保持するとリークするため、Python 側で track 参照を持つラッパーになっている。
- 受信音声の駆動は `src/sora_factory.cpp` が `context_config.configure_dependencies` で `dependencies.audio_mixer` に自前の `DummyAudioMixer` を差し込んで行う。`use_audio_device` を false にすると通常の AudioMixer では音声ループが止まり、`SoraAudioSinkImpl` が実装する `webrtc::AudioTrackSinkInterface::OnData` が発火しないためである。
- sora-rust-sdk の受け口は `AudioTrackSinkHandler::on_data` (生 PCM) と `VideoSinkHandler::on_frame` (`VideoFrameRef`) である。受信 Sink は sora-rust-sdk には無く、`shiguredo_webrtc` のものを直接使う。
- `shiguredo_webrtc` の `MediaStreamTrack` に状態取得が無く、`RtpReceiver` に `stream_id` が無い。

## 設計方針

- `docs/migration-to-sora-rust-sdk.md` の決定事項 12 に従い、受信音声は `AudioDeviceModuleHandler` を実装した偽オーディオデバイスで再生を駆動する。`AudioMixer` の露出は上流へ依頼しない。偽デバイスは 10 ms 周期で再生要求を出し、要求はステレオ 48 kHz で行い、時刻ポインタには有効な変数を渡す。
- 映像は `VideoSinkHandler::on_frame` で受けた `VideoFrameRef` を ARGB の numpy 配列へ変換して渡す。
- 音声のリサンプル (`output_frequency` / `output_channels`) は本 issue の対象外とし、リサンプラと VAD の issue で扱う。本 issue ではネイティブ形式のまま渡す経路を作る。
- `SoraTrackInterface.state` と `SoraMediaTrack.stream_id` は上流に受け口が無いため、本 issue の対象外とする。上流の依頼 (G) が受理されるまで実装できない。
- コールバックの Python 中継方式はコールバック中継の issue で確定する。本 issue では Sink の受け渡しに必要な最小限の経路を作る。
- `src/sora_sdk/__init__.py` の track 参照保持ラッパーが必要かどうかは、Rust 側の参照カウンタの扱いを実装して検証する。不要なら削除する。

## 完了条件

- recvonly で音声 PCM と映像フレームを numpy で受け取れること。
- `SoraAudioSinkImpl` の `read` / `on_data` / `on_format`、`SoraAudioStreamSinkImpl` の `on_frame`、`SoraVideoSinkImpl` の `on_frame` が動作すること。
- `SoraConnection.on_track` で受信トラックを取得できること。
- 実 Sora に対する recvonly 接続で音声と映像のフレーム受信を確認する pytest が通ること。
- リークがないこと (接続の終了後に受信トラックと Sink が解放されること)。

## 依存

- 先行: ビルド基盤を maturin へ置き換える issue。
- 上流: webrtc-rs への `MediaStreamTrack` の状態取得と `RtpReceiver` の `stream_id` の追加依頼 (G)。受理されるまで `SoraTrackInterface.state` と `SoraMediaTrack.stream_id` は実装できない。
- 後続: 送信系 API、リサンプラと VAD、テスト移行の各 issue が本 issue に依存する。

## 解決方法
