# capture_time_identifier を SoraTransformableVideoFrame で取得できるようにする

- Created: 2026-09-11
- Completed: -
- Branch: feature/add-capture-time-identifier
- Polished: -
- Reporter: @tnoho

## 目的

撮影時のタイムスタンプ (capture_time_identifier) を WebRTC Encoded Transform のフレームから取得できるようにする。

capture_time_identifier はフレームの撮影時に発行され、Capturer から Encoded Transform まで引き継がれる。Encoded Transform でエンコード済みフレームと撮影時のフレームを紐づけられるため、撮影時のセンサーデータなど映像に同期した情報をエンコード済みフレームに記録できる。libwebrtc 内部には実装があるが、Sora の独自 Capturer / Encoder では値が欠落するため、対応を入れて Python SDK から参照できるようにする。

## 現状

- `src/sora_frame_transformer.h` の `SoraTransformableFrame::GetCaptureTimeIdentifier()` が `frame_->GetPresentationTimestamp()` を読み、マイクロ秒の `std::optional<int64_t>` として返す実装を持つ。
- `src/sora_sdk_ext.cpp` の `SoraTransformableVideoFrame` のバインディングには `capture_time_identifier` が無く、Python から取得できない (`src/sora_sdk/sora_sdk_ext.pyi`)。
- libwebrtc の `webrtc::TransformableFrameInterface` には `GetPresentationTimestamp()` (`std::optional<Timestamp>`) がある。値が無い場合は `std::nullopt` を返す。旧 API の `GetCaptureTimeIdentifier()` は deprecated (`_install/<platform>/webrtc/include/api/frame_transformer_interface.h`)。
- Sora C++ SDK の独自 Capturer / Encoder は capture_time_identifier に対応しておらず、値が設定されない。

## 設計方針

- Python SDK 側は `SoraTransformableVideoFrame` に読み取り専用プロパティ `capture_time_identifier` を追加し、`GetCaptureTimeIdentifier()` の値をマイクロ秒の `int | None` で返す。値が無い場合は `None` を返す。
- 音声にも同じ仕組みがあるが、本 issue では映像 (`SoraTransformableVideoFrame`) を対象とし、音声が必要になったら別 issue にする。
- Sora C++ SDK 側の独自 Capturer / Encoder が capture_time_identifier を設定する対応が前提になる。Python SDK 側のバインディングは C++ SDK の対応と独立して追加できる。

## 完了条件

- `SoraTransformableVideoFrame.capture_time_identifier` で撮影時のタイムスタンプを取得できる。
- 値が無い場合は `None` になる。
- `tests/` に `capture_time_identifier` を確認するテストがある。
- 利用方法が README または docstring に記載されている。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- Sora C++ SDK の独自 Capturer / Encoder が capture_time_identifier を設定する対応が必要で、その実現方法と時期が未定。
- C++ SDK 側で値が設定されない限り、Python SDK のテストで実際に値が入ることを確認できない。
- Sora C++ SDK 側は WebRTC Encoded Transform に対応していないため、Capturer / Encoder への変更が他へ影響しないかを確認する必要がある。

再開するときは reopened にしてから実装を進める。
