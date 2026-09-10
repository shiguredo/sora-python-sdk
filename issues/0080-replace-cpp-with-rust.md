# Rust ベースに全面置き換えする

- Created: 2026-09-05
- Completed: -
- Branch: feature/add-sora-rust-sdk-prototype
- Polished: {YYYY-MM-DD}

## 目的

C++ 実装を削除し、Rust ベースを `sora_sdk` 名に昇格させる。
旧 tests は一部変更だけで通ることを完了条件にする。

## 現状

- Rust 実装は `sora_rust_sdk` 名の試作で、受信・送信・残差 API を再現済みである。
- C++ 実装 (`src/` の原始と CMake / setup 系) が残っている。
- 旧 tests (40 件) は `sora_sdk` 名と旧 API 形状を前提にしている。
- 不足する互換要素は列挙群、記録制御、符号化器情報、辞書 metadata、
  3 引数 Sink、VAD、frame transformer、libcamera である。
- 音声 encoded 変換は組み立て器に受け口がなく対象外とする。
- `state` / `stream_id` は取得口がなく対象外とする。

## 設計方針

- C++ 原始と CMake / setup 系と旧 tests を削除し、Rust 実装を根元に移す。
- 旧 tests の前提に合わせて互換要素を追加し、名称は `sora_sdk` に統一する。
- リサンプルは直線補間で自前実装し、VAD は実力 but 簡易方式と明記する。
- 動作確認は手元の実 Sora で旧 tests を走らせて行う。
  実行できない基盤依存の tests は選別結果を記録する。

## 完了条件

- 旧 tests が一部変更だけで通り、差分理由が整理されていること。
- C++ 実装の残骸が残っていないこと。
