# データチャネルの open / close コールバックを追加する

- Created: 2026-09-10
- Completed: -
- Branch: feature/add-data-channel-open-close-callbacks
- Polished: -

## 目的

データチャネルが利用可能になったタイミング (open) と閉じたタイミング (close) を Python から明示的に検知できるようにする。

データチャネルは開くまでメッセージを送信できないため、利用側はデータチャネルの準備ができたことを待ってから `send_data_channel()` を呼ぶ必要がある。現状は label を引数に取る `on_data_channel` が open を通知するだけで、close を検知する手段が無い。また、open を `on_open` のような明示的なコールバックとして扱えないため、利用側はどのコールバックを待てばよいかを `on_data_channel` の意味から読み解く必要がある。

## 現状

- `src/sora_sdk_ext.cpp` の `SoraConnection` バインディングで `on_data_channel` を公開している。実体は `src/sora_connection.h` の `SoraConnection::on_data_channel_` (`std::function<void(std::string)>`) で、`src/sora_connection.cpp` の `SoraConnection::OnDataChannel(std::string label)` が label を Python のコールバックに渡す。
- データチャネルは label ベースで扱っており、送信は `SoraConnection::SendDataChannel` (`send_data_channel(label, data)`) で行う。DataChannel オブジェクトそのものは Python に公開していない。
- Sora C++ SDK の `sora::SoraSignalingObserver::OnDataChannel(std::string label)` は DataChannel が開いたときに label を通知する。閉じたときの通知は定義されていない。
- Python SDK が DataChannel の状態変化として受け取れるのは `on_data_channel` のみで、`on_open` / `on_close` に相当する API は存在しない。
- `on_switched` コールバックはあるが、これは WebSocket から DataChannel へのシグナリング切り替えの通知であり、個々の DataChannel の状態変化を通知するものではない。
- `tests/client.py` の `SoraClient.send_message()` は `on_data_channel` を待ってから `send_data_channel()` を呼んでおり、データチャネルの準備完了待ちを `on_data_channel` に依存させている。

## 設計方針

保留を解除したら、まず Sora C++ SDK 側で DataChannel の close を検知できるようにする方法を確認し、次のいずれかの形を選ぶ。

- `SoraConnection` に label を引数に取る `on_data_channel_open` / `on_data_channel_close` を追加する。既存の `on_data_channel` を残せるため破壊的変更にならない。close の通知には `sora::SoraSignalingObserver` 側の対応が必要になる。
- `SoraDataChannel` のようなオブジェクトを Python に公開し、WebRTC API の `RTCDataChannel` と同様に `on_open` / `on_close` を持たせる。状態をオブジェクト単位で扱いやすい一方、既存の label ベース API との併存方法を決める必要がある。

open の通知タイミングを DataChannel が開いた時点とするか、受信側がメッセージを受け取れるようになった時点とするかもあわせて決める。RFC 8832 では open 側は DATA_CHANNEL_ACK を受信する前にメッセージを送信できるとされている。

## 完了条件

- データチャネルの open / close を Python から検知できる。
- `tests/` に open / close の検知を確認するテストがある。
- 利用方法が README または docstring に記載されている。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- API の形。label を引数に取る open / close コールバックを追加するか、DataChannel オブジェクトを公開するか。
- close の通知には Sora C++ SDK 側の対応が必要であり、その実現方法と時期が未定。
- open の通知タイミングと、既存の `on_data_channel` との役割分担。
