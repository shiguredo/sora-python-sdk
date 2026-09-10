# トラック単位でのミュート機能を追加する

- Created: 2026-09-10
- Completed: -
- Branch: feature/add-track-level-mute
- Polished: -

## 目的

接続を維持したまま、実行中の Python スクリプトから送信中の音声 / 映像トラックをトラック単位でミュート / アンミュートできるようにする。

テスト用途で、送信中にミュートを切り替えたときの受信側の挙動 (無音になるか、黒フレームになるか、統計値がどう変わるか) を Python SDK で確認したいという要望がある。

## 現状

`src/sora_sdk_ext.cpp` のバインディングで `SoraTrackInterface` に `enabled` と `set_enabled(enable)` が公開されており、`SoraAudioSource` / `SoraVideoSource` / `SoraMediaTrack` から呼び出せる。実装は `src/sora_track_interface.h` の `SoraTrackInterface::enabled` / `SoraTrackInterface::set_enabled` で、`webrtc::MediaStreamTrackInterface::set_enabled` をそのまま呼び出している。

WebRTC の `api/media_stream_interface.h` では `set_enabled` を "A disabled track will produce silence (if audio) or black frames (if video). Can be disabled and re-enabled." と定義しており、API 上はトラック単位のミュートに利用できる。ただし次の点が未確認であり、ミュート機能として使えるか判断できていない。

- 送信側トラック (`SoraAudioSource` / `SoraVideoSource`) で `set_enabled(false)` を呼んだときに、実際に無音 / 黒フレームが送信されるか。`SoraAudioSource` は `SoraAudioSourceInterface::OnData` へ直接 PCM を渡す構成であり、`enabled` と送信内容の関係を確認した実績がない。
- Python のどのスレッドから呼んでよいか。WebRTC のトラック実装にはシグナリングスレッドを前提とするものがあり、任意スレッドからの呼び出しが安全か未確認である。
- ミュート中も `on_data` を呼び続ける必要があるか、呼び続けた場合に無音が送信されるか。
- `tests/` に `set_enabled` を使ったテストはなく、README にもミュート用途の説明はない。

## 設計方針

保留を解除したら、まず既存の `set_enabled` で要件を満たせるか検証する。検証結果に応じて次のどちらかを選ぶ。

- 既存の `set_enabled` で無音 / 黒フレームを送信できることが確認できた場合、ミュート用途での使い方 (呼び出しスレッド、`on_data` を継続するか等) を決めてドキュメントとテストを追加する。
- 実現できない場合、送信側トラックに専用のミュート API を追加する。接続を維持したまま音声 / 映像を個別に切り替えられる形とし、ミュート中は無音 / 黒フレームを送信する。

## 完了条件

- 接続を維持したまま、実行中の Python スクリプトから音声 / 映像トラックをトラック単位でミュート / アンミュートできる。
- ミュート中は対象トラックのメディアが無音 (音声) または黒フレーム (映像) になり、アンミュートで送信が再開することをテストで確認できる。
- 利用方法が README に記載されている。

## pending にした理由

要望が「テスト的に欲しい」という段階に留まり、具体的な利用シーン (どのトラックを、いつ、何のためにミュートするか) が確定していない。また、既存の `set_enabled` で実現できる可能性があり、専用 API を追加すべきかを判断できない。要件の具体化と既存 API の検証が進むまで保留する。再開するときは reopened にしてから実装を進める。
