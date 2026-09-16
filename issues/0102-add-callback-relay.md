# コールバックの Python 中継を GIL 非依存で実装する

- Created: 2026-09-16
- Completed: -
- Branch: feature/add-callback-relay
- Polished: {YYYY-MM-DD}

## 目的

sora-rust-sdk のコールバックから Python の callable を呼ぶ経路を、GIL 取得で上流をブロックしない形で実装し、free-threading 宣言の前提を成立させる。

## 現状

- 現行の `SoraConnection` は 11 種のコールバックを持つ。`on_set_offer` / `on_ws_close` / `on_disconnect` / `on_signaling_message` / `on_notify` / `on_push` / `on_message` / `on_rpc` / `on_switched` / `on_track` / `on_data_channel` である。
- 現行は `src/sora_connection.cpp` が `webrtc::scoped_refptr` と `gil_scoped_acquire` で Python callable を呼ぶ。`src/gil.h` が GIL の取得をまとめている。
- sora-rust-sdk の `SoraConnectionEventHandler` は `Send` のみを要求し、コールバックは単一タスクから直列に呼ばれる。ブロックさせることは禁止されており、重い処理は自前のタスクへ転送する必要がある。
- 上流のコールバックは Rust / tokio のスレッド上で呼ばれる。Python callable を直接呼ぶと GIL 取得で上流をブロックしうる。
- `SoraConnectionEventHandler` に `on_disconnect` / `on_set_offer` / `on_rpc` の受け口が無い。`on_switched` は引数を取らない。

## 設計方針

- `docs/migration-to-sora-rust-sdk.md` の決定事項 13 と 14 に従う。
- Rust 側のコールバックはキューへ push して即座に戻る。キューは上流のコールバックをブロックさせない。
- Python 側は専用スレッドがキューから取り出して callable を呼ぶ。上流が単一タスクから直列に呼ぶため、キューで順序が保存される。
- `#[pymodule(gil_used = false)]` を宣言する。フレーム受け渡しは numpy 配列の生成時にのみ GIL を取る。
- 解放の順序を明確にする。キューと専用スレッドは接続の終了時に停止し、残った通知を捨てる。Python の終了時にスレッドが残らないようにする。
- `on_disconnect` / `on_set_offer` / `on_rpc` / `on_switched` の引数は上流の依頼 (A / B / C / D) が受理されるまで実装できない。本 issue では中継の仕組みを作り、受理された時点で接続する。

## 完了条件

- Rust 側のコールバックから Python callable が呼ばれること。
- コールバックから戻るまでに上流をブロックしないこと (キューへの push のみで戻ること)。
- 通知の順序が上流の呼び出し順と一致すること。
- 接続の終了後に専用スレッドが残らないこと。
- free-threading ビルド (`python3.14t`) で `import sora_sdk` とコールバックの中継が動作すること。

## 依存

- 先行: ビルド基盤を maturin へ置き換える issue。
- 上流: sora-rust-sdk への切断結果 (A)、受信 offer (B)、受信 RPC (C)、切替内容 (D) の追加依頼。受理されるまで該当のコールバックは接続できない。
- 後続: 接続設定の issue が本 issue に依存する。

## 解決方法
