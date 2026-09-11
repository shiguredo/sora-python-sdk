# コールバック内で例外が発生したときに abort になるのを防ぐ

- Created: 2026-09-11
- Completed: -
- Branch: feature/fix-callback-exception-abort
- Polished: -
- Reporter: @voluntas

## 目的

`on_notify` / `on_disconnect` などの Python コールバック内で `assert` などが失敗した場合に、プロセスが abort せず、失敗を確認できるようにする。

## 現状

- `src/sora_call.h` の `call_python()` は `nanobind::python_error` / `std::exception` を catch して RTC_LOG に出力したあと rethrow する。
- `call_python()` の呼び出し元は `src/sora_connection.cpp` の `OnDisconnect` / `OnNotify` / `OnPush` / `OnMessage` / `OnRpc` / `OnSwitched` / `OnSignalingMessage` / `OnWsClose` / `OnTrack` / `OnDataChannel` などで、いずれも Sora C++ SDK のスレッドから呼ばれる。
- これらの関数から C++ の例外が抜けると、Sora C++ SDK 側で捕捉されないため `std::terminate` を経由して abort になりうる。コールバック内の `assert` の失敗でプロセスが落ちるのはこの経路と考えられる。
- コールバックの失敗を利用者に伝える仕組み (エラー通知) は無い。

## 設計方針

保留を解除したら、コールバックの例外をどう扱うかを決める。

- `call_python()` で例外を rethrow せず、RTC_LOG に残して握り潰す。1 回のコールバック失敗でプロセスを落とさない。
- 握り潰すだけだと利用者が気付けないため、失敗を通知する方法 (エラーコールバック、ログ、例外内容の保持) を検討する。
- rethrow を続ける場合は、呼び出し元で確実に捕捉して abort させない形にする。
- `on_track` のようにフレーム処理の途中で呼ばれるコールバックと、`on_disconnect` のように終了処理中に呼ばれるコールバックで扱いを変える必要があるかを確認する。

## 完了条件

- コールバック内で例外が発生してもプロセスが abort しない。
- コールバックの失敗が利用者に伝わる、またはログから原因を追える。
- `tests/` にコールバック内で例外を発生させてもプロセスが落ちないことを確認するテストがある。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- 例外を握り潰すか、何らかの形で利用者へ通知するかの設計が未確定。
- コールバックごとに扱いを変える必要があるかが未確認。
- nanobind の `python_error` を C++ 側で握り潰した場合の Python 例外状態の後始末方法の確認が必要。

再開するときは reopened にしてから実装を進める。
