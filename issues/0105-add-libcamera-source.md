# libcamera 入力を Rust ベースで実装する

- Created: 2026-09-16
- Completed: -
- Branch: feature/add-libcamera-source
- Polished: {YYYY-MM-DD}

## 目的

現行 `sora_sdk` の `Sora.create_libcamera_source` を sora-rust-sdk の `libcamera` feature で再現する。現行は全プラットフォームで公開しつつ Raspberry Pi 以外では実行時にエラーを返す状態であり、移行で機能を失わないようにする。

## 現状

- `Sora.create_libcamera_source(width, height, fps, native_frame_output, controls)` は全プラットフォームで公開されている。`CMakeLists.txt` が Raspberry Pi のみ `USE_V4L2` を定義するため、Raspberry Pi 以外では実行時にエラーを返す。
- `setup.py` が Raspberry Pi 向けの wheel にのみ `libcamerac.so` を同梱する。
- sora-rust-sdk に `libcamera` feature (`dep:libc` と `dep:shiguredo_libcamera`) があり、`LibcameraVideoCapturerBuilder` と `LibcameraVideoCapturer` が公開される。
- ビルダーの引数は `camera_index(u32)` / `width(i32)` / `height(i32)` / `native_frame_output(bool)` / `control(key, value)` / `controls(Vec<(String, String)>)` である。既定値は camera_index 0 / 640 / 480 / false で、`build()` は width と height が 0 以下のときエラーを返す。
- `LibcameraNativeFrameBuffer` は `fd` / `size` / `stride` / `raw_width` / `raw_height` / `scaled_width` / `scaled_height` / `is_i420` / `is_nv12` を公開する。`native_frame_output` が true のとき DMA-BUF を出力する。
- 試作は `create_libcamera_source` を常にエラーを返す受け口として残しており、このままでは機能が失われる。
- 上流の `SoraConnectionBuilder` に fps に対応する設定が無い。

## 設計方針

- `docs/migration-to-sora-rust-sdk.md` の決定事項 11 に従う。
- `libcamera` feature を有効化して `create_libcamera_source` を実装する。feature の有効化方法 (常時 / 対象プラットフォームのみ / 別 wheel) は本 issue で確定する。Raspberry Pi OS 以外でビルドが壊れないことを条件とする。
- `native_frame_output` は `LibcameraVideoCapturerBuilder::native_frame_output` へ、`controls` は `control` / `controls` へそのまま渡す。
- `fps` は上流に対応する設定が無いため、次のいずれかを本 issue で確定する。上流へ追加を依頼する、`Video` の設定で代替できるか確認する、公開 API から外す。値を捨てて黙って無視しない。
- Raspberry Pi 以外でのエラーは、現行と同じく実行時に英語のメッセージで返す。
- wheel への `libcamerac.so` 同梱は CI の issue と連携して扱う。

## 完了条件

- `libcamera` feature を有効にしたビルドが通り、対象プラットフォームで `Sora.create_libcamera_source` が映像入力を開始できること。
- `native_frame_output` と `controls` が上流へ渡ること。
- `fps` の扱いが確定し、コードと issue の記述が一致していること。
- 対象プラットフォームで libcamera 入力の映像を実 Sora へ送信する pytest が通ること。

## 依存

- 先行: ビルド基盤を maturin へ置き換える issue、送信系 API の issue。
- 上流: 無し。sora-rust-sdk の `libcamera` feature を使う。
- 後続: CI の issue が本 issue に依存する (wheel への `libcamerac.so` 同梱のため)。

## 解決方法
