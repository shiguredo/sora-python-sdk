# WebSocket シグナリング接続時にヘッダーを指定できるようにする

- Created: 2026-09-11
- Completed: -
- Branch: feature/add-ws-headers
- Polished: -
- Reporter: @voluntas

## 目的

Sora はシグナリング接続時の HTTP ヘッダーをウェブフックやログに追加する仕組みを持つ。これをテストできるように、`Sora.create_connection()` で WebSocket シグナリングの HTTP ヘッダーを任意に指定できるようにする。

## 現状

- `Sora.create_connection()` には WebSocket の HTTP ヘッダーを任意に指定する引数が無い (`src/sora_sdk/sora_sdk_ext.pyi`)。
- 指定できるのは `user_agent` のみ。`user_agent` は `sora::SoraSignalingConfig::user_agent` として C++ SDK に渡され、`Websocket::SetUserAgent()` が `User-Agent` ヘッダーに設定する。
- Sora C++ SDK の `sora::SoraSignalingConfig` には任意のヘッダーを渡すフィールドが無い (`_install/<platform>/sora/include/sora/sora_signaling.h`)。`sora::Websocket` も `SetUserAgent()` しか持たず、`set_headers` ラムダは `User-Agent` のみを設定する。
- そのため Python SDK だけで任意ヘッダーを送ることはできない。

## 設計方針

保留を解除したら、まず Sora C++ SDK に WebSocket の HTTP ヘッダーを渡す口を追加できるか確認する。

- Sora C++ SDK 側に `SoraSignalingConfig::ws_headers` (例: `std::vector<std::pair<std::string, std::string>>`) を追加し、`sora::Websocket` の `set_headers` で `User-Agent` と合わせて設定する。
- Python SDK 側は `create_connection()` に `ws_headers: dict[str, str]` を追加し、C++ SDK のフィールドへ渡す。既存の `user_agent` は残し、後方互換を保つ。
- ヘッダー名が重複したときや `User-Agent` と競合したときの扱い (上書きするか、エラーにするか) を決める。

## 完了条件

- `Sora.create_connection(ws_headers={"key1": "value1", "key2": "value2"})` のようにヘッダーを指定できる。
- 指定したヘッダーがシグナリング接続の HTTP ヘッダーに含まれることを確認できる。
- 既存の `user_agent` 指定が引き続き動作する。
- `tests/` にヘッダー指定を確認するテストがある。
- 利用方法が README または docstring に記載されている。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- Sora C++ SDK に任意ヘッダーを渡すフィールドが無く、C++ SDK 側の対応が必要。その実現方法と時期が未定。
- C++ SDK に追加する型と、Python の `dict[str, str]` からの変換方法。
- `User-Agent` と任意ヘッダーが競合したときの扱い。
- ヘッダーに指定できる値の制約 (改行の禁止など) と検証方法。

再開するときは reopened にしてから実装を進める。
