# SoraAudioSource::OnData の一部オーバーロードだけ track_ の null チェックが抜けている問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-audio-source-on-data-no-null-check

## 目的

`SoraAudioSource::OnData` は 4 つのオーバーロードを持つが、 `OnData(const int16_t* data, size_t samples_per_channel)` のみ、 `track_` の null チェックが抜けている。
他の 3 つは `if (!track_) return;` で守られているため、 publisher 側破棄後に `Disposed()` で `track_ = nullptr` された後の呼び出しでも安全に弾ける。
このオーバーロードだけが整合を欠いており、破棄後の競合パスで未定義動作に至るリスクがある。
他オーバーロードと同様の null チェックを追加し、対称性と安全性を取り戻す。

## 優先度根拠

Medium とする。

- 通常運用ではユーザーが破棄済みの `SoraAudioSource` に `OnData` を呼ぶことは想定されにくく、観測可能なクラッシュは現状報告されていない。
- 一方で、 publisher 側の破棄と Python 側 `OnData` 呼び出しの順序によっては、 `track_ == nullptr` 状態で `source_->OnData` を呼ぶ経路が発生し得る。 `source_` 自体が無効化されている場合に未定義動作になる可能性がある。
- 他の 3 つのオーバーロードと一貫していないこと自体が明確な欠陥で、修正コストはほぼゼロであり、 broken window として放置すべきでない。

## 現状

`src/sora_audio_source.cpp` の `OnData` 4 オーバーロード:

139-146 行 (1 つ目、 null チェック有り):

```cpp
void SoraAudioSource::OnData(const int16_t* data,
                             size_t samples_per_channel,
                             double timestamp) {
  if (!track_) {
    return;
  }
  source_->OnData(data, samples_per_channel, (int64_t)(timestamp * 1000));
}
```

148-150 行 (2 つ目、 null チェック無し):

```cpp
void SoraAudioSource::OnData(const int16_t* data, size_t samples_per_channel) {
  source_->OnData(data, samples_per_channel, std::nullopt);
}
```

152-161 行 (3 つ目、 null チェック有り):

```cpp
void SoraAudioSource::OnData(
    nb::ndarray<int16_t, nb::shape<-1, -1>, nb::c_contig, nb::device::cpu>
        ndarray,
    double timestamp) {
  if (!track_) {
    return;
  }
  source_->OnData(ndarray.data(), ndarray.shape(0),
                  (int64_t)(timestamp * 1000));
}
```

163-169 行 (4 つ目、 null チェック有り):

```cpp
void SoraAudioSource::OnData(
    nb::ndarray<int16_t, nb::shape<-1, -1>, nb::c_contig, nb::device::cpu>
        ndarray) {
  if (!track_) {
    return;
  }
  source_->OnData(ndarray.data(), ndarray.shape(0), std::nullopt);
}
```

148-150 行のオーバーロードだけ `if (!track_) return;` が抜けており、 `track_` が `nullptr` の状態で `source_->OnData` が呼ばれる可能性がある。

## 設計方針

- 148-150 行の `OnData(const int16_t* data, size_t samples_per_channel)` の先頭に、他オーバーロードと同じ `if (!track_) { return; }` を追加する。
- 4 オーバーロード全てで先頭の null チェックが同一になるよう、コード上の対称性を確保する。
- 将来同種の漏れを防ぐため、可能であれば private なヘルパー (例: `bool IsAlive() const { return track_ != nullptr; }` ) に置き換えることも検討するが、本 issue では最小修正でよい。

## 完了条件

- 148-150 行のオーバーロードに `track_` の null チェックが追加され、 4 オーバーロード全てが対称になっていること。
- 既存テスト ( `tests/` 配下) が引き続き通ること。
- `track_` が `nullptr` の状態で 4 オーバーロードのいずれを呼んでも、 SDK が安全に no-op で返ることが確認できる。
