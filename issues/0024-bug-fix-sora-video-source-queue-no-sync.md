# SoraVideoSource の queue_ と finished_ に明示的な同期が無い問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-sora-video-source-queue-no-sync

## 目的

`SoraVideoSource` のフレームキュー ( `std::queue<std::unique_ptr<Frame>> queue_` ) と終了フラグ ( `bool finished_` ) は、複数スレッドから読み書きされるにもかかわらず、専用のミューテックスや `std::atomic` で保護されていない。
事実上は Python の GIL 取得によって同期されているが、 GIL の取得タイミングがコード上から自明ではなく、また `finished_` を `notify_all` の外で書き換える経路もあるため、データレースの観点で危うい。
明示的な同期プリミティブで意図を明確にし、 GIL に依存しない正しい同期を取れるようにする。

## 優先度根拠

Medium とする。

- 現在は GIL によって偶然動作しているが、これは設計の明示ではなく副作用的な保護であり、 GIL 取得タイミングを変更するリファクタリング (例: free-threaded Python 対応) で容易に壊れる構造である。
- データレースはサニタイザを使わないと発見が難しいクラスの問題で、本番でランダムなクラッシュとして顕在化する可能性がある。
- 低コストかつ局所的な修正で構造的に安全にできるため、優先的に対応する。

## 現状

`src/sora_video_source.h` 103-105 行:

```cpp
std::condition_variable_any queue_cond_;
std::queue<std::unique_ptr<Frame>> queue_;
bool finished_;
```

`src/sora_video_source.cpp` 55-79 行 (送信側と消費側):

```cpp
if (finished_) {
  return;
}
queue_.push(
    std::make_unique<Frame>(std::move(data), width, height, timestamp_us));
queue_cond_.notify_all();
}

bool SoraVideoSource::SendFrameProcess() {
  std::unique_ptr<Frame> frame;
  {
    GILLock lock;
    queue_cond_.wait(lock, [&] { return !queue_.empty() || finished_; });
    if (finished_) {
      return false;
    }
    frame = std::move(queue_.front());
    queue_.pop();
  }
  if (frame) {
    SendFrame(frame->data.get(), frame->width, frame->height,
              frame->timestamp_us);
  }
  return true;
}
```

- 生産側 ( `OnCaptured` ) は Python 経由で呼ばれるため GIL 保持中にキュー操作を行うが、コード上から「ここで GIL を持っている」という保証が読み取りにくい。
- 消費側 ( `SendFrameProcess` ) は `GILLock lock` を取って `queue_cond_.wait` するが、 `condition_variable_any` を GIL のロックで待つ運用も読みづらい。
- `finished_` は単なる `bool` で、デストラクタ側からの書き換え (`finished_ = true;` ) と、 OnCaptured 側からの読み取りに `std::atomic` を介していない。

## 設計方針

- `SoraVideoSource` 内に専用の `std::mutex queue_mtx_` を追加し、 `queue_` への push / pop および空判定をこのミューテックス下で行う。 `queue_cond_` も `std::condition_variable_any` のままで使うが、待機は `queue_mtx_` で行う方向に統一する。
- `finished_` を `std::atomic<bool>` に変更する。書き換えと読み取りが複数スレッドから行われるため、最低限のメモリ順序保証を確保する。
- GIL とミューテックスの取得順序に注意する。 `SendFrameProcess` で `GILLock` を取る必要があるのは Python のフレーム送出 ( `SendFrame` 内の Python 呼び出し有無) に応じて判断し、必要なら `gil_scoped_release` をかけて `queue_mtx_` を保持しないままで python へ戻る、などのデッドロック回避を検討する。

## 完了条件

- `queue_` の push / pop / 空判定が `queue_mtx_` 配下で行われること。
- `finished_` が `std::atomic<bool>` であり、書き換え・読み取りが明示的に同期されていること。
- 既存のフレーム送出機能 (フレーム順序、終了時の安全な停止) が回帰しないこと。
- GIL とミューテックスの取得順序が文書化され、デッドロックの可能性が排除されていること。
