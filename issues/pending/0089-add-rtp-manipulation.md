# 変なパケットを送れる仕組みを検討する

- Created: 2026-09-11
- Completed: -
- Branch: feature/add-rtp-manipulation
- Polished: -
- Reporter: @voluntas

## 目的

Sora の E2E テストで、意図的に壊した RTP や改変した RTP を送れる仕組みを検討する。

タイムスタンプを指定できる仕組みが E2E テストで役立ったのと同様に、次のような異常系をテストできると、Sora やアプリ側の耐性を確認できる。

- 壊れた RTP を送る
- シーケンス番号を変えて送る
- RTP 拡張を追加する
- 参考: <https://github.com/aboba/webrtc-rtptransport>

## 現状

- WebRTC Encoded Transform に対応しており、`SoraTransformableFrame` でフレームデータ (`set_data`) と RTP タイムスタンプ (`rtp_timestamp`) を書き換えられる (`src/sora_frame_transformer.h`、`src/sora_sdk/sora_sdk_ext.pyi`)。
- `payload_type` / `ssrc` は読み取り専用で、シーケンス番号・マーカービット・ RTP 拡張は公開されていない。壊れた RTP やシーケンス番号の改変、 RTP 拡張の追加は Encoded Transform だけでは行えない。
- `src/sora_frame_transformer.h` の `SoraTransformableFrame` は `webrtc::TransformableFrameInterface` をラップしており、フレーム単位の操作に限定される。 RTP パケット単位の操作は提供していない。
- 異常系の RTP を送る仕組みは E2E テストに存在しない。

## 設計方針

保留を解除したら、まず何をどこで改変できるようにするかを決める。

- Encoded Transform の口を拡張し、`SoraTransformableFrame` にシーケンス番号や RTP 拡張を設定する API を追加する。libwebrtc の `TransformableFrameInterface` で公開されている範囲で実現できるかを確認する。
- Encoded Transform では届かない RTP 拡張やシーケンス番号は、libwebrtc の RTP 送信経路に手を入れずにテストする方法 (受信した RTP パケットを直接改変して送り返すなど) を検討する。
- 参考にする webrtc-rtptransport の方式を調査する。
- テスト専用の仕組みとして提供するか、通常の API として公開するかを決める。

## 完了条件

- 壊れた RTP / 改変したシーケンス番号 / 追加した RTP 拡張を送れることが、実 Sora に対する E2E テストで確認できる。
- 送信した異常系 RTP に対して Sora / 受信側がどう振る舞うかを確認できる。
- 実現方法が README または docstring に記載されている。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- RTP パケット単位の操作は libwebrtc / Sora C++ SDK の公開 API に無く、Encoded Transform だけでは実現できる範囲が限られる。実現方法の設計が必要。
- テスト専用 API として公開するか、通常 API に含めるかの判断が必要。
- 参考にする webrtc-rtptransport の方式の調査が未了。

再開するときは reopened にしてから実装を進める。
