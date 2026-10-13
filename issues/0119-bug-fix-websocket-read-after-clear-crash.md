# 接続の切断後に WebSocket のデータを受信すると、同梱している Sora C++ SDK がクラッシュしてプロセスが落ちる

- Created: 2026-10-13
- Completed: -
- Branch: feature/fix-websocket-read-after-clear-crash
- Polished: {YYYY-MM-DD}

## 目的

`sora-python-sdk` を使うアプリケーションが、クラスターのノードが一時的に停止して復帰するような状況でプロセスごと落ちるのを防ぐ。

`Fatal Python error: Segmentation fault` で終了コード 139 になり、Python 側では回避できない。

## 現状

### 発生事象

接続の切断処理の後に WebSocket のデータを受信すると、`io_context` のスレッドで SIGSEGV になる。

wheel に含まれる `sora_sdk_ext` のシンボルから、次が分かっている (demangle 済み、外側から内側へ)。

```text
boost::asio::detail::scheduler::run(boost::system::error_code&)
boost::asio::detail::reactive_socket_recv_op<...>
boost::beast::websocket::stream<...>
sora::Websocket::OnRead(...)
sora::SoraSignaling::DoRead()
sora::Websocket::Read(...)
boost::asio::post(boost::asio::strand<...>, ...)
```

### 再現手順

3 ノードのクラスターを用意する。

1. 配信者を 1 台目のノードに接続する
2. 視聴者を 2 台目と 3 台目のノードに接続し、両方に映像が届くことを確認する
3. 3 台目のノードのプロセスを、`net_ticktime` より長い時間 (例: 35 秒) SIGSTOP する
4. 3 台目のノードの視聴者の接続が ICE の失敗で切れるのを待つ
5. SIGCONT でノードを復帰させる

復帰の直後にクライアントが SIGSEGV する。2 回試して 2 回とも再現した。
`sora` リポジトリの `e2e-test/test_cluster_hung_node_recovery.py` でも同じ手順で 3 回連続して再現している。

`2026.2.0.dev1` (Sora C++ SDK `2026.3.0-canary.7`) と `2026.2.0.dev2` (Sora C++ SDK `2026.3.0-canary.8`) の両方で発生する。このリポジトリのコードではなく、同梱している Sora C++ SDK の中のライフタイムの問題である。

### 原因

同梱している Sora C++ SDK の `src/sora_signaling.cpp` の `SoraSignaling::OnRead` は、エラーの無い read 完了で `state_ != State::Connected` の場合も `DoRead()` を呼ぶ。

一方 `SoraSignaling::Clear()` は `ws_ = nullptr` と `state_ = State::Closed` を行う。`Clear()` は `SoraSignaling::SendOnDisconnect` が `io_context` に post するラムダから呼ばれるため、既にキューに入っている read 完了より先に実行されうる。

したがって、次の順序で `ws_` が null のまま `DoRead()` が走る。

1. 相手ノードの一時停止で ICE が失敗し、`SendOnDisconnect` から `Clear()` が呼ばれて `ws_ = nullptr`、`state_ = State::Closed` になる
2. 一時停止していたノードが復帰し、バッファしていたデータを送る
3. 保留されていた read が成功として完了し、`SoraSignaling::OnRead` が `state_ != State::Connected` の分岐で `DoRead()` を呼ぶ
4. `SoraSignaling::DoRead()` が null の `ws_` を `operator->` で参照し、`Websocket::Read` の `boost::asio::post(strand_, ...)` で落ちる

## 設計方針

- このリポジトリ側のコード変更ではなく、Sora C++ SDK の修正を取り込んだバージョンに上げる
- 修正は `sora-cpp-sdk` の issue で扱う。`SoraSignaling::OnRead` の `state_ != State::Connected` の分岐で read を再開しないことと、`SoraSignaling::DoRead()` が `ws_` を参照する前に確認することが必要
- 修正版の Sora C++ SDK がリリースされたら `DEPS` の `SORA_CPP_SDK_VERSION` を上げ、再現手順で落ちないことを確認する

## 完了条件

- 上記の再現手順でクライアントのプロセスが落ちないこと
- `sora` リポジトリの `e2e-test/test_cluster_hung_node_recovery.py` が成功すること
- 既存の E2E テストが通ること

## 関連 issue

- `sora-cpp-sdk` リポジトリの `issues/0113-bug-fix-signaling-read-after-clear-crash.md`: 原因そのものの修正
- `sora` リポジトリの `issues/0479-bug-fix-hung-node-recovery-session-destroy.md`: このクラッシュに先立って発生するセッション破棄の問題 (別リポジトリ)

## 解決方法

（実装時に記入）
