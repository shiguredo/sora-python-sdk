# `SoraConnection` の `conn_ == nullptr` ガードを 1 箇所に集約する

- Created: 2026-10-10
- Completed: -
- Branch: feature/refactor-sora-connection-guard
- Polished: {YYYY-MM-DD}

## 目的

`SoraConnection` の各公開メソッドに同じ `conn_ == nullptr` ガードと例外メッセージが複製されており、条件やメッセージを変更するときに全箇所を直す必要がある。1 箇所に集約して保守性を上げる。

## 現状

- `src/sora_connection.cpp` に同一のガード (同じ `std::runtime_error` のメッセージ) が 4 箇所ある
  - `Connect()`
  - `SendDataChannel()`
  - `SendRpc()`
  - `GetStats()`
- `GetStats()` はガードに加えて `pc` の null チェックも行っている
- `Disconnect()` は `conn_ == nullptr` を「未接続」として別の扱いをするため対象外とする
- 複製されているため、ガードの追加漏れ (新しいメソッドで忘れる) が起きやすい

## 設計方針

- private メソッド (例: `EnsureConnected()`) にガードを集約し、各公開メソッドの先頭で呼ぶ
- 例外の型とメッセージは現状と同一にする (挙動を変えない)
- `GetStats()` の `pc` の null チェックは集約の対象外とし、現状の位置を維持する
- 挙動が変わらないためテストの追加は不要だが、`disconnect()` 後の呼び出しが `RuntimeError` になることを既存テストで確認する

## 完了条件

- `conn_ == nullptr` のガードと例外メッセージが 1 箇所になっていること
- 4 つのメソッドの挙動と例外メッセージが変わらないこと
- 既存のテストがすべて通ること

## 変更対象

- `src/sora_connection.h` / `src/sora_connection.cpp`
