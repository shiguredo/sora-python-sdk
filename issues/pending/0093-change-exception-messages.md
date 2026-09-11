# 例外発生時のメッセージが std::exception だけにならないようにする

- Created: 2026-09-11
- Completed: -
- Branch: feature/change-exception-messages
- Polished: -
- Reporter: @voluntas

## 目的

C++ 側で例外が発生したときに、Python へ情報の乏しいメッセージだけが渡るのを改善し、原因を特定できるようにする。

## 現状

- nanobind は捕捉していない C++ の例外を Python の例外に変換する。`std::exception` 系は `RuntimeError` に変換され、メッセージに `what()` が使われる。
- 投げられた例外が `std::exception` そのものだと `what()` が `std::exception` になり、発生箇所も例外の種類も分からない。実際に E2E テストで `FAILED test_invalid_rtp.py::test_invalid_rtp_payload - RuntimeError: std::exception` が発生した。
- どのコードが `std::exception` を投げているかは特定できていない。libwebrtc / Sora C++ SDK 側の可能性がある。
- Python SDK 側に独自の例外翻訳 (`nb::register_exception_translator`) は入っていない。

## 設計方針

保留を解除したら、まず `std::exception` がどこで投げられているかを特定する。

- `std::exception` を投げている箇所を特定し、意味のある例外型とメッセージに置き換える。libwebrtc / Sora C++ SDK 側であれば上流に依頼する。
- `nb::register_exception_translator()` で C++ の例外型を意味のある Python 例外に変換する。
- Python SDK 側で C++ の呼び出しをラップし、どの操作で失敗したかのコンテキストをメッセージに含める。
- 例外を投げる側と翻訳する側のどちらで情報を付与するかの方針を決める。

## 完了条件

- 例外発生時に、原因を特定できるメッセージを持つ Python 例外が得られる。
- `RuntimeError: std::exception` のような情報の無いメッセージが出なくなる。
- `tests/` に例外メッセージを確認するテストがある (再現するテストが作れる場合)。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- `std::exception` がどこで投げられているかが未特定。
- libwebrtc / Sora C++ SDK 側の対応が必要かどうかが未確認。
- 例外の情報を Python SDK 側で付与するか、投げる側で付与するかの設計が未確定。
- 再現するテストを作れるかどうかが未確認。

再開するときは reopened にしてから実装を進める。
