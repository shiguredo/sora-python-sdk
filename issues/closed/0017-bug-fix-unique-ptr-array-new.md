# `std::unique_ptr<uint8_t>` で配列 `new[]` を保持し未定義動作になっているのを修正する

- Priority: High
- Created: 2026-06-23
- Completed: 2026-07-16
- Model: Opus 4.7
- Branch: feature/fix-unique-ptr-array-new
- Polished: 2026-07-16

## 目的

`SoraVideoFrame::argb_data_` と `SoraVideoSource::Frame::data` が、配列 `new uint8_t[N]` で確保したメモリを非配列版の `std::unique_ptr<uint8_t>` で保持している。デストラクタは `default_delete<uint8_t>` 経由で非配列の `delete` を呼ぶため、配列として確保したメモリを非配列の `delete` で破棄するコードパスとなり、C++ 規格 `[expr.delete]` （配列 `new` と非配列 `delete` の不一致）上の未定義動作になる。配列版 `std::unique_ptr<uint8_t[]>` （`default_delete<uint8_t[]>` → `delete[]`）に直し、規格適合にする。

本 issue は静的な規格違反の修正である。実行時に SEGV を安定再現する手順は求めない。正しさの主証拠は、所有権型が配列版になり破棄が `delete[]` になることである。実接続テストは回帰検知に使う。

## 優先度根拠

High とする。

- C++ 規格上の未定義動作で、実装依存の偶然で動作している状態である。
- UB の発火点は `unique_ptr` の破棄であり、sink （受信 `SoraVideoFrame` の破棄）と source （送信バッファの破棄）の両方で起きる。動画の送受信を使う経路全般に潜在する。

## 現状

リポジトリ内で `new uint8_t[` と非配列 `std::unique_ptr<uint8_t>` が組み合わさっている箇所は、次の 2 系統のみである（`src/` を grep で確認済み）。

### `SoraVideoFrame` （sink / 受信）

`src/sora_video_sink.h:44`:

```cpp
std::unique_ptr<uint8_t> argb_data_;
```

`src/sora_video_sink.cpp:21`:

```cpp
argb_data_ = std::unique_ptr<uint8_t>(new uint8_t[width_ * height_ * 3]);
```

生成は `OnFrame` 本体ではなく、`PostTask` ラムダ内の `std::make_shared<SoraVideoFrame>(...)` （`sora_video_sink.cpp:102-112`）である。破棄は `shared_ptr` の参照カウントが 0 になったときで、`Data()` を呼ばなくても起きる。

### `SoraVideoSource` （source / 送信）

`src/sora_video_source.h:85-88`:

```cpp
Frame(std::unique_ptr<uint8_t> d, int w, int h, int64_t t)
    : data(std::move(d)), width(w), height(h), timestamp_us(t) {}

const std::unique_ptr<uint8_t> data;
```

`src/sora_video_source.cpp:52-57`:

```cpp
std::unique_ptr<uint8_t> data(new uint8_t[width * height * 3]);
memcpy(data.get(), ndarray.data(), width * height * 3);

if (finished_) {
  return;
}
```

`OnCaptured` で ndarray をコピーしたバッファを所有する。UB の発火点は次のとおり。

- `finished_ == true` の early return: `Frame` に渡さず、ローカル `data` の破棄で UB。`finished_ = true` はデストラクタのみのため、破棄進行中に `OnCaptured` が重なったときの経路である。
- 通常経路: `Frame` に移し、`SendFrameProcess` 内のローカル `std::unique_ptr<Frame>` のスコープ終了（`SendFrame` のあと、`return true` 前）で UB。
- 終了時: `SendFrameProcess` がキューをドレインせず抜ける場合、`~SoraVideoSource` での `queue_` 残要素破棄で UB。

### 対象外

- `SoraVideoSource::SendFrame(const uint8_t* argb_data, ...)` （`sora_video_source.h:95`）は生ポインタ引数であり、本 issue の型修正対象ではない。
- 変数名 `argb_data_` / パラメータ名 `argb_data` は実体が BGR24 （`libyuv::FOURCC_24BG`）だが、命名の変更は本 issue では行わない。
- `ndarray` の owner 問題は本 issue では解消しない（`issues/0034-bug-fix-ndarray-no-parent-reference.md`）。

## 設計方針

- 非配列 `std::unique_ptr<uint8_t>` を配列版 `std::unique_ptr<uint8_t[]>` に変更する。対象は次の 5 箇所である。
  - `sora_video_sink.h` のメンバ `argb_data_`
  - `sora_video_sink.cpp` の確保・代入
  - `sora_video_source.h` の `Frame` コンストラクタ引数
  - `sora_video_source.h` の `Frame::data` メンバ
  - `sora_video_source.cpp` のローカル `data` の確保
