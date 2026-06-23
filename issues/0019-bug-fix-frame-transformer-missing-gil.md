# `SoraAudioFrameTransformer::Transform` と `SoraVideoFrameTransformer::Transform` で GIL を取得せずに `on_transform_` を呼んでいる問題を修正する

- Priority: High
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-frame-transformer-missing-gil

## 目的

`SoraAudioFrameTransformer::Transform` と `SoraVideoFrameTransformer::Transform` は、libwebrtc のエンコーダ/デコーダワーカースレッド (GIL 非保持) から呼ばれる `webrtc::FrameTransformerInterface::Transform` の override。内部で Python の `std::function` (`on_transform_`) を直接呼んでおり、GIL を取得していない。Python オブジェクトの構築 (`std::make_unique<SoraTransformableAudioFrame>`/`SoraTransformableVideoFrame`) と `std::function` 呼び出しで Python C-API に触れるため、GIL 未保持で SEGV / メモリ破壊が発生しうる。

## 優先度根拠

High とする。

- libwebrtc のエンコーダ/デコーダスレッドから確実に GIL 非保持で呼ばれる経路。Encoded Transform 機能を有効化したユーザで再現性のあるクラッシュ。
- `SoraConnection::OnPush` (`closed/0009`) や `SoraAudioSink::Read` (`closed/0012` / `closed/0014`) で同種の修正が既に行われており、未対応で残るのは frame transformer のみ。
- 修正コストは小さい (各 Transform で `gil_scoped_acquire acq;` を 1 行追加)。

## 現状

### `SoraAudioFrameTransformer`

`src/sora_frame_transformer.h:258-269`:

```cpp
class SoraAudioFrameTransformer : public SoraFrameTransformer {
 public:
  SoraAudioFrameTransformer() : SoraFrameTransformer() {}

  void Transform(std::unique_ptr<webrtc::TransformableFrameInterface>
                     transformable_frame) override {
    on_transform_(std::make_unique<SoraTransformableAudioFrame>(
        std::move(transformable_frame)));
  }
  std::function<void(std::unique_ptr<SoraTransformableAudioFrame>)>
      on_transform_;
};
```

### `SoraVideoFrameTransformer`

`src/sora_frame_transformer.h:325-336`:

```cpp
class SoraVideoFrameTransformer : public SoraFrameTransformer {
 public:
  SoraVideoFrameTransformer() : SoraFrameTransformer() {}

  void Transform(std::unique_ptr<webrtc::TransformableFrameInterface>
                     transformable_frame) override {
    on_transform_(std::make_unique<SoraTransformableVideoFrame>(
        std::move(transformable_frame)));
  }
  std::function<void(std::unique_ptr<SoraTransformableVideoFrame>)>
      on_transform_;
};
```

### 呼び出し元

`webrtc::FrameTransformerInterface::Transform` は libwebrtc のエンコーダ/デコーダワーカースレッドから呼ばれる。`gil.h` で定義した `gil_scoped_acquire` を呼ぶ前に Python C-API に触れる経路になっている。

## 設計方針

- `SoraAudioFrameTransformer::Transform` と `SoraVideoFrameTransformer::Transform` の冒頭で `gil_scoped_acquire acq;` を取得する。
- ただし libwebrtc 側のロック保持中に GIL を取得することになるため、video sink (`src/sora_video_sink.cpp:89-99` のコメント) で議論されたデッドロック条件と同じ構造になっていないかを確認する。デッドロックの危険があれば、`PostTask` 経由でワーカースレッドへ飛ばし、そこで GIL を取る形に変更する。
- `on_transform_` 呼び出しが「同期で行われる前提」(`enqueue` の責務など) を `webrtc::FrameTransformerInterface` の仕様で確認する。同期前提でないなら `PostTask` で安全に切り離せる。

`CHANGES.md` の `## develop` セクションに `[FIX]` エントリを追加する。

## 完了条件

- `SoraAudioFrameTransformer::Transform` と `SoraVideoFrameTransformer::Transform` の中で、`on_transform_` 呼び出し前に GIL が保持されていること。
- `tests/test_encoded_transform.py` の Audio / Video 双方が通り続けること。
- libwebrtc のエンコーダ/デコーダスレッドから Python オブジェクトを GIL 非保持で触る経路がコードベース全体で残っていないこと。
