# libwebrtc の非推奨 API 利用を解消する

- Created: 2026-09-11
- Completed: -
- Branch: feature/update-libwebrtc-deprecated-apis
- Polished: -

## 目的

Sora C++ SDK を `2026.3.0-canary.5` に上げたことで WebRTC が `m152` から `m154` になり、`src/` が使っている libwebrtc API のうち 3 つが `[[deprecated]]` になった。ビルド時に非推奨警告が出ており、将来の libwebrtc 更新で削除されるとビルドが通らなくなる。警告を解消し、後継 API へ追従する。

## 現状

ビルド時に次の非推奨警告 (`-Wdeprecated-declarations`) が出る。

1. `src/sora_log.cpp` の `EnableLibwebrtcLog` が `webrtc::LogMessage::LogThreads()` を呼んでいる。`rtc_base/logging.h` の `LogMessage::LogThreads` に `[[deprecated("Use InitializeLogging instead.")]]` が付いている。
2. `src/sora_frame_transformer.h` の `SoraTransformableFrame::GetTimestamp()` が `frame_->GetTimestamp()` を呼んでいる。`api/frame_transformer_interface.h` の `TransformableFrameInterface::GetTimestamp` に `[[deprecated("Use GetRtpTimestampInfo instead")]]` が付いている。後継の `GetRtpTimestampInfo()` は `RtpTimestampInfo` (`std::variant<RtpTimestampWithOffset, RtpTimestampWithoutOffset>`) を返し、RTP timestamp のオフセットが不明なケースを区別できる。旧 `GetTimestamp()` はオフセットが不明でも値を返していた。
3. `src/sora_frame_transformer.h` の `SoraTransformableVideoFrame::GetFrameDependencies()` が `frame()->Metadata().GetFrameDependencies()` を呼んでいる。`api/video/video_frame_metadata.h` の `VideoFrameMetadata::GetFrameDependencies` に `[[deprecated("Use GetDependencies instead")]]` が付いている。後継の `GetDependencies()` は `std::optional<std::span<const int64_t>>` を返す。

Python 公開 API への影響:

- 1 は `src/sora_sdk_ext.cpp` の `enable_libwebrtc_log` から呼ばれる。
- 2 は `src/sora_sdk_ext.cpp` で `SoraTransformableFrame.rtp_timestamp` (読み書き property) として公開されている。
- 3 は `src/sora_sdk_ext.cpp` で `SoraTransformableVideoFrame.get_frame_dependencies` として公開されている。

## 設計方針

- 警告の解消を目的とし、Python 公開 API の後方互換は維持する。
- ログ設定は `webrtc::LoggingConfig` と `webrtc::InitializeLogging` に置き換える。`set_min_severity(severity)` / `set_log_thread(true)` / `set_log_timestamp(true)` を設定して `InitializeLogging` を 1 回呼び、既存の `LogToDebug` / `LogTimestamps` / `LogThreads` 呼び出しは削除する。`InitializeLogging` は 1 回しか呼べないため、複数回呼ばれない前提をコードコメントに残す。
- `rtp_timestamp` は従来どおり `int` を返す。`GetRtpTimestampInfo()` の variant は `RtpTimestampWithOffset` / `RtpTimestampWithoutOffset` のどちらでも `value` を取り出して返す。オフセットの有無を Python に公開するかは本 issue では扱わない (必要になったら別 issue にする)。
- `get_frame_dependencies` は `GetDependencies()` の `std::optional` を扱う。`std::nullopt` のときは長さ 0 の ndarray を返し、空を表す従来挙動に合わせる。
- 破壊的な公開 API 変更が必要になった場合は本 issue に混ぜず、別 issue に分ける。

## 完了条件

- `m154` で上記 3 箇所の非推奨警告が出ないこと。
- `enable_libwebrtc_log` の動作 (指定 severity の出力、タイムスタンプ、スレッド ID の表示) が維持されていること。
- `SoraTransformableFrame.rtp_timestamp` と `SoraTransformableVideoFrame.get_frame_dependencies` の後方互換が維持されていること。
- ビルドが成功し、既存テストが通ること。
- CHANGES.md の `## develop` にエントリが追記されていること。

## 解決方法

1. `src/sora_log.cpp` の `EnableLibwebrtcLog` を `webrtc::LoggingConfig` + `webrtc::InitializeLogging` に書き換える。
2. `src/sora_frame_transformer.h` の `SoraTransformableFrame::GetTimestamp()` を `GetRtpTimestampInfo()` ベースに書き換える。
3. `src/sora_frame_transformer.h` の `SoraTransformableVideoFrame::GetFrameDependencies()` を `GetDependencies()` ベースに書き換える。
4. `uv run python run.py build macos_arm64` などでビルドし、該当警告が消えていることを確認する。
5. ログ出力と `get_frame_dependencies` の挙動を確認するテストを追加または更新する。
6. CHANGES.md の `## develop` に `[UPDATE]` エントリを追記する。
