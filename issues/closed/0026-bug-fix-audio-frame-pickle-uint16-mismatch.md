# SoraAudioFrame の pickle 経路で int16_t を uint16_t に詰め替えている型不整合を修正する

- Priority: Medium
- Created: 2026-06-23
- Completed: 2026-07-28
- Model: Opus 4.7
- Branch: feature/fix-audio-frame-pickle-uint16-mismatch
- Polished: 2026-07-28

## 目的

`SoraAudioFrame` の音声データは符号付き 16 bit (`int16_t`) であるにもかかわらず、 `VectorData()` の戻り型および pickle 復元用コンストラクタ `SoraAudioFrameVectorImpl` の引数型が `std::vector<uint16_t>` (符号なし) になっている。
`RawData()` 内で `(const int16_t*)vector_.data()` と C スタイルキャストを行っており、型としての意味が崩れている。signed/unsigned の対応する整数型同士の alias は C++ の strict aliasing rule で明示的に許可されているため UB ではないが、型の意味が不一致であり、静的解析ツールや LLM に対しても誤解を生じる「broken window」である。
扱う型を `std::vector<int16_t>` に統一し、型の意味と実装を一致させる。

## 優先度根拠

Medium とする。

- 現状は実害が観測されていないが、符号付き音声サンプルを符号なし型として保持する設計は明確に誤りであり、 LLM や静的解析ツールに対しても誤解を生じる「broken window」である。
- pickle 経路は Python 側のマルチプロセス処理 (例: `multiprocessing` でのフレーム転送) で実利用される可能性があり、 endianness や数値表現のテストを増やす際にもこの不整合が障害となる。
- 型の整合を取るための変更は機械的かつ範囲が限定されており、低コストで根本的に解消できる。

## 現状

`src/sora_audio_stream_sink.cpp` 24-30 行 ( `SoraAudioFrameDefaultImpl::VectorData` ):

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

同 97-106 行 ( `SoraAudioFrame` の pickle 復元コンストラクタ):

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

同 67-69 行 ( `SoraAudioFrameVectorImpl::RawData` ):

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

- 変更対象ファイル: `src/sora_audio_stream_sink.h`、`src/sora_audio_stream_sink.cpp`、`src/sora_sdk_ext.cpp`
- `SoraAudioFrameImpl` (抽象基底クラス) の純粋仮想宣言 (`sora_audio_stream_sink.h:27`)、`SoraAudioFrameDefaultImpl::VectorData()` / `SoraAudioFrameVectorImpl::VectorData()` / `SoraAudioFrame::VectorData()` の戻り型を全て `std::vector<int16_t>` に統一する。
- `SoraAudioFrameVectorImpl` および `SoraAudioFrame` の Vector 受け取りコンストラクタの引数型も `std::vector<int16_t>` に変更する。
- `sora_sdk_ext.cpp` の `__getstate__` / `__setstate__` のタプル型も `std::vector<int16_t>` に揃える。
- 内部メンバ `vector_` 自体も `std::vector<int16_t>` に変更し、 `RawData()` の reinterpret_cast を撤廃する。`SoraAudioFrame::RawData()` (`sora_audio_stream_sink.cpp:120-122`) の冗長な C スタイルキャストも同時に除去する。なお `SoraAudioFrame::Data()` (`sora_audio_stream_sink.cpp:116`) の `(int16_t*)RawData()` は const_cast であり本変更の対象外。
- ヘッダの doc コメント (`sora_audio_stream_sink.h:117,121`) の `uint16_t` 記述も `int16_t` に更新する。
- pickle 後方互換性について: nanobind は `std::vector<uint16_t>` を Python の int リスト (0〜65535) として直列化する。変更後の `__setstate__` は `std::vector<int16_t>` を期待するため、旧 pickle データの 32768 以上の値は int16_t への変換時にオーバーフローしうる。ただし pickle データはプロセス内の一時データであり、バージョンをまたいで永続化する用途はないため、後方互換性は切り捨てる。この方針を CHANGES.md に記載する。

## 完了条件

- `VectorData()` / `__getstate__` / `__setstate__` / `SoraAudioFrameVectorImpl` の全経路で型が `std::vector<int16_t>` に統一されること。
- `RawData()` の reinterpret_cast 相当のキャストおよび `SoraAudioFrame::RawData()` の冗長キャストが撤廃されること。
- pickle / unpickle 経路のラウンドトリップを検証するテストを追加し、音声データが破損しないことを確認できること。
- 既存テスト ( `tests/` 配下) が引き続き通り、リソースリークやクラッシュが発生しないこと。

## 解決方法

`src/sora_audio_stream_sink.h`、`src/sora_audio_stream_sink.cpp`、`src/sora_sdk_ext.cpp` の 3 ファイルで、`SoraAudioFrameImpl` 抽象基底クラスの純粋仮想宣言、`SoraAudioFrameDefaultImpl::VectorData()`、`SoraAudioFrameVectorImpl` のコンストラクタ・メンバ・`VectorData()`・`RawData()`、`SoraAudioFrame` のコンストラクタ・`VectorData()`・`RawData()`、および `__setstate__` のタプル型を全て `std::vector<int16_t>` に統一した。`RawData()` の C スタイルキャスト (`(const int16_t*)vector_.data()` および `(const int16_t*)impl_->RawData()`) を撤廃し、型安全な直接返却に変更した。
