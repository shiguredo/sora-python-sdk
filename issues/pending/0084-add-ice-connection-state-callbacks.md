# ICE / PeerConnection の状態変化コールバックを追加する

- Created: 2026-09-11
- Completed: -
- Branch: feature/add-ice-connection-state-callbacks
- Polished: -
- Reporter: @voluntas

## 目的

ICE 接続状態、PeerConnection 接続状態、ICE 収集状態の変化を Python から検知できるようにする。

現状は接続確立や切断をシグナリングの `on_notify` (`connection.created` / `connection.destroyed`) や `on_disconnect` でしか把握できず、PeerConnection レベルの接続確立を直接待てない。`on_connection_state_change` があれば、`connected` を待つ処理をシグナリングの notify に依存せず書ける。

## 現状

- Python 側は `SoraConnection` のコールバックとして `on_set_offer` / `on_ws_close` / `on_disconnect` / `on_signaling_message` / `on_notify` / `on_push` / `on_message` / `on_rpc` / `on_switched` / `on_track` / `on_data_channel` を持つ (`src/sora_connection.h`、`src/sora_sdk_ext.cpp`)。
- 接続確立の検知は `on_notify` の `connection.created` に依存している (`tests/client.py` など)。
- Sora C++ SDK の `sora::SoraSignalingObserver` には ICE / PeerConnection の状態変化を通知するコールバックが無い (`_install/<platform>/sora/include/sora/sora_signaling.h`)。
- `sora::SoraSignaling` は `webrtc::PeerConnectionObserver` の `OnStandardizedIceConnectionChange()` / `OnConnectionChange()` / `OnIceGatheringChange()` を実装している。ただし前者 2 つは内部の `ice_state_` / `connection_state_` を更新するだけで `SoraSignalingObserver` へは通知しておらず、`OnIceGatheringChange()` は空実装である。
- Python SDK は `sora::SoraSignaling` をそのまま利用しており PeerConnection を直接持たないため、SDK 側だけで状態変化を拾うことができない。

## 設計方針

保留を解除したら、まず Sora C++ SDK 側で状態変化を observer へ通知できるようにする方法を確認し、次のいずれかの形を選ぶ。

- `SoraConnection` に `on_ice_connection_state_change` / `on_connection_state_change` / `on_ice_gathering_state_change` を追加する。コールバック引数は libwebrtc の enum をそのまま公開するか、Python 向けの enum を新設するかを決める。
- WebRTC の `RTCPeerConnection` と同様に、状態を `SoraConnection` のプロパティとして取得できるようにする。変化のたびにコールバックを呼ぶ形と、最新値だけを保持する形のどちらにするかを決める。

いずれの場合も既存の `on_notify` / `on_disconnect` は残し、破壊的変更にしない。コールバックの呼び出しは既存コールバックと同じく Python GIL を保持する経路で行う。

## 完了条件

- ICE 接続状態、PeerConnection 接続状態、ICE 収集状態の変化を Python から検知できる。
- 各状態の値が libwebrtc のどの状態に対応するかが分かる形で公開されている。
- `tests/` に状態変化の検知を確認するテストがある。
- 利用方法が README または docstring に記載されている。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- Sora C++ SDK の `sora::SoraSignalingObserver` に状態変化を通知するコールバックが無く、SDK 側の対応が必要。その実現方法と時期が未定。
- 公開する状態の型。libwebrtc の `IceConnectionState` / `PeerConnectionState` / `IceGatheringState` を直接公開するか、Python 向けの enum を定義するか。
- API の形。3 つのコールバックを追加するか、状態プロパティと変化コールバックの組み合わせにするか。
- `on_connection_state_change` が通知する状態の粒度と、シグナリングの `connection.created` との役割分担。

再開するときは reopened にしてから実装を進める。
