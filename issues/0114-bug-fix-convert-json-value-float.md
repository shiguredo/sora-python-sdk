# `ConvertJsonValue()` が float32 で厳密に表現できる浮動小数点数しか変換できない問題を修正する

- Created: 2026-10-10
- Completed: -
- Branch: feature/fix-convert-json-value-float
- Polished: {YYYY-MM-DD}

## 目的

`metadata` や `send_rpc()` の `params` に Python の `float` を指定したとき、float32 で厳密に表現できない値 (`0.1` など) が `TypeError` になる問題を修正する。Python の `float` は JSON の数値として扱えるのが自然であり、`0.1` のような一般的な値が弾かれるとアプリケーションは原因の分かりにくい失敗に直面する。

## 現状

- `src/sora_json.cpp` の `ConvertJsonValue()` は `nb::isinstance<float>` で判定し `nb::cast<float>` で変換している
- nanobind の `load_f32()` は `cast_flags::convert` なしでは「float32 に丸めた値が元の値と一致する」場合だけ変換に成功するため、`nb::isinstance<float>` は `0.1` のような値で false になる
- 実測 (Python 3.12 / nanobind 3.1.0)
  - `metadata={"v": 0.5}` / `1.5` / `2.0` / `0.25` / `1e10` は成功
  - `metadata={"v": 0.1}` / `0.2` / `123.456` / `1e-10` / `1e300` は `TypeError: Invalid JSON value in metadata`
  - `send_rpc(1, method, {"v": 0.1})` は `TypeError: Invalid JSON value in params`
- 影響範囲は `ConvertJsonValue()` を使うすべての引数 (`metadata` / `signaling_notify_metadata` / `forwarding_filter` / `forwarding_filters` / 各コーデックパラメータ / `data_channels` / `send_rpc()` の `params`)
- `boost::json::value` は `double` を保持できるため `float` に落とす必要はない
- 変更前の `Sora::ConvertJsonValue()` から同一の実装で、リリース済みのバージョンにも存在する

## 設計方針

- `nb::isinstance<float>` / `nb::cast<float>` を `nb::isinstance<double>` / `nb::cast<double>` に変更する
- float32 で厳密に表現できる値は double でも同じ数値になるため、既存で成功していた入力の JSON の数値は変わらない。この点はテストで確認する
- `inf` / `nan` の扱いが変わらないことも確認する
- `int64` の範囲を超える整数とキーが文字列でない `dict` の挙動 (`RuntimeError`) は変更しない
- `skills/sora-python-sdk/SKILL.md` の float32 に関する記述を実態に合わせて更新する

## 完了条件

- `metadata={"v": 0.1}` のように float32 で厳密に表現できない浮動小数点数を指定しても例外にならないこと
- `send_rpc(1, method, {"v": 0.1})` が送信できること
- float32 で厳密に表現できる値の変換結果が変わらないこと
- 追加したテストと既存のテストがすべて通ること

## 変更対象

- `src/sora_json.cpp`
- `tests/` の JSON 変換のテスト (`tests/test_convert_json_value_int64.py` と同種のテストを追加する)
- `skills/sora-python-sdk/SKILL.md`
