# SoraConnection::Disconnect の condition_variable wait を有限タイムアウトに変更し永久ブロックを防ぐ

- Priority: Medium
- Created: 2026-06-23
- Completed: 2026-07-27
- Model: Opus 4.7
- Branch: feature/fix-disconnect-no-timeout

## 目的

`src/sora_connection.cpp` の `SoraConnection::Disconnect` は、`conn_->Disconnect()` を呼んだ後で `on_disconnect_cv_.wait(lock, ...)` により `OnDisconnect` コールバックの到着を待つ。この `wait` にはタイムアウトが設定されていないため、`OnDisconnect` が来ないケース (例: `io_context` の例外停止、シグナリング相手の応答喪失、内部スレッドのデッドロックなど) では Python プロセスが永久にブロックされ、`Ctrl+C` でも `SIGINT` でも抜けられなくなる。本 issue では `wait_for` で有限タイムアウトを設定し、加えて Python の `KeyboardInterrupt` 系シグナルで break できる経路を作って、ハング状態でもユーザがプロセスを安全に終了できるようにする。

## 優先度根拠

Medium とする。

- 永久ブロックは「Ctrl+C で止まらない」というユーザ体験上もっとも嫌われるクラスの障害で、サンプルアプリ・テスト・本番運用すべてで「とりあえず `kill -9`」が常態化するきっかけになる。
- 一方、再現頻度は通常低く、`OnDisconnect` が来ない経路は libwebrtc 側の異常ケースで限定的である。
- 修正自体は `wait_for` への置き換えと `PyErr_CheckSignals` の組み合わせで実装でき、リスクは中程度。タイムアウト値の妥当性検証だけ慎重に行う必要がある。

## 現状

`src/sora_connection.cpp` の `Disconnect` は以下の通り。

```cpp
void SoraConnection::Disconnect() {
  if (conn_) {
    Disposed();
    conn_->Disconnect();
    // OnDisconnect が来るまで待つ
    {
      GILLock lock;
      on_disconnect_cv_.wait(lock,
                             [this]() -> bool { return on_disconnected_; });
    }
    // Connection から生成したものは、ここで消す
    audio_sender_ = nullptr;
    video_sender_ = nullptr;
    conn_ = nullptr;
  }
}
```

- `std::condition_variable::wait` はタイムアウト無しのオーバーロードを使っており、`on_disconnected_` が `true` になるまで永久に待つ。
- `OnDisconnect` を呼ぶのは libwebrtc 側のシグナリングスレッドで、`io_context` の例外停止やスレッドの停止に伴ってコールバック自体が呼ばれない経路がある。この場合 `on_disconnected_` は永遠に `false` のままになる。
- `wait` 中は GIL を `GILLock` で握り直しているとはいえ、Python の `KeyboardInterrupt` を起点としたシグナルチェックを能動的に行う仕組みがないため、`Ctrl+C` を押しても `wait` が抜けない。
- `Disconnect` は Python の `with sora.create_connection(...) as conn:` の終了処理など、ユーザコードから同期的に呼ばれる経路がある。永久ブロックはユーザ側からの中断手段を全て封じる。

## 設計方針

実装時は以下のうち実態に合うものを選定する (本 issue では断定しない)。

1. `wait` を `wait_for(lock, std::chrono::seconds(N), [this](){ return on_disconnected_; })` に置き換え、たとえば `N = 10` 秒のような有限タイムアウトを設定する。タイムアウトに到達した場合は `RTC_LOG(LS_ERROR)` を出してから後続のクリーンアップに進む。
2. 短い間隔 (例: 100ms) で `wait_for` をループし、各ループで `gil_scoped_acquire` + `PyErr_CheckSignals()` を呼んで `KeyboardInterrupt` 等の Python シグナルを取り込めるようにする。シグナルが立っていたら早期 break する。
3. 上記 1 と 2 を組み合わせ「短い `wait_for` を最大 N 秒分ループする」構成にする。

タイムアウト値はサンプル・テストで `OnDisconnect` 到着までに通常かかる時間を計測し、その 10 倍程度を上限にするのが安全。タイムアウトに到達した場合でも `audio_sender_ = nullptr;` 以降のクリーンアップは必ず実行する。

`Disposed()` と `conn_->Disconnect()` の呼び出し順は維持する。`on_disconnect_cv_.notify_all()` を投げる側 (`OnDisconnect`) の挙動には手を入れない。

## 完了条件

- `OnDisconnect` が来ない異常ケースでも `Disconnect` が有限時間で抜け、Python プロセスが終了可能になること。
- `Ctrl+C` (`KeyboardInterrupt`) を Disconnect 待ち中に押した場合に、`Disconnect` から脱出できること (シグナル経路を採用した場合)。
- 正常系での `Disconnect` の挙動 (応答到着で即 return する) が従来と変わらないこと。
- タイムアウトで抜けた場合に `RTC_LOG(LS_ERROR)` などで「OnDisconnect が来なかった」事実がログに残ること。
- 既存の e2e テスト・ユニットテストが引き続き通ること。

## 解決方法

`Disconnect` の `on_disconnect_cv_.wait` を、最大 10 秒・100ms 間隔の `wait_for` ループに置き換えた。

- 各周回で `PyErr_CheckSignals` を呼び、待ち中の `KeyboardInterrupt` でも抜けられるようにした
- タイムアウト時は `RTC_LOG(LS_ERROR)` で `OnDisconnect` 未到着を記録し、その後も `audio_sender_` / `video_sender_` / `conn_` のクリーンアップは必ず実行する
- シグナルで抜けた場合はクリーンアップ後に `nb::python_error` を投げる

追加したテスト:

- `tests/test_disconnect_timeout.py`
  - 正常系の `disconnect()` が数秒以内に戻ることを検証する（異常経路はモック禁止のためコード上の有限 wait で担保）

変更履歴は `CHANGES.md` の `## develop` に `[FIX]` として追記した。
