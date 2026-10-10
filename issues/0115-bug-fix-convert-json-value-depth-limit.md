# `ConvertJsonValue()` が深い入れ子でスタックオーバーフローする問題を修正する

- Created: 2026-10-10
- Completed: -
- Branch: feature/fix-convert-json-value-depth-limit
- Polished: {YYYY-MM-DD}

## 目的

`metadata` や `send_rpc()` の `params` に深い入れ子の `list` / `dict` を指定するとスタックオーバーフローでプロセスが SIGSEGV し、Python の例外として扱えない問題を修正する。アプリケーションがデータから JSON を組み立てる場合、入れ子の深さは入力に依存する。

## 現状

- `src/sora_json.cpp` の `ConvertJsonValue()` は `list` / `dict` を再帰で変換しており、深さの上限が無い
- 実測 (macOS arm64 / Python 3.12)
  - 入れ子 1,000 段は成功する
  - 入れ子 10,000 段は成功する
  - 入れ子 50,000 段はプロセスが SIGSEGV で終了する (終了コード 139)
- 変更前の `Sora::ConvertJsonValue()` から同一の実装で、リリース済みのバージョンにも存在する
- 深さの上限を設けることで、アプリケーションの入力起因でプロセスが落ちることを防げる

## 設計方針

- 変換中に深さを数え、上限を超えた場合は `nb::type_error` を送出する (`error_message` とは区別できるメッセージにする)
- 上限は実際に安全に処理できる深さから決める (例: 128)。上限値を決めた根拠をコメントに残す
- `int64` の範囲を超える整数とキーが文字列でない `dict` の挙動 (`RuntimeError`) は変更しない
- 境界値 (上限ちょうど / 上限 + 1) と、`list` / `dict` が混在する入れ子のテストを追加する

## 完了条件

- 深い入れ子を指定しても SIGSEGV せず、例外になること
- 上限以下の入れ子は従来どおり変換できること
- 追加したテストと既存のテストがすべて通ること

## 変更対象

- `src/sora_json.h` / `src/sora_json.cpp`
- `tests/` の JSON 変換のテスト
