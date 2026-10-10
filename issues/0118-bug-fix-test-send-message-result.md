# E2E テストの `send_message()` が送信失敗を検知できない問題を修正する

- Created: 2026-10-10
- Completed: -
- Branch: feature/fix-test-send-message-result
- Polished: {YYYY-MM-DD}

## 目的

`tests/client.py` の `SoraClient.send_message()` は `send_data_channel()` の戻り値を捨てているため、ラベルが開いていない・offer に含まれないなどの理由で送信に失敗してもテストがそのまま進み、後続の受信待ちのタイムアウトとして失敗する。失敗の原因が送信側にあることが分からず、調査に時間がかかる。

## 現状

- `send_message()` は `self._connection.send_data_channel(label, data)` の戻り値を確認していない
- 待機は `self._data_channel_ready_events[label].wait(timeout=timeout)` で行っており、ラベルが offer に含まれない場合は `KeyError` になる
- `SoraClient` には `_wait_data_channel_ready()` (ラベルが無い場合は待たずに `False` を返す) があるが、`send_message()` は使っていない
- 同じ `SoraClient` の `send_rpc()` は `wait_rpc_ready()` で前提を確認し、送信できなかった場合は `False` を返す設計になっている
- `send_data_channel()` は Sora が管理するラベルと offer に含まれないラベル、開いていないラベルへ送信せず `False` を返す
- `send_message()` には「direction が sendrecv / sendonly の時しか送れず、例外をあげるようにする」という TODO コメントがある

## 設計方針

- `send_message()` の戻り値を確認し、`False` の場合は `AssertionError` にしてテストを失敗させる
- ラベルが `_data_channel_ready_events` に無い場合の扱いを決める。`_wait_data_channel_ready()` を使うか `KeyError` のままにするかを選び、判断理由をコメントに残す
- 既存の呼び出し元 (`tests/test_messaging.py` / `tests/test_messaging_header.py` など) の挙動が変わらないようにする
- TODO コメントの `direction` の検証はこの issue の範囲外とし、必要なら別 issue にする

## 完了条件

- `send_message()` が送信できなかった場合にテストを失敗させること
- 既存のテストがすべて通ること

## 変更対象

- `tests/client.py`
