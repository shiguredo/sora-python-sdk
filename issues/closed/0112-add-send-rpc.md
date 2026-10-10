# `SoraConnection` に `send_rpc()` を追加して `rpc` ラベルへ JSON-RPC 2.0 リクエストを送れるようにする

- Created: 2026-10-10
- Completed: 2026-10-10
- Branch: feature/add-send-rpc
- Polished: 2026-10-10
- Reporter: @voluntas

## 目的

Sora C++ SDK `2026.3.0-canary.8` で `SoraSignaling::SendDataChannel()` の送信先がユーザー定義ラベル (`#` で始まるラベル) に制限され、Sora が管理するラベル (`signaling` / `stats` / `notify` / `push` / `rpc`) と offer に含まれないラベルへは送信せず `false` を返すようになった。同じ変更で JSON-RPC 2.0 のリクエストを `rpc` ラベルへ送る `SoraSignaling::SendRpc()` が追加された (sora-cpp-sdk の issue 0107)。

sora-python-sdk は `SendRpc()` を公開していないため、Python から `rpc` ラベルへリクエストを送る手段が無く、Sora の RPC 機能 (JSON-RPC 2.0 over DataChannel) を利用できない。`send_rpc()` を追加し、既存の `on_rpc` での応答受信と組み合わせて Python から RPC を利用できるようにする。

根拠: RPC を利用するアプリケーションは `send_data_channel("rpc", ...)` でリクエストを送っていたが、canary.8 以降この呼び出しは送信されずに `false` を返すため、応答が来ずにタイムアウトする。SDK が `send_rpc()` を提供しない限りアプリケーション側だけでは修正できない。

## 現状

- `src/sora_sdk_ext.cpp` の `SoraConnection` バインディングは `send_data_channel()` と `on_rpc` を公開しているが `send_rpc()` は無い
- `src/sora_connection.h` / `src/sora_connection.cpp` の `SoraConnection` にも `SendRpc()` は無い。`SendDataChannel()` は `conn_->SendDataChannel(label, data)` に委譲して戻り値を返し、`conn_ == nullptr` の場合は `RuntimeError` を送出する
- `_install/<platform>/sora/include/sora/sora_signaling.h` (`2026.3.0-canary.8`) の `SoraSignaling::SendRpc()` の仕様は次のとおり
  - `{"jsonrpc":"2.0","id":<id>,"method":<method>,"params":<params>}` を組み立てて `rpc` ラベルで送信し、送信できた場合に `true` を返す
  - `id` は `std::optional<uint64_t>`。`std::nullopt` の場合は `id` を含めず、JSON-RPC 2.0 の Notification になる (Sora は応答を返さない)
  - `params` は `std::optional<boost::json::value>`。`std::nullopt` の場合は `params` を含めない。Object でも Array でもない値の場合は送信せず `false` を返す
  - `rpc` ラベルが開いていない場合 (RPC が無効な Sora、未接続) は送信せず `false` を返す
  - 応答は `SoraSignalingObserver::OnRpc()` に JSON 文字列で通知される。Python では `on_rpc` が `bytes` として受け取る
- `rpc` ラベルのメッセージは C++ SDK が `OnRpc()` にのみ通知するため、`on_message` は `rpc` ラベルでは呼ばれない
- `src/sora.cpp` の `Sora::ConvertJsonValue()` が Python の値 (`None` / `bool` / `int` / `float` / `str` / `list` / `dict`) を `boost::json::value` へ変換している。ただし `Sora` の private メソッドであり `SoraConnection` からは利用できない
- `Sora::ConvertJsonValue()` は `None` を `boost::json::value(nullptr)` に変換する。JSON-RPC 2.0 の「`params` を含めない」とは意味が異なる
- sora-python-sdk の `send_data_channel()` は canary.8 以降、Sora 管理ラベルへ送信すると `false` を返す

## 設計方針

