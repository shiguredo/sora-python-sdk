# コールバック内で例外が発生するとプロセスが SIGABRT で異常終了する問題を修正する

- Created: 2026-10-10
- Completed: -
- Branch: feature/fix-callback-exception-abort
- Polished: {YYYY-MM-DD}

## 目的

`on_message` / `on_rpc` などのコールバック内で Python の例外が発生すると、プロセスが SIGABRT (終了コード 134) で異常終了する。アプリケーション側のバグが原因であっても SDK がプロセスごと落とすのは望ましくなく、原因もログ以外からは分からない。

## 現状

- `src/sora_call.h` の `call_python()` は例外をキャッチしてログ出力したあと `throw;` で再送出している
- 再送出された例外は SDK のスレッドを越えるため処理されず、`std::terminate` を経由して SIGABRT になる
- 実測 (macOS arm64)
  - `on_rpc` の中で `ValueError` を送出すると終了コード 134
  - `on_rpc` の中で `send_rpc()` が `TypeError` になった場合も終了コード 134
  - 変更していない既存の `on_message` の中で `ValueError` を送出しても終了コード 134
- `call_python()` はすべてのコールバック経路で使われている

## 設計方針

- `call_python()` で例外を再送出せず、ログ出力のみにする (プロセスを落とさないことを優先する)
- ログには例外の内容が残るため、アプリケーションは `RTC_LOG` の出力から原因を確認できる
- 例外を握りつぶす判断に伴い、`skills/sora-python-sdk/SKILL.md` の注意点に「コールバック内で例外を投げても SDK がログに出すだけでプロセスは落ちない」旨を追記する
- 例外をアプリケーションに通知する API の追加は、この issue の範囲外とする

## 完了条件

- コールバック内で Python の例外が発生してもプロセスが異常終了しないこと
- 例外の内容がログに残ること
- 既存のテストがすべて通ること

## 変更対象

- `src/sora_call.h`
- `skills/sora-python-sdk/SKILL.md`
