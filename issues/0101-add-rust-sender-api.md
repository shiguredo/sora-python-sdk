# 送信系 API を Rust ベースで実装する

- Created: 2026-09-16
- Completed: -
- Branch: feature/add-rust-sender-api
- Polished: {YYYY-MM-DD}

## 目的

現行 `sora_sdk` の送信系公開 API を sora-rust-sdk + PyO3 で再現し、sendonly / sendrecv の利用を置き換え可能にする。

## 現状

- 送信系の公開面は `src/sora_sdk/sora_sdk_ext.pyi` の `SoraAudioSource` / `SoraVideoSource` と、`Sora.create_audio_source` / `Sora.create_video_source` である。
- `SoraAudioSource.on_data` は 4 つの多重定義を持つ。`(data, samples_per_channel, timestamp)` / `(data, samples_per_channel)` の番地指定と、numpy 配列を受け取る `(ndarray, timestamp)` / `(ndarray)` である。
- `SoraVideoSource.on_captured` は 3 つの多重定義を持つ。numpy 配列のみ、秒の `timestamp`、マイクロ秒の `timestamp_us` である。
- 音声の取り込みは `src/sora_audio_source.cpp`、映像の取り込みは `src/sora_video_source.cpp` が担う。
- sora-rust-sdk には `SoraConnectionBuilder::sender_audio_track` / `sender_video_track` があり、`SoraConnectionContext::create_audio_source` / `create_audio_track` / `create_video_track` でトラックを組み立てられる。
- 任意 PCM の投入には `AdmConfig` に加えて `AudioDeviceModuleHandler` の録音側の実装が要る。`AudioTransportHandler` (`Send` 境界) が録音駆動の受け口である。
- 映像入力は `shiguredo_webrtc` の `AdaptedVideoTrackSource` を使う。
- 試作は偽オーディオデバイスの録音側と `AdaptedVideoTrackSource::on_frame` で送信経路を実証している。

## 設計方針

- `docs/migration-to-sora-rust-sdk.md` の決定事項 12 に従い、偽オーディオデバイスの録音側で PCM を送信する。受信系 issue と同じ偽デバイスを共有する。
- `SoraAudioSource.on_data` の 4 つの多重定義を維持する。番地指定は受け取った標本数を送信キューへ積む形で扱い、numpy 配列は `int16` の 2 次元配列として扱う。
- `SoraVideoSource.on_captured` の 3 つの多重定義を維持する。RGB の numpy 配列を ARGB 経由で I420 へ変換して投入する。時刻は整数ならマイクロ秒、実数なら秒として扱う。
- 送信キューは上限を持ち、あふれた古いデータを捨てる。取り込み形式は送信元の形式で報告する。
- コーデック指定やビットレートなどの送信設定は本 issue の対象外とし、接続設定の issue で扱う。
- 音声の encoded transform は上流に受け口が無いため対象外とする。上流の依頼 (E) が受理されるまで実装できない。

## 完了条件

- sendonly で音声 PCM と映像フレームを送信し、対向の受信で確認できること。
- `Sora.create_audio_source` / `Sora.create_video_source` が動作すること。
- `SoraAudioSource.on_data` の 4 つの多重定義と `SoraVideoSource.on_captured` の 3 つの多重定義が動作すること。
- 実 Sora に対する sendrecv のループバックで音声と映像の送受信を確認する pytest が通ること。

## 依存

- 先行: ビルド基盤を maturin へ置き換える issue、受信系 API の issue (偽オーディオデバイスを共有するため)。
- 上流: sora-rust-sdk への音声 encoded transform の受け口の追加依頼 (E)。受理されない場合は音声の encoded transform を公開 API から外す。
- 後続: libcamera、テスト移行の各 issue が本 issue に依存する。

## 解決方法