- `SoraConnection` に `SendRpc()` を追加し、`conn_->SendRpc()` へ委譲する。戻り値は C++ SDK の結果をそのまま返す
- バインディングは `send_rpc(id, method, params)` とする。引数名は C++ SDK に合わせて `id` / `method` / `params` とし、生成される `sora_sdk_ext.pyi` に `arg0` を出さない (issue 0077 と同じ方針)
- `id` の型は C++ SDK に合わせて `std::optional<uint64_t>` とし、`None` または 0 以上 2^64-1 以下の整数だけを受け付ける。C++ SDK の引数型が `uint64_t` のため文字列 id は指定できない
- `id` の採番と応答の突き合わせ、タイムアウト、JSON-RPC のエラー応答の解釈はアプリケーションの責務とし、SDK では行わない (C++ SDK と同じ)
- `params` の変換規則は既存の `Sora::ConvertJsonValue()` と同一にし、新しい変換規則を持ち込まない
- `params` の変換失敗時の例外型も既存の `Sora::ConvertJsonValue()` の挙動を変えない。`int64` の範囲を超える整数とキーが文字列でない `dict` は `nb::cast_error` に由来する `RuntimeError`、JSON の値として扱えない型は `nb::type_error` (`TypeError`) になる。例外型の整理はこの issue の範囲外とする
- `params=None` は `std::nullopt` を渡して `params` を含めない。`ConvertJsonValue(None)` の `null` は使わない
- `params` の変換処理を `Sora::ConvertJsonValue()` と重複させない。変換処理を共通ヘルパー (例: `src/sora_json.h` / `src/sora_json.cpp` の free 関数) へ切り出し、`Sora` と `SoraConnection` の両方から使う。`.cpp` を追加する場合は `CMakeLists.txt` のソース一覧も更新する。既存の `Sora::ConvertJsonValue()` の呼び出し側から見た挙動 (変換結果と `nb::type_error` のメッセージ) は変えない
- `disconnect()` 後 (`conn_ == nullptr`) は `send_data_channel()` と同じ `RuntimeError` にして SEGV させない
- `on_rpc` のシグネチャ (`bytes`) と挙動は変更しない

## 完了条件

- `send_rpc()` が `{"jsonrpc":"2.0","id":<id>,"method":<method>,"params":<params>}` を `rpc` ラベルで送信し、送信できた場合に `True` を返すこと
- `id=None` の場合に `id` を含めないリクエストが送信されること
- `params=None` の場合に `params` を含めないリクエストが送信されること
- `params` が Object でも Array でもない値に変換される場合 (文字列・`int64` の範囲内の整数・浮動小数点数・真偽値) に送信せず `False` を返すこと
- `params` が JSON の値として扱えない型 (`set` / `tuple` / `bytes` / 変換対象外のオブジェクトなど) の場合に `TypeError` (`nb::type_error`) になること
- `params` の `int64` の範囲を超える整数と、キーが文字列でない `dict` は、既存の `Sora::ConvertJsonValue()` と同じ `nb::cast_error` に由来する `RuntimeError` になること
- `id` が `None` でも 0 以上 2^64-1 以下の整数でもない場合に `TypeError` になること
- `rpc` ラベルが開いていない場合 (未接続・RPC が無効な Sora) に `False` を返し、送信しないこと
- `disconnect()` 後に呼んだ場合に `RuntimeError` になり SEGV しないこと
- RPC が有効な Sora に接続した場合、送信したリクエストの応答が `on_rpc` に届き、`id` が一致すること
- 生成される `sora_sdk_ext.pyi` の `send_rpc` が `id` / `method` / `params` の引数名で出力されること
- 既存のテストに回帰が無いこと
- `skills/sora-python-sdk/SKILL.md` に次の内容が記載されていること
  - `send_rpc()` の使い方 (引数、`on_rpc` での応答受信、id と応答の突き合わせはアプリケーションの責務であること)
  - `rpc` ラベルへは `send_data_channel()` ではなく `send_rpc()` を使うこと
  - `send_data_channel()` が送信できるのは `#` で始まるユーザー定義ラベルだけで、Sora が管理するラベルと offer に含まれないラベルへは送信せず `false` を返すこと
- `CHANGES.md` の `## develop` に `[ADD]` エントリが追記されていること

## テスト方針

- `tests/test_rpc.py` を追加する。既存のテストと同じく実際の Sora に接続する (モックやスタブは利用しない)
- `tests/client.py` の `SoraClient` に `on_rpc` の受信キューと `send_rpc()` ヘルパを追加する。`rpc` ラベルは offer の `data_channels` に含まれるため、既存の `_on_set_offer()` で `_data_channel_ready_events` に登録される
- `data_channel_signaling=True` / `audio=False` / `video=False` で接続し、`rpc` ラベルの準備完了を待ってから `send_rpc()` を呼ぶ
- `rpc` が有効な環境ではリクエストを送り、応答 (`result` または `error` を含む JSON) が同じ `id` で `on_rpc` に届くことを確認する。払い出される method に依存しない検証にするため、存在しない method を使ったエラー応答で確認してよい
- `id` を省略した Notification では応答が来ないことも確認する
- `rpc` ラベルが offer に含まれない環境では `send_rpc()` が `False` を返すことだけを確認する
- `disconnect()` 後の `RuntimeError` は `tests/test_send_data_channel_get_stats_after_disconnect.py` と同じ形式で確認する

## 変更対象

