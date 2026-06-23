# `std::unique_ptr<uint8_t>` で配列 `new[]` を保持し未定義動作になっているのを修正する

- Priority: High
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-unique-ptr-array-new

## 目的

`SoraVideoFrame::argb_data_` と `SoraVideoSource::OnCaptured` 内の作業バッファが、配列 `new uint8_t[N]` で確保したメモリを非配列版の `std::unique_ptr<uint8_t>` で保持している。デストラクタが `delete` を呼ぶため、`new[]` で確保したメモリを `delete` で破棄するコードパスとなり、C++ 規格 ([expr.delete]/3) 上の未定義動作になる。多くの実装ではメモリは解放されるが、規格的には UB であり、ツールチェーン更新・最適化レベル変更で予期せぬ挙動を起こしうる。

## 優先度根拠

High とする。

- C++ 規格上の未定義動作で、実装依存の偶然で動作している状態。
- 修正は型を `std::unique_ptr<uint8_t[]>` に変えるだけで副作用無し。
- BGR24 フレームを扱うすべての sink / source 経路で発生しており、`SoraVideoFrame::Data` を Python 側で呼ぶ全ユーザに影響する。

## 現状

### `SoraVideoFrame` 側 (sink)

`src/sora_video_sink.h:44`:

```cpp
std::unique_ptr<uint8_t> argb_data_;
```

`src/sora_video_sink.cpp:21`:

```cpp
argb_data_ = std::unique_ptr<uint8_t>(new uint8_t[width_ * height_ * 3]);
```

### `SoraVideoSource` 側 (source)

`src/sora_video_source.h:88`:

```cpp
const std::unique_ptr<uint8_t> data;
```

`src/sora_video_source.cpp:52`:

```cpp
std::unique_ptr<uint8_t> data(new uint8_t[width * height * 3]);
```

両者とも `new uint8_t[N]` で配列を確保した結果を非配列版の `unique_ptr` に渡しており、デストラクタは `delete` (非配列版) を呼ぶ。

## 設計方針

- `std::unique_ptr<uint8_t>` を `std::unique_ptr<uint8_t[]>` に変更する。
- 宣言・代入の両方を直す (ヘッダのメンバ宣言、コンストラクタや関数内のローカル変数、`Frame` 構造体のメンバ)。
- 変数名 `argb_data_` は実体が BGR24 なので別 issue で `bgr_data_` 等にリネーム検討するが、本 issue の範囲外とする。

## 完了条件

- `src/sora_video_sink.h:44`、`src/sora_video_sink.cpp:21`、`src/sora_video_source.h:88`、`src/sora_video_source.cpp:52` の `std::unique_ptr<uint8_t>` が `std::unique_ptr<uint8_t[]>` に変更されていること。
- リポジトリ全体で `std::unique_ptr<uint8_t>(new uint8_t[` のパターンが残っていないこと (`grep` で検証)。
- 既存の動画送受信テストが通り続けること (`tests/test_encoded_transform.py` ほか)。
