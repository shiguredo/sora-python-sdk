# SoraAudioFrame の pickle 経路で int16_t を uint16_t に詰め替えている型不整合を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-audio-frame-pickle-uint16-mismatch

## 目的

`SoraAudioFrame` の音声データは符号付き 16 bit (`int16_t`) であるにもかかわらず、 `VectorData()` の戻り型および pickle 復元用コンストラクタ `SoraAudioFrameVectorImpl` の引数型が `std::vector<uint16_t>` (符号なし) になっている。
`RawData()` 内で `(const int16_t*)vector_.data()` と reinterpret_cast 相当のキャストを行っており、 strict aliasing 規則に対してグレーな扱いとなる。実用上は同サイズの整数型なので動作しているが、型としての意味が崩れており、最適化条件によっては不正なコード生成のリスクがある。
扱う型を `std::vector<int16_t>` に統一し、型の意味と実装を一致させる。

## 優先度根拠

Medium とする。

- 現状は実害が観測されていないが、符号付き音声サンプルを符号なし型として保持する設計は明確に誤りであり、 LLM や静的解析ツールに対しても誤解を生じる「broken window」である。
- pickle 経路は Python 側のマルチプロセス処理 (例: `multiprocessing` でのフレーム転送) で実利用される可能性があり、 endianness や数値表現のテストを増やす際にもこの不整合が障害となる。
- 型の整合を取るための変更は機械的かつ範囲が限定されており、低コストで根本的に解消できる。

## 現状

`src/sora_audio_stream_sink.cpp` 23-29 行 ( `SoraAudioFrameDefaultImpl::VectorData` ):

```cpp
std::vector<uint16_t> SoraAudioFrameDefaultImpl::VectorData() const {
  std::vector<uint16_t> vector(
      audio_frame_->data(),
      audio_frame_->data() +
          audio_frame_->samples_per_channel() * audio_frame_->num_channels());
  return vector;
}
```

`audio_frame_->data()` の戻りは `const int16_t*` だが、 `std::vector<uint16_t>` に詰め直されている。

同 96-105 行 ( `SoraAudioFrame` の pickle 復元コンストラクタ):

```cpp
SoraAudioFrame::SoraAudioFrame(
    std::vector<uint16_t> vector,
    size_t samples_per_channel,
    size_t num_channels,
    int sample_rate_hz,
    std::optional<int64_t> absolute_capture_timestamp_ms) {
  impl_.reset(new SoraAudioFrameVectorImpl(vector, samples_per_channel,
                                           num_channels, sample_rate_hz,
                                           absolute_capture_timestamp_ms));
}
```

同 66-68 行 ( `SoraAudioFrameVectorImpl::RawData` ):

```cpp
const int16_t* SoraAudioFrameVectorImpl::RawData() const {
  return (const int16_t*)vector_.data();
}
```

`src/sora_sdk_ext.cpp` 452-468 行 ( `__getstate__` / `__setstate__` ):

```cpp
.def("__getstate__",
     [](const SoraAudioFrame& frame) {
       // picke 化する際に呼び出されるので、すべてのデータを tuple に格納します。
       return std::make_tuple(
           frame.VectorData(), frame.samples_per_channel(),
           frame.num_channels(), frame.sample_rate_hz(),
           frame.absolute_capture_timestamp_ms());
     })
.def("__setstate__",
     [](SoraAudioFrame& frame,
        const std::tuple<std::vector<uint16_t>, size_t, size_t, int,
                         std::optional<int64_t>>& state) {
       // picke から戻す際に呼び出されるので、 tuple から SoraAudioFrame に戻します。
       new (&frame) SoraAudioFrame(std::get<0>(state), std::get<1>(state),
                                   std::get<2>(state), std::get<3>(state),
                                   std::get<4>(state));
     })
```

両ステート関数の型も `std::vector<uint16_t>` で定義されており、 pickle のタプル要素として符号なし 16 bit と扱われる。

## 設計方針

- `SoraAudioFrameDefaultImpl::VectorData()` / `SoraAudioFrameVectorImpl::VectorData()` / `SoraAudioFrame::VectorData()` の戻り型を全て `std::vector<int16_t>` に統一する。
- `SoraAudioFrameVectorImpl` および `SoraAudioFrame` の Vector 受け取りコンストラクタの引数型も `std::vector<int16_t>` に変更する。
- `sora_sdk_ext.cpp` の `__getstate__` / `__setstate__` のタプル型も `std::vector<int16_t>` に揃える。
- 内部メンバ `vector_` 自体も `std::vector<int16_t>` に変更し、 `RawData()` の reinterpret_cast を撤廃する。
- 既存の pickle データとの後方互換性は基本的に問題ないはず ( int16 と uint16 のビットパターンは同じ) だが、 numpy 等で型情報を持ち越す場合に差異が出ないか確認する。

## 完了条件

- `VectorData()` / `__getstate__` / `__setstate__` / `SoraAudioFrameVectorImpl` の全経路で型が `std::vector<int16_t>` に統一されること。
- `RawData()` の reinterpret_cast 相当のキャストが撤廃されること。
- 既存テスト ( `tests/` 配下) が引き続き通り、 pickle / unpickle 経路で音声データが破損しないことが確認できる。
- ABI / pickle 形式の互換性に影響があれば、その旨を CHANGES.md に記載する判断ができる状態にする。
