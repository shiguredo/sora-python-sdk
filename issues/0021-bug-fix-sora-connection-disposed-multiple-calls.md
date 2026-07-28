# SoraConnection のデストラクタで Disposed() が複数回呼ばれている問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-sora-connection-disposed-multiple-calls
- Polished: 2026-07-28

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

`Disconnect()` の内部 (`src/sora_connection.cpp` 74-122 行):

```cpp
void SoraConnection::Disconnect() {
  if (conn_) {
    Disposed();
    conn_->Disconnect();
    // OnDisconnect を有限時間待つ (10 秒タイムアウト付きポーリング)
    {
      constexpr auto kDisconnectTimeout = std::chrono::seconds(10);
      constexpr auto kPollInterval = std::chrono::milliseconds(100);
      const auto deadline =
          std::chrono::steady_clock::now() + kDisconnectTimeout;

      GILLock lock;
      while (!on_disconnected_) {
        // wait_for + PyErr_CheckSignals によるシグナル取り込み
        // ...
      }
    }
    audio_sender_ = nullptr;
    video_sender_ = nullptr;
    conn_ = nullptr;

    if (PyErr_Occurred()) {
      throw nb::python_error();
    }
  }
}
```

呼び出し経路:

1. `Disconnect()` の冒頭で `Disposed()` が 1 回呼ばれる (`conn_` が存在する場合)。
2. デストラクタ本体で `Disposed()` が 1 回呼ばれる。
3. `publisher_->RemoveSubscriber(this)` の後で `Disposed()` がもう 1 回呼ばれる。

通常の破棄経路では `Disposed()` が最大 3 回連続で呼ばれることになり、 `video_source_->RemoveSubscriber(this)` や `audio_source_->RemoveSubscriber(this)` の呼び出しも複数回試行される (2 回目以降は `nullptr` チェックで弾かれる) 構造になっている。

`DisposePublisher::Disposed()` 自体には冪等性を保証する明示的なフラグが無く、 `SoraConnection::Disposed()` のローカルな `nullptr` チェックに依存している。

### `conn_ == nullptr` 時の経路

`Disconnect()` は `if (conn_)` でガードされているため、以下のケースでは `Disposed()` を呼ばない:

- ユーザが明示的に `disconnect()` を呼んだ後のデストラクタ (この場合は既に `Disposed()` 済みなので問題なし)
- `Init()` を一度も呼ばずに破棄された場合

`Init()` 未呼び出しでも `SetAudioTrack()` / `SetVideoTrack()` は呼び出し可能であり、`audio_source_` / `video_source_` に SoraConnection が subscriber として登録される。この状態で `Disposed()` が一度も呼ばれなければ、SoraConnection は track の subscriber リストに残ったまま破棄され、track 側が後に `Disposed()` を呼んだ際に dangling pointer への `PublisherDisposed()` 呼び出しが発生する。

### デストラクタ内 throw の問題

`Disconnect()` は末尾で `throw nb::python_error()` しうる (`sora_connection.cpp:118-120`)。デストラクタから `Disconnect()` を呼んでいるため、スタックアンワインディング中に throw すると `std::terminate` になる。この問題は本 issue のスコープ外とし、別途 issue として扱う。

## 設計方針

- デストラクタ内の直接的な `Disposed()` 呼び出し (2 箇所) を削除し、`Disconnect()` 内の 1 回に集約する。ただし `conn_ == nullptr` 時 (Init 未呼び出し、または明示的 disconnect 後) は `Disconnect()` が `Disposed()` を呼ばないため、デストラクタに無条件の `Disposed()` を 1 回残す。最終的なデストラクタの形:

```cpp
SoraConnection::~SoraConnection() {
  Disconnect();
  Disposed();  // subscriber 通知は冪等ガード済み。video_source_ / audio_source_ は nullptr チェックで no-op
  if (publisher_) {
    publisher_->RemoveSubscriber(this);
  }
}
```

- `DisposePublisher::Disposed()` 側に `std::atomic<bool> disposed_` フラグを追加し、`disposed_.exchange(true)` が true を返した場合 (2 回目以降) は subscriber 通知ループをスキップするようにする。`std::atomic` を使うのは、free-threading 対応を見据えた防御的選択である (現状の GIL 下では `disconnect()` とデストラクタの真の並行は到達不能だが、`DisposePublisher` は基底クラスとして全派生クラスの将来の並行利用に耐えるべき)。`exchange(true)` を使うことで check-then-set の TOCTOU 競合を排除する (単純な `if (disposed_) return; disposed_ = true;` では競合が残る)。
- `disposed_` フラグがガードするのは基底クラスの subscriber 通知ループのみ。`SoraConnection::Disposed()` の `video_source_` / `audio_source_` クリーンアップは既存の nullptr チェックが引き続きガードする。`SoraTrackInterface::Disposed()` の `publisher_ = nullptr; track_ = nullptr;` は nullptr 代入の冪等性 (scoped_refptr への nullptr 再代入が no-op) により安全性が保たれる。派生クラス側の既存ガードと基底フラグの役割分担は以下のとおり:
  - 基底フラグ (`disposed_`): subscriber への `PublisherDisposed()` 通知の重複防止
  - 派生クラスの nullptr チェック / nullptr 代入の冪等性: 個別リソースの解放の重複防止
- `SoraVideoSource::Disposed()` は issue 0023 (`issues/closed/0023-bug-fix-sora-video-source-no-disposed-override.md`) で `finished_.exchange(true)` によるワーカスレッド停止シグナルの重複防止を実装済みであり、本 issue の基底フラグ (subscriber 通知の重複防止) とは異なる層をガードする補完的な関係にある。
- `disposed_` フラグは `DisposePublisher` 基底に追加されるため全派生クラス (`Sora`, `SoraConnection`, `SoraTrackInterface`, `SoraVideoSource`, `SoraAudioSource`, `SoraMediaTrack`) に影響する。`Sora::~Sora()` は `Disposed()` を 1 回しか呼ばないため振る舞いは変わらない。`SoraMediaTrack` は `PublisherDisposed()` 経由の早期 `Disposed()` + デストラクタの `Disposed()` の 2 回パスがあるが、nullptr 代入の冪等性で安全。
- 修正後も、現状の正しい振る舞い (購読者への通知が確実に 1 度行われること、 `video_source_` / `audio_source_` の登録解除が確実に行われること) を変えないこと。

## 完了条件

- `SoraConnection` の通常破棄経路 (conn_ あり) で `Disposed()` の実効的な副作用が 1 回だけであることを、コードレビューおよび手動トレースで確認できる。
- `conn_ == nullptr` 経路 (Init 未呼び出し) でも `Disposed()` が 1 回呼ばれ、subscriber への通知が行われることを確認できる。
- `DisposePublisher::Disposed()` が複数回呼ばれても subscriber 通知が重複しないことが、実装とテストで確認できる。
- 既存テスト ( `tests/` 配下) が全て通り、リソースリークやクラッシュが発生しないこと。
