# SoraVideoSource に Disposed の override が無く送信スレッド停止がデストラクタ依存になっている問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Completed: 2026-07-27
- Model: Opus 4.7
- Branch: feature/fix-sora-video-source-no-disposed-override

## 目的

`SoraVideoSource` は送信用ワーカスレッドを保持しているが、 `SoraTrackInterface::PublisherDisposed()` 経由で `Disposed()` が呼ばれた際に、 `SoraVideoSource` 固有の停止処理 ( `finished_ = true; queue_cond_.notify_all();` ) が走らない。
そのため、 Python 側の参照カウントが残ったまま生成元の Sora インスタンスが先に破棄されると、 `SoraVideoSource` のワーカスレッドが残存する可能性がある。
スレッドの寿命を `track_` の寿命に確実に追従させ、リソースリークを防ぐ。

## 優先度根拠

Medium とする。

- 通常運用では Python 側参照が先に解放されるため `~SoraVideoSource()` が呼ばれてスレッドが停止し、現状でも問題は顕在化しにくい。
- ただし、 Python 側で `SoraVideoSource` を保持したまま Sora インスタンスのみを破棄するユースケース (例: テストでの寿命操作、複雑なオブジェクトグラフ) では、ワーカスレッドが残存しデッドロックやプロセス終了ハングの原因となり得る。
- リソース寿命の整合は SDK の品質に直結する論点であり、低コストで明確な修正で構造的整合を取れるため優先的に対応する。

## 現状

`src/sora_track_interface.h` 53-61 行 (基底クラス):

```cpp
virtual void Disposed() override {
  DisposePublisher::Disposed();
  publisher_ = nullptr;
  track_ = nullptr;
}
virtual void PublisherDisposed() override {
  // Track は生成元が破棄された後に再利用することはないので Disposed() を呼ぶ
  Disposed();
}
```

`src/sora_video_source.h` (送信スレッド・キュー):

```cpp
std::unique_ptr<std::thread> thread_;
std::condition_variable_any queue_cond_;
std::queue<std::unique_ptr<Frame>> queue_;
bool finished_;
```

`src/sora_video_source.cpp` 23-31 行 (デストラクタ):

```cpp
SoraVideoSource::~SoraVideoSource() {
  if (!finished_) {
    finished_ = true;
    queue_cond_.notify_all();
    gil_scoped_release release;
    thread_->join();
    thread_ = nullptr;
  }
}
```

スレッド停止に必要な `finished_ = true; queue_cond_.notify_all();` はデストラクタにのみ存在する。
基底クラスの `Disposed()` が `track_ = nullptr` を行うが、 `SoraVideoSource` 固有の状態 ( `finished_` , `queue_cond_` , `thread_` ) には触れない。

そのため、 publisher 側 (Sora インスタンス) が先に破棄されて `PublisherDisposed()` 経由で `Disposed()` が呼ばれても、ワーカスレッドは `queue_cond_.wait()` 上で待ち続ける。 Python 側の `SoraVideoSource` への参照が残っている限り、デストラクタが呼ばれないため、スレッドが回収されない。

## 設計方針

- `SoraVideoSource::Disposed()` を `override` として定義し、 `finished_ = true; queue_cond_.notify_all();` を先に行ったうえで、基底の `SoraTrackInterface::Disposed()` を呼ぶ。
- スレッドの `join` 自体はデストラクタに残してよいが、 `Disposed()` が複数回呼ばれても安全であるよう、 `finished_` チェックの順序を慎重に整える (issue 0024 と関連)。
- `Disposed()` の中で GIL を保持したまま `join` するとデッドロックする可能性があるため、 `join` は `Disposed()` ではなくデストラクタに残し、 `Disposed()` ではスレッドを停止可能な状態に遷移させるだけにする。

## 完了条件

- `SoraVideoSource::Disposed()` が override 定義され、 `finished_ = true; queue_cond_.notify_all();` が確実に実行されること。
- publisher 側を先に破棄しても、 `Python` 側参照がある間にスレッドが「待機解除可能な状態」になり、最終的なデストラクタで安全に `join` されることが確認できる。
- 既存テスト ( `tests/` 配下) が全て通ること。
- `SoraVideoSource` の寿命やスレッド停止に関する挙動が、 publisher 側破棄が先でも後でも変わらないことを確認する。

## 解決方法

`SoraVideoSource::Disposed()` を override し、`finished_.exchange(true)` と `queue_cond_.notify_all()` でワーカスレッドを待機解除可能な状態にする。
`join` は GIL 保持下のデッドロックを避けるためデストラクタに残す。

デストラクタは `Disposed()` 済みでも `thread_` があれば必ず `join` するよう整理した
（以前は `finished_` が既に true だと `join` をスキップしていた）。
