# SoraAudioSourceInterface のコンストラクタに境界値検査が無く不正な引数でクラッシュする問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Completed: 2026-07-27
- Model: Opus 4.7
- Branch: feature/fix-audio-source-no-validation

## 目的

`SoraAudioSourceInterface` のコンストラクタは `sample_rate` および `channels` を引数で受け取るが、値の妥当性を検査していない。
`sample_rate < 100` の場合 `buffer_samples_ = sample_rate / 100` が 0 になり、 `channels == 0` の場合 `buffer_size_` が 0 になる。
その後 `new int16_t[buffer_size_]` でサイズ 0 の配列を確保しようとし、後続処理で 0 除算や空アクセスによりクラッシュ・機能不全を引き起こす。
Python 側からの不正引数を早期に弾き、明確な例外メッセージを返すようにする。

## 優先度根拠

Medium とする。

- 通常の使用パターン (例: 48000 Hz / 2ch、 16000 Hz / 1ch) では問題は発生しない。
- ただし、ユーザーが誤って 50 Hz や 0 ch を渡した場合、ネイティブ層でサイズ 0 の `new` や `sample_rate * channels` での 0 除算に至り、 Python 例外として扱えない形でクラッシュする可能性がある。
- API 境界での値検証は SDK の堅牢性の基本要件であり、低コストで実装でき、エラー診断性を大きく向上できるため優先的に対応する。

## 現状

`src/sora_audio_source.cpp` 3-12 行:

```cpp
SoraAudioSourceInterface::SoraAudioSourceInterface(size_t channels,
                                                   int sample_rate)
    : channels_(channels),
      sample_rate_(sample_rate),
      buffer_samples_(sample_rate / 100),
      buffer_size_(sample_rate / 100 * channels),
      buffer_used_(0),
      last_timestamp_(0) {
  buffer_ = new int16_t[buffer_size_];
}
```

- `sample_rate < 100` のとき、 `sample_rate / 100 == 0` となり `buffer_samples_` および `buffer_size_` が 0 になる。
- `channels == 0` のとき、 `buffer_size_ = sample_rate / 100 * 0 == 0` となる。
- `new int16_t[0]` は規格上は許されているが、その後の 10ms フレーム送出時に 0 除算や、空配列への書き込みが発生して未定義動作になる。
- `sample_rate` は `int` 型なので負値も渡しうるが、これも検査されていない。

## 設計方針

- コンストラクタ冒頭で以下を検査し、無効値の場合は `nb::value_error` (もしくは適切な Python 例外) を投げる。
  - `sample_rate >= 100` (10ms バッファを成立させる最小値)
  - `channels >= 1`
  - 必要に応じて `sample_rate` の上限 (例: 192000 Hz 等) や `channels` の上限 (例: 64 ch 等) も検討する。ただし上限は SDK 全体で揃える必要があるため、本 issue では最小値の検証を必須とする。
- エラーメッセージは英語のログメッセージとして、何の値が無効だったかを明示する (例: `"sample_rate must be at least 100 Hz, got <value>"` )。
- Python バインディング側でも引数を `int` / `size_t` で受け取っているか確認し、必要なら docstring に有効範囲を追記する。

## 完了条件

- `sample_rate < 100` または `channels == 0` を渡した場合に、 `new` が走る前に Python 例外で弾かれること。
- 例外メッセージから、ユーザーが原因 (どの引数が無効か) を即座に判別できること。
- 既存の正当なパラメータ ( 48000 Hz / 2ch など) では動作が変わらないこと。
- バリデーションを追加したことに伴うテスト (無効値で例外が出るケース) が `tests/` に追加されること。

## 解決方法

`SoraAudioSourceInterface` コンストラクタで `new` の前に最小値を検査し、無効なら `std::invalid_argument` を投げるようにした。
nanobind がこれを Python の `ValueError` に変換する。

- `sample_rate < 100` → `"sample_rate must be at least 100 Hz, got <value>"`
- `channels < 1` → `"channels must be at least 1, got <value>"`

`tests/test_audio_source_invalid_params.py` で上記 2 ケースを検証した。
