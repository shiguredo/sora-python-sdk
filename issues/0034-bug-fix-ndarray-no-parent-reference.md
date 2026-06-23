# SoraVideoFrame / SoraAudioFrame / SoraTransformableFrame の ndarray に親オブジェクトの参照を保持させる

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-ndarray-no-parent-reference

## 目的

`SoraVideoFrame::Data`、`SoraAudioFrame::Data`、`SoraTransformableFrame::GetData` の 3 箇所では、戻り値となる `nb::ndarray` のオーナー引数に `nb::handle()` (空ハンドル) を渡している。この実装では返した `ndarray` がメモリの実体を所有するオブジェクト (フレームインスタンス) への参照を保持しておらず、Python 側でフレームインスタンスが GC された瞬間に `ndarray` がダングリングポインタを指す状態になる。素直に書けば `frame.Data()` の戻り値だけを保持して `frame` を解放するコードは普通に書かれうるため、ユーザ側からは「アクセスすると SEGV する」「無効な値が返る」というクラッシュ系の障害として現れる。本 issue では nanobind の慣用に従って親オブジェクトの参照を `ndarray` に持たせ、参照グラフ上で実体が `ndarray` より先に消えないことを保証する。

## 優先度根拠

Medium とする。

- メモリ安全に関わるバグで、表面化すると SEGV または不可解な値の崩れにつながる。
- 一方で「ユーザがフレームを保持しないまま `Data()` の戻りだけを保持する」というやや変則的な使い方をしないと顕在化しないため、再現頻度は中程度。
- 修正は nanobind の慣用 (`self` を `nb::handle` として渡す) に倣えば各箇所小さな変更で済むが、テンプレートシグネチャやバインディングに少し変更が要る場合があり、影響範囲の確認は必要。
- データ破壊系の潜在バグであり、放置は不可。優先的に潰すべきだが現時点で再現報告はないため High ではなく Medium とする。

## 現状

3 箇所で同種の問題がある。

### `src/sora_video_sink.cpp:28-33`

```cpp
nb::ndarray<nb::numpy, uint8_t, nb::shape<-1, -1, 3>> SoraVideoFrame::Data() {
  size_t shape[3] = {static_cast<size_t>(height_), static_cast<size_t>(width_),
                     3};
  return nb::ndarray<nb::numpy, uint8_t, nb::shape<-1, -1, 3>>(
      argb_data_.get(), 3, shape, nb::handle());
}
```

`argb_data_` は `SoraVideoFrame` が `std::unique_ptr<uint8_t>` で保持しており、`SoraVideoFrame` が破棄されるとメモリも解放される。返している `ndarray` の owner は `nb::handle()` (空) のため、`SoraVideoFrame` の Python ラッパが GC された後に `ndarray` だけ参照を持っていると、`argb_data_` が指す既に解放済みメモリにアクセスする。

### `src/sora_audio_stream_sink.cpp:107-114`

```cpp
nb::ndarray<nb::numpy, int16_t, nb::shape<-1, -1>> SoraAudioFrame::Data()
    const {
  // Data はまだ vector の時は返せてない
  size_t shape[2] = {static_cast<size_t>(samples_per_channel()),
                     static_cast<size_t>(num_channels())};
  return nb::ndarray<nb::numpy, int16_t, nb::shape<-1, -1>>(
      (int16_t*)RawData(), 2, shape, nb::handle());
}
```

`RawData()` は `impl_->RawData()` に転送されるが、その実体は `webrtc::AudioFrame` か独自バッファのいずれかで、いずれも `SoraAudioFrame` 自身が所有する。`ndarray` の owner が空なので、`SoraAudioFrame` が消えた瞬間に同じ問題が起きる。

### `src/sora_frame_transformer.h:122-129`

```cpp
const nb::ndarray<nb::numpy, const uint8_t, nb::shape<-1>> GetData() const {
  auto view = frame_->GetData();

  // pybind11 なら memoryview があるが、 nanobind にはなく ndarray に const をつけて ReadOnly にする
  size_t shape[1] = {static_cast<size_t>(view.size())};
  return nb::ndarray<nb::numpy, const uint8_t, nb::shape<-1>>(
      view.data(), 1, shape, nb::handle());
}
```

`view.data()` は `frame_` (= `webrtc::TransformableFrameInterface`) の所有するバッファを指す。`SoraTransformableFrame` (とその派生) が破棄されると `frame_` も解放され、`view.data()` が指す領域が無効になる。owner 不足は同様。

## 設計方針

nanobind の `nb::ndarray` は第 4 引数の `nb::handle` 形式の owner に Python オブジェクトを渡すと、`ndarray` の生存期間を owner に紐付けてくれる (内部的に `Py_INCREF` 相当の処理を行い、`ndarray` 解放時に `Py_DECREF` する)。

- 3 つの関数いずれも親オブジェクトは `this` (= フレームのバインディングが指す Python オブジェクト) なので、`nb::find(this)` などで対応する `nb::handle` を取得して owner に渡すのが素直。`nb::handle()` の代わりに `nb::cast(this).ptr()` 相当の表現にする方法もあり、本リポジトリで `nb::find` を使っている箇所があるならそれに揃える。
- C++ コンストラクタが `this` から `nb::handle` を取れるのは、対応する Python ラッパが既に作られている状態 (Python 側からそのオブジェクトのメソッドが呼ばれた時点) であり、`Data()` / `GetData()` が呼ばれる場面はその条件を満たす。
- ヘッダ側 (`sora_frame_transformer.h`) は `const` メンバ関数なので `this` の型が `const`。owner 取得 API のシグネチャと合わせて適切にキャストする。
- 必要なら 3 関数に共通する小さなヘルパ (例: `MakeOwnedNdArray(...)`) を切り出すが、まずは 3 箇所をそれぞれ素直に書き直して動作を確認するのが最短。

## 完了条件

- Python 側で以下のような書き方をしても安全に動作すること。

```python
data = frame.data  # ndarray を取り出して
del frame          # フレーム自体は解放
print(data.sum())  # ここでクラッシュしない
```

- 3 関数のいずれかが返す `ndarray` の owner が空 (`nb::handle()`) のままになっていないこと。
- 既存の e2e テスト・ユニットテストが引き続き通ること。
- 必要であれば「`ndarray` を保持したままフレームを解放する」テストケースを追加し、SEGV しないことを確認する。