- `src/sora_connection.h` / `src/sora_connection.cpp` (`SendRpc()` の追加)
- `src/sora.h` / `src/sora.cpp` (JSON 変換処理の共通ヘルパーへの切り出し)
- `src/sora_json.h` / `src/sora_json.cpp` (共通ヘルパー) と `CMakeLists.txt`
- `src/sora_sdk_ext.cpp` (`send_rpc()` のバインディング)
- `tests/client.py` / `tests/test_rpc.py`
- `skills/sora-python-sdk/SKILL.md`
- `CHANGES.md`

## 解決方法

- `SoraConnection` に `SendRpc(std::optional<uint64_t> id, const std::string& method, const nb::handle& params)` を追加し、`conn_->SendRpc()` へ委譲するようにした
  - `conn_ == nullptr` の場合は `send_data_channel()` と同じ `RuntimeError` を送出する
  - `params` に `None` を指定した場合は `std::nullopt` を渡し、`params` を含めない
- `Sora::ConvertJsonValue()` を `src/sora_json.h` / `src/sora_json.cpp` の free 関数 `ConvertJsonValue()` へ切り出し、`Sora` と `SoraConnection` の両方から使えるようにした。`CMakeLists.txt` のソース一覧に `src/sora_json.cpp` を追加した。関数本体と例外型・メッセージは切り出し前と同一
- `src/sora_sdk_ext.cpp` に `send_rpc(id, method, params=None)` のバインディングを追加した。生成される `sora_sdk_ext.pyi` は `send_rpc(self, id: int | None, method: str, params: object | None = None) -> bool` になり `arg0` は出力されない
- `tests/client.py` の `SoraClient` に `on_rpc` の受信キュー、`send_rpc()`、`recv_rpc()`、`wait_rpc_ready()`、`_wait_data_channel_ready()` を追加した
- `tests/test_rpc.py` を追加した (6 件)
  - 応答が `on_rpc` に届き `id` が一致すること (`id` は境界値の 0 と 2^64-1 を含む)
  - `params` に `None` と Array を指定した場合、`params` を省略した 2 引数呼び出しでも送信できること
  - `id` に `None` を指定した Notification では応答が返らないこと
  - `params` が Object / Array 以外の値 (文字列・整数・浮動小数点数・真偽値) の場合は送信せず `False`、JSON の値として扱えない値 (`set` / `tuple` / `bytes` / float32 で厳密に表現できない浮動小数点数) は `TypeError`、`int64` の範囲を超える整数とキーが文字列でない `dict` は `RuntimeError` になること
  - `id` が `None` でも 0 以上 2^64-1 以下の整数でもない場合は `TypeError` になること
  - `rpc` ラベルが無い接続 (`data_channel_signaling=False`) では送信せず `False` を返すこと
  - `disconnect()` 後は `RuntimeError` になり SEGV しないこと
- `skills/sora-python-sdk/SKILL.md` に `Sora の RPC` の節を追加し、利用条件 (`sora.conf` の `data_channel_rpc`)、`send_rpc()` の引数、例外、`on_rpc` での応答受信を記載した。あわせて `send_data_channel()` の送信先の制限と注意点を追記した
- `CHANGES.md` の `## develop` に `[ADD]` エントリを追記した

### あわせて修正した既存テストの不備

テスト用の Sora が affinity により signaling の redirect を返すようになり、SDK が redirect 時に接続先の WebSocket を張り直して `OnWsClose(1000, "SELF-CLOSED")` を通知するため、`ws_close_code is None` を期待する `tests/test_type_switched.py` の 2 件が失敗していた (develop とその CI でも同じ 2 件が失敗)。`tests/client.py` の `SoraClient` で redirect による `SELF-CLOSED` を接続中の WebSocket のクローズとして記録しないようにし、`tests/test_type_switched.py` の docstring に前提を追記した。`CHANGES.md` の `### misc` にもエントリを追加した。

### 確認したこと

- `uv run pytest tests/ -n auto` が 82 passed / 98 skipped / 1 xfailed で通ること (実際の Sora に接続)
- `uv run pytest tests/test_rpc.py -q` が 6 件すべて通ること (約 8 秒)
- `uv run ruff check` / `uv run ruff format --check` / `uv run ty check` が通ること
- `uv run python run.py format` が差分を出さないこと (clang-format と ruff)
- 生成される `sora_sdk_ext.pyi` の `send_rpc` が `id` / `method` / `params` の引数名で出力されること
- 実際の Sora で `{"jsonrpc":"2.0","id":0,"method":"9999.0.0/not_exist","params":{"key":"value"}}` が送信され、`UNSUPPORTED-JSON-RPC-METHOD` のエラー応答が同じ `id` で `on_rpc` に届くこと
- `rpc` ラベルの準備完了は接続完了から 0.03〜0.07 秒で、`send_rpc()` の待機 (5 秒) に十分な余裕があること
- `git diff` の `ConvertJsonValue()` の本体が切り出し前と 1 バイト一致し、既存の呼び出し側の変換結果と例外が変わらないこと
