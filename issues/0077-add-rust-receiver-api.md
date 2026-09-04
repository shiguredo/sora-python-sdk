# Rust ベースで受信系 API を再現する

- Created: 2026-09-04
- Completed: -
- Branch: feature/add-sora-rust-sdk-prototype
- Polished: {YYYY-MM-DD}

## 目的

既存 `sora_sdk` の受信系公開 API を Rust ベースで再現し、
recvonly 利用を置き換え可能にする。

## 現状

- プロトタイプのループバックで受信経路は実証済み
  (`AudioTrackSinkHandler` で PCM、`VideoSinkHandler` で `VideoFrameRef`、
  `convert_from_i420` で ARGB 変換まで確認)。
- `SoraAudioSink` / `SoraVideoSink` / `SoraAudioFrame` / `SoraVideoFrame` や
  `on_track` 等のコールバック中継は未実装である。

## 設計方針

- `AudioTrackSink` / `VideoSink` を Rust 側で保持し、
  PCM・ARGB を numpy で Python に渡す。
- コールバックは GIL 取得スレッドで Python callable を呼ぶ。
- 送信系・メッセージングは対象外とし、後続 issue に切り出す。

## 完了条件

- recvonly で音声・映像フレームを numpy で受け取れること。
- 対応する pytest が通ること。
