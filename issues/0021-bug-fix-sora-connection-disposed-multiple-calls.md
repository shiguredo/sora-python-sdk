# SoraConnection のデストラクタで Disposed() が複数回呼ばれている問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-sora-connection-disposed-multiple-calls

## 目的

`SoraConnection::~SoraConnection()` 内で `Disposed()` が連続して呼ばれており、 `Disconnect()` 経由のものも含めると最大 3 回まで呼ばれてしまう。
`Disposed()` の冪等性が暗黙の前提となっており、将来的な変更で副作用が増えた場合に二重解放や二重通知が発生するリスクがある。
呼び出し順序を整理し、 `DisposePublisher::Disposed()` の冪等性も明示的に担保することで、リソース管理の安全性を高める。

## 優先度根拠

Medium とする。

- 現状の実装でも `Disposed()` が偶然冪等に動作しているため、ただちに観測可能な不具合は起きていない。
- 一方で、デストラクタという最も誤りが許容されないパスで「同じ後始末関数が無条件に複数回呼ばれている」状態は、将来のリファクタリングで容易にクラッシュや二重解放を招く構造的危険を抱えており、放置はできない。
- リソース解放経路の正しさは SDK 全体の安定性に直結するため、優先的に対応する必要がある。

## 現状

`src/sora_connection.cpp` の 35-42 行 (デストラクタ):

```cpp
SoraConnection::~SoraConnection() {
  Disconnect();
  Disposed();
  if (publisher_) {
    publisher_->RemoveSubscriber(this);
  }
  Disposed();
}
```

`Disconnect()` の内部 (`src/sora_connection.cpp` 74-89 行):

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

呼び出し経路:

1. `Disconnect()` の冒頭で `Disposed()` が 1 回呼ばれる (`conn_` が存在する場合)。
2. デストラクタ本体で `Disposed()` が 1 回呼ばれる。
3. `publisher_->RemoveSubscriber(this)` の後で `Disposed()` がもう 1 回呼ばれる。

通常の破棄経路では `Disposed()` が最大 3 回連続で呼ばれることになり、 `video_source_->RemoveSubscriber(this)` や `audio_source_->RemoveSubscriber(this)` の呼び出しも複数回試行される (2 回目以降は `nullptr` チェックで弾かれる) 構造になっている。

`DisposePublisher::Disposed()` 自体には冪等性を保証する明示的なフラグが無く、 `SoraConnection::Disposed()` のローカルな `nullptr` チェックに依存している。

## 設計方針

- デストラクタからの `Disposed()` 呼び出しは 1 回だけにする。具体的には、 `Disconnect()` 内で既に `Disposed()` を呼んでいるなら、デストラクタ本体の 1 回目の `Disposed()` を削除する。 `publisher_->RemoveSubscriber(this)` の後の `Disposed()` についても、本来 `RemoveSubscriber` 経由で `PublisherDisposed` 経路が走らない通常終了パスでは不要であるため、整理する。
- 加えて、 `DisposePublisher::Disposed()` 側に「2 回目以降は何もしない」というガード (例: `disposed_` フラグ) を明示的に置き、 `SoraConnection::Disposed()` を含む派生クラスでも安全に多重呼び出しに耐えられる構造にする。
- 修正後も、現状の正しい振る舞い (購読者への通知が確実に 1 度行われること、 `video_source_` / `audio_source_` の登録解除が確実に行われること) を変えないこと。

## 完了条件

- `SoraConnection` の通常破棄経路で `Disposed()` が 1 回だけ呼ばれることを、コードレビューおよび手動トレースで確認できる。
- `DisposePublisher::Disposed()` および派生クラスの `Disposed()` が、複数回呼ばれても副作用なく無視されることが、実装と簡単なユニットテストで確認できる。
- 既存テスト ( `tests/` 配下) が全て通り、リソースリークやクラッシュが発生しないこと。
