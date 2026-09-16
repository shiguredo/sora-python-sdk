# 音声リサンプラと VAD を Rust ベースで実装する

- Created: 2026-09-16
- Completed: -
- Branch: feature/add-resampler-and-vad
- Polished: {YYYY-MM-DD}

## 目的

現行 `sora_sdk` の音声リサンプルと VAD を sora-rust-sdk + PyO3 で再現する。いずれも libwebrtc の実装をそのまま使うことで、現行と同等の出力を保つ。

## 現状

- 音声のリサンプルは `src/sora_audio_sink.h` と `src/sora_audio_stream_sink.h` が libwebrtc の `webrtc::PushResampler<int16_t>` を使う。`SoraAudioSinkImpl` の `output_frequency` / `output_channels` と `SoraAudioStreamSinkImpl` の同じ引数で指定する。
- VAD は `src/sora_vad.cpp` の `SoraVAD` が libwebrtc の `webrtc::VoiceActivityDetectorWrapper` (`modules/audio_processing/agc2/vad_wrapper.h`) を使い、`analyze(frame)` で音声確率を float で返す。
- `shiguredo_webrtc 0.154.0` にリサンプラの型が無い。`src/` と C++ ラッパーの両方を検索して 0 件である。
- `shiguredo_webrtc 0.154.0` に VAD の型が無い。`voice_activity_detection` は `RTCOfferAnswerOptions` のフラグであり、`VoiceActivityDetectorWrapper` の露出ではない。
- `webrtc::VoiceActivityDetectorWrapper` は libwebrtc の C++ API に存在するが、shiguredo の C ラッパーに露出していないため Rust 側から参照できない。

## 設計方針

- `docs/migration-to-sora-rust-sdk.md` の決定事項 8 と 10 に従う。
- webrtc-rs へ `PushResampler<int16_t>` 相当と `VoiceActivityDetectorWrapper` 相当の露出を依頼する (依頼 H と I)。受理されるまで本 issue は着手しない。
- リサンプラも VAD も自前実装で代替しない。直線補間などの簡易実装は設計方針で禁止されており、現行と出力が一致する保証が無い。
- 依頼が受理されない場合は、`SoraVAD` と `output_frequency` / `output_channels` を公開 API から削除する判断をユーザーに仰ぐ。勝手に代替実装へ切り替えない。
- `SoraAudioFrame` の `absolute_capture_timestamp_ms` は上流のフレームから取得できる場合のみ返し、取得できない場合は `None` を返す。値を合成しない。

## 完了条件

- `SoraAudioSinkImpl` と `SoraAudioStreamSinkImpl` の `output_frequency` / `output_channels` が現行と同じ結果を返すこと。
- `SoraVAD.analyze` が現行と同じ音声確率を返すこと。
- 実 Sora に対する受信で、リサンプル後の音声と VAD の判定を確認する pytest が通ること。
- モックやスタブを使っていないこと。

## 依存

- 先行: ビルド基盤を maturin へ置き換える issue、受信系 API の issue。
- 上流: webrtc-rs への VAD の露出依頼 (H) と音声リサンプラの露出依頼 (I)。いずれも受理されるまで本 issue は着手しない。
- 後続: テスト移行の issue が本 issue に依存する。

## 解決方法
