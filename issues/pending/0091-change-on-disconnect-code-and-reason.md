# on_disconnect の ErrorCode を DisconnectCode に変更し Reason も取得できるようにする

- Created: 2026-09-11
- Completed: -
- Branch: feature/change-on-disconnect-code-and-reason
- Polished: -
- Reporter: @voluntas

## 目的

`SoraConnection.on_disconnect` の引数を見直し、切断の種類 (code / reason / type) を取得できるようにする。

現状の `on_disconnect` は `SoraSignalingErrorCode` と `message` しか受け取れず、WebSocket / DataChannel の close code や reason を直接扱えない。また `SoraSignalingErrorCode` という名前は実態 (正常終了も含む切断コード) と合っていない。

## 現状

- `SoraConnection.on_disconnect` は `Callable[[SoraSignalingErrorCode, str], None]` で、引数は C++ SDK の `sora::SoraSignalingErrorCode` と `message` (`src/sora_connection.h`、`src/sora_sdk/sora_sdk_ext.pyi`)。
- `sora::SoraSignalingErrorCode` の値は `CLOSE_SUCCEEDED` / `CLOSE_FAILED` / `INTERNAL_ERROR` / `INVALID_PARAMETER` / `WEBSOCKET_HANDSHAKE_FAILED` / `WEBSOCKET_ONCLOSE` / `WEBSOCKET_ONERROR` / `PEER_CONNECTION_STATE_FAILED` / `ICE_FAILED` で、正常終了 (`CLOSE_SUCCEEDED`) も含むため ErrorCode という名前が適切でない。
- C++ SDK の `sora::SoraSignalingObserver::OnDisconnect` は `(ec, message)` のみで、code / reason / type を渡す口が無い。
- 利用側は `message` から切断理由を読み取るしかなく、`ws.close_code` / `ws.close_reason` や `datachannel` の close code / reason を機械的に扱えない。

## 設計方針

保留を解除したら、まず期待する挙動を Sora C++ SDK 側とすり合わせる。

- `SoraSignalingErrorCode` を `DisconnectCode` にリネームする。値の意味は維持し、既存の `on_disconnect` の後方互換をどうするか (エイリアスを残すか、破壊的変更にするか) を決める。
- 次の 3 つを取得できるようにする。
  - C++ SDK レイヤー: `(error_code, message)`
  - 共通 SDK レイヤー: `(type, code, reason)`
    - `code` は `ws.close_code` / DataChannel の close code
    - `reason` は `ws.close_reason` / DataChannel の close reason
    - `type` は `websocket` / `datachannel` / `unknown`
  - code の意味: `1000` は正常終了、`4490` は Sora から送られた値、`4999` はそれ以外の SDK 側の異常
- `on_disconnect` では code / reason のペアを主、`message` を補助情報として扱う。
- 実現には Sora C++ SDK 側で close code / reason / type を observer へ渡す対応が必要になる。C++ SDK も合わせて変更できるかを確認する。

## 完了条件

- `DisconnectCode` で切断コードを扱える。
- `on_disconnect` で code / reason / type を取得できる。
- C++ SDK レイヤーの `(error_code, message)` と共通 SDK レイヤーの `(type, code, reason)` の両方を取得できる。
- `tests/` に code / reason / type を確認するテストがある。
- 利用方法が README または docstring に記載されている。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- Sora C++ SDK 側で close code / reason / type を observer へ渡す対応が必要で、期待する挙動をすり合わせる必要がある。
- `SoraSignalingErrorCode` のリネームを後方互換にするか、破壊的変更にするか。
- `type` の `unknown` が何を指すかを含めた code / reason / type の確定。
- `on_disconnect` の引数の形 (タプルにするか、専用の型を追加するか)。

再開するときは reopened にしてから実装を進める。
