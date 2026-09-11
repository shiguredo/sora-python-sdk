# サイマルキャストの E2E テストが encoderImplementation のチェックでエラーとなった原因を調査する

- Created: 2026-09-11
- Completed: -
- Branch: feature/test-investigate-encoder-implementation
- Polished: -
- Reporter: @miosakuma

## 目的

サイマルキャストの E2E テストで `encoderImplementation` の期待値が一致しなくなった原因を調査する。

`SimulcastEncoderAdapter (libaom, libaom, libaom)` を期待していたが、`SimulcastEncoderAdapter (libaom)` が返るようになった。Sora Labo で `sora-2025.1.0-canary.9` と `undoc_transport_wide_cc_incoming = true` を設定したところ挙動が変わり、この設定の無い Sora では成功していた。テストを通すために期待値を緩めたが、原因は未解明である。

## 現状

- `tests/test_simulcast.py` の `test_simulcast` は `SimulcastEncoderAdapter` の部分一致と `encoder_implementation` の部分一致で確認しており、`(libaom, libaom, libaom)` と `(libaom)` の違いを検出できない。
- `tests/test_openh264.py` と `tests/test_macos.py` にも simulcast の `encoderImplementation` を確認するテストがある。
- 関係者による確認では、Sora Labo で `test_simulcast` が `SimulcastEncoderAdapter (libvpx, libvpx, libvpx)` / `SimulcastEncoderAdapter (libaom)` を返し、`test_macos_simulcast` / `test_openh264_simulcast` は `(VideoToolbox, VideoToolbox)` / `(OpenH264, OpenH264)` を返した。
- sora-python-sdk-examples での手動確認では `SimulcastEncoderAdapter (libaom, libaom, libaom)` が返っており、カメラ映像とフェイク映像の差の可能性が指摘されている。
- `undoc_transport_wide_cc_incoming = true` が `encoderImplementation` の表記に影響する仕組みは未調査。

## 設計方針

- `undoc_transport_wide_cc_incoming = true` の有無で何が変わるかを Sora / libwebrtc の実装から確認する。
- カメラ映像とフェイク映像 (テストの `fake_video`) で `encoderImplementation` が変わるかを切り分ける。E2E をカメラ映像で動かせるかも検討する。
- 原因が判明したら、期待値を元に戻せるか、部分一致のままでよいかを決める。
- Sora / libwebrtc 側の挙動であって Python SDK の問題ではない場合は、その旨を記録する。

## 完了条件

- `encoderImplementation` の表記が変わる条件が特定されていること。
- カメラ映像とフェイク映像の差、`undoc_transport_wide_cc_incoming` の影響が切り分けられていること。
- テストの期待値を厳密にするか、部分一致のままでよいかの判断が記録されていること。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- `undoc_transport_wide_cc_incoming = true` が `encoderImplementation` に影響する仕組みが未解明。
- カメラ映像とフェイク映像で挙動が変わるかどうかの切り分けが未了。
- E2E テストをカメラ映像で動かせるかの検討が必要。
- 原因が Sora / libwebrtc 側か Python SDK 側かの切り分けが必要。

再開するときは reopened にしてから実装を進める。
