# Rust ベースで送信系 API を再現する

- Created: 2026-09-04
- Completed: -
- Branch: feature/add-sora-rust-sdk-prototype
- Polished: {YYYY-MM-DD}

## 目的

既存 `sora_sdk` の送信系公開 API を Rust ベースで再現し、
sendonly / sendrecv 利用を置き換え可能にする。

## 現状

- 受信系は `Sora` / `SoraConnection` / `SoraMediaTrack` / Sink 群として再現済みである。
- 送信側の `SoraAudioSource` / `SoraVideoSource` と `on_data` / `on_captured` による
  フレーム投入経路は未実装である。
- `SoraConnection::builder` には `sender_audio_track` / `sender_video_track` があり、
  トラックの組み立て自体は可能である。
- 音声の取り込みは `AdmConfig::UseBuiltIn` の実マイク経路でしか実証しておらず、
  任意 PCM の投入経路は未実証である。
- 映像の取り込みはループバック検証の `AdaptedVideoTrackSource::on_frame` で
  黒フレーム投入を実証済みである。

## 設計方針

- `Sora.create_audio_source` / `create_video_source` に対応する Rust 型を追加し、
  `create_connection` で `audio_source` / `video_source` を受け取って
  `sender_audio_track` / `sender_video_track` に組み立てる。
- 音声は偽デバイス (`src/fake_audio_device.rs` の `FakeAudioDevice`) の
  録音側に PCM 投入口を追加し、10 ms 周期の取り込み駆動で送信する。
  再生駆動と同様にステレオ 48 kHz 要求と有効な時刻ポインタの注意点を守る。
- 映像は `AdaptedVideoTrackSource` を保持し、`on_captured` で受けた
  RGB フレームを I420 変換して投入する。
- 送信系以外の追加引数 (コーデック指定やビットレート等) は対象外とし、
  後続 issue に切り出す。

## 完了条件

- sendonly で音声 PCM と映像フレームを送信し、対向の受信で確認できること。
- 対応する pytest が通ること。
