# `SoraConnection::SendDataChannel` / `GetStats` で `conn_` の null チェックが欠落し disconnect 後の呼び出しで SEGV する問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-send-data-channel-get-stats-no-null-check

## 目的

`SoraConnection::Disconnect()` は内部状態を片付けた後 `conn_ = nullptr` で終わる。にもかかわらず、`SoraConnection::SendDataChannel` と `SoraConnection::GetStats` の 2 つだけが `conn_` の null チェック無しで `conn_->...` を呼び出している。Python 側で `disconnect()` 後にうっかりこれらを呼んでしまうと、SDK 内部で nullptr dereference して SEGV する。

`SoraConnection::Connect()` は同じ条件で `std::runtime_error` を投げて Python 例外に変換できる仕組みを持っているのに、`SendDataChannel` / `GetStats` だけが死角になっている。他の API (`SetAudioTrack` 等) は `audio_sender_` / `video_sender_` のガードで救われているが、これら 2 つはガードしているメンバそのものが `conn_` なので、`conn_ == nullptr` で即死する。

SDK ユーザーがクラッシュではなく Python 例外として扱える状態に揃える。

## 優先度根拠

Medium とする。

- Python レイヤから C++ レイヤを SEGV させる経路であり、SDK としては避けたいクラスの欠陥。ただし「ユーザーが `disconnect()` 後に意図的に呼ぶ」ことが前提なので、踏みやすさは中程度。High ではない。
- 修正は数行 (`if (conn_ == nullptr) throw std::runtime_error(...);`) で済む。対費用効果が非常に高い。
- `Connect()` は既に同等のチェックを持っているため、対称性を取るだけでよい。レビュー上の判断材料も明確。「他の入口は守っているのに、この 2 つだけ守っていない」状態は broken windows で、放置すると将来似た API を追加するときも同様にガード忘れが起きる。

## 現状

### `SendDataChannel`

`src/sora_connection.cpp:139-142`:

```cpp
bool SoraConnection::SendDataChannel(const std::string& label,
                                     nb::bytes& data) {
  return conn_->SendDataChannel(label, std::string(data.c_str(), data.size()));
}
```

`conn_` を null チェックせず即時参照。

### `GetStats`

`src/sora_connection.cpp:144-158`:

```cpp
std::string SoraConnection::GetStats() {
  auto pc = conn_->GetPeerConnection();
  if (pc == nullptr) {
    return "[]";
  }
  // ...
}
```

`conn_->GetPeerConnection()` の前に `conn_` の null チェックが無い。`pc` の null チェックはしているが、`conn_` 自体が nullptr ならその前段で落ちる。

### 対照的に `Connect` はガード済み

`src/sora_connection.cpp:64-72`:

```cpp
void SoraConnection::Connect() {
  if (conn_ == nullptr) {
    throw std::runtime_error(
        "Already disconnected. Please create another Sora instance to "
        "establish a new connection.");
  }
  conn_->Connect();
}
```

これと同じ規約を `SendDataChannel` / `GetStats` にも適用する必要がある。

### `Disconnect` で `conn_ = nullptr` が起きる経路

`src/sora_connection.cpp:74-89`:

```cpp
void SoraConnection::Disconnect() {
  if (conn_) {
    // ...
    audio_sender_ = nullptr;
    video_sender_ = nullptr;
    conn_ = nullptr;
  }
}
```

つまり `disconnect()` を 1 度呼んだ後の `connection` インスタンスに対して、`send_data_channel()` / `get_stats()` を呼んだ瞬間に SEGV 確定。

## 設計方針

`SendDataChannel` と `GetStats` の冒頭に、`Connect()` と同じ形の null チェックを追加する。

```cpp
bool SoraConnection::SendDataChannel(const std::string& label,
                                     nb::bytes& data) {
  if (conn_ == nullptr) {
    throw std::runtime_error("connection is disconnected");
  }
  return conn_->SendDataChannel(label, std::string(data.c_str(), data.size()));
}

std::string SoraConnection::GetStats() {
  if (conn_ == nullptr) {
    throw std::runtime_error("connection is disconnected");
  }
  auto pc = conn_->GetPeerConnection();
  // ...
}
```

エラーメッセージは `Connect()` の文言と整合させる。日本語ではなく英語 (ログメッセージは英語規約) を維持する。

テスト方針:

- 既存テスト群を変えず、`disconnect()` 後の `send_data_channel()` / `get_stats()` 呼び出しが SEGV ではなく Python 例外として観測されるテストを追加する。

## 完了条件

- `disconnect()` 後の `send_data_channel()` 呼び出しが SEGV ではなく Python 例外 (`RuntimeError`) として観測されること。
- `disconnect()` 後の `get_stats()` 呼び出しが SEGV ではなく Python 例外 (`RuntimeError`) として観測されること。
- 既存の正常系動作 (connect 中の `send_data_channel` / `get_stats`) が変わらないこと。
- 同種の経路 (`SetAudioTrack` 等) で `conn_` を触る箇所がないかをレビューし、必要なら追加でガードすること。