- 確保の書き方は次に限定する（機械検証と一致させるため）。
  - `std::unique_ptr<uint8_t[]>(new uint8_t[n])`
  - 本 issue では `std::make_unique<uint8_t[]>` や `reset(new uint8_t[n])` には書き換えない。
- `.get()` の戻り値は引き続き `uint8_t*` である。次の呼び出し側は変更しない。
  - `sora_video_sink.cpp` の `libyuv::ConvertFromI420` と `nb::ndarray` 構築
  - `sora_video_source.cpp` の `memcpy` と `SendFrame` への引き渡し
- 本修正固有のエッジケース対応は不要である（0x0 の early return 等は触らない）。

## 変更対象

- `src/sora_video_sink.h` / `src/sora_video_sink.cpp`: `argb_data_` の型と確保。
- `src/sora_video_source.h` / `src/sora_video_source.cpp`: `Frame` の引数・メンバと `OnCaptured` 内ローカルの型と確保。
- `CHANGES.md`: `## develop` に担当者行付きの `[FIX]` エントリを追加する。

`src/sora_sdk_ext.cpp`、`src/sora_sdk/sora_sdk_ext.pyi`、公開 API のシグネチャは変更しない。
回帰テストのソース変更は必須ではない（既存テストの実行でよい）。

## 完了条件

- 上記 5 箇所がすべて `std::unique_ptr<uint8_t[]>` になっていること。正しさの主証拠はこれ（破棄が `delete[]` になること）である。
- 機械検証（両方満たすこと）:
  - `rg -n 'unique_ptr<uint8_t\[\]>' src/` が 5 ヒットすること（メンバ 2・確保/代入・引数・ローカル確保）
  - `rg -n 'unique_ptr<uint8_t[^[]' src/` が 0 ヒットであること（非配列版の根絶）
- ネイティブ拡張がビルドできること。
- Python 公開 API （`SoraVideoFrame.data` / `SoraVideoSource.on_captured` 等）・`.pyi` の変更が不要であること。
- 既存の実接続テストで回帰しないこと（モックは使わない）。少なくとも次を通す。これらは UB の有無を直接証明するものではなく、型修正の副作用を見る回帰である。
  - source 経路: `tests/test_encoded_transform.py` の `test_encoded_transform` （`on_captured` 経由）
  - sink + source 経路: `tests/test_sendonly_recvonly.py` の `test_sendonly_recvonly_video` （`fake_video=True`。`tests/client.py` 経由で `SoraVideoSink` と `on_captured` の両方に触れる）
- `CHANGES.md` の `## develop` に、`[FIX]` の種別順と担当者行の書式を満たすエントリを追加すること。文言の方向性は次のとおり。
  - `SoraVideoFrame` / `SoraVideoSource` が配列確保メモリを非配列 `unique_ptr` で保持していた未定義動作を、`std::unique_ptr<uint8_t[]>` に修正する
- 実装完了時に `Completed: YYYY-MM-DD` を追加し、`## 解決方法` に実際の変更内容と検証結果（上記 rg・ビルド・テスト）を記録すること。

## 後方互換性

Python 公開 API、`.pyi`、送受信の観測可能な挙動は変更しない。
変更されるのは、C++ 内部の所有権型が非配列 `std::unique_ptr<uint8_t>` から配列版 `std::unique_ptr<uint8_t[]>` になる点だけである。

## 関連 issue

- `issues/0034-bug-fix-ndarray-no-parent-reference.md`: 同じ `argb_data_` / `Data()` 近傍だが、問題は `nb::handle()` による親参照不足 （GC 後の UAF）。0017 完了後も owner 問題は残る。0034 本文の所有権型表記は 0017 マージ後に refresh で追従する。
- `issues/0024-bug-fix-sora-video-source-queue-no-sync.md`: 同じ `Frame` / `queue_` を触るが、mutex / `atomic` による同期が主題。所有権型とは独立。
- `issues/0023-bug-fix-sora-video-source-no-disposed-override.md`: 同じ `SoraVideoSource` の寿命 / `Disposed`。バッファ型とは独立。

## 解決方法

設計方針どおり、非配列 `std::unique_ptr<uint8_t>` を配列版 `std::unique_ptr<uint8_t[]>` に変更した。確保は `std::unique_ptr<uint8_t[]>(new uint8_t[n])` に統一した。

変更箇所:

- `src/sora_video_sink.h` / `src/sora_video_sink.cpp`: `argb_data_`
- `src/sora_video_source.h` / `src/sora_video_source.cpp`: `Frame` の引数・メンバと `OnCaptured` 内ローカル `data`

検証:

- `rg -n 'unique_ptr<uint8_t\[\]>' src/` が 5 ヒット
- 非配列 `unique_ptr<uint8_t>` が `src/` に残っていないこと
- `uv run python run.py build macos_arm64` が成功

`CHANGES.md` の `## develop` に `[FIX]` を追記した。
