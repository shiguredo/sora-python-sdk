# Sora::ConvertJsonValue の int キャストを int64_t に変更し int32 範囲超で例外になる問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Completed: 2026-07-28
- Model: Opus 4.7
- Branch: feature/fix-convert-json-value-int32-truncation

## 目的

`src/sora.cpp` の `Sora::ConvertJsonValue` は Python の値を `boost::json::value` に変換するルーチンで、整数の分岐で `nb::cast<int>(value)` を使っている。Python の `int` は任意精度整数なので 32bit `int` の範囲を簡単に超え、その場合 nanobind が変換時に例外を投げる。Sora の API では JWT の `exp` などタイムスタンプ系・大きな ID・ビットレートの累計など `int64_t` 範囲の値を JSON にそのまま乗せたいケースが普通にあり、現状の実装ではユーザが何も間違えていなくても例外で落ちる。本 issue では `nb::cast<int64_t>` に切り替え、`boost::json::value` が int64 を受け取れる性質も活かして 64bit までは安全に通るようにする。

## 優先度根拠

Medium とする。

- 「2^31 を超える整数を JSON 値として渡すと例外で落ちる」というのは、利用者から見ると素直な使い方でいきなり当たる落とし穴で、しかも症状の分かりにくさが地味に厄介。
- 修正は型を `int` → `int64_t` に差し替える程度で済み、リスクは低い。
- ただし変換先の `boost::json::value` の挙動と、Python 側 `bool` が `int` のサブクラスである点 (分岐順序) は確認が必要。これらを丁寧に押さえれば High ではなく Medium 相当として潰せる。

## 現状

`src/sora.cpp` の `ConvertJsonValue` の該当箇所は以下の通り。

```cpp
boost::json::value Sora::ConvertJsonValue(nb::handle value,
                                          const char* error_message) {
  if (value.is_none()) {
    return nullptr;
  } else if (nb::isinstance<bool>(value)) {
    return nb::cast<bool>(value);
  } else if (nb::isinstance<int>(value)) {
    return nb::cast<int>(value);
  } else if (nb::isinstance<float>(value)) {
    return nb::cast<float>(value);
  } else if (nb::isinstance<const char*>(value)) {
    return nb::cast<const char*>(value);
  } else if (nb::isinstance<nb::list>(value)) {
    ...
```

- `nb::cast<int>(value)` は C++ の `int` 型 (通常 32bit) に変換するため、`int` の表現範囲を超える Python 整数は変換できず、nanobind が例外を送出する。
- Python の `int` は任意精度整数で、JWT の `exp` (Unix 秒) や大きなビットレート積算値、64bit ID など、`int32` 範囲を簡単に超える値が日常的に登場する。
- `boost::json::value` は `int64_t` を受け取れる API を持っており、変換先での精度低下も発生しない。
- なお Python では `bool` が `int` のサブクラスであるため、`nb::isinstance<bool>(value)` のチェックを `nb::isinstance<int>(value)` の前に置く必要がある。現コードは正しい順序になっているため、本修正では順序を維持する。

## 設計方針

- `nb::cast<int>(value)` を `nb::cast<int64_t>(value)` に変更する。`boost::json::value` の暗黙変換コンストラクタが `int64_t` を受け取れることを前提にする (受けられない場合は明示的に `int64_t` を渡すラッパ経由にする)。
- Python 側で `int64` 範囲を超える整数 (例: 256bit ID) を渡すケースは現実的にレアだが、もし必要なら別途 `OverflowError` のような明示的なエラー文言で例外を投げる検討の余地はある。本 issue ではまず int64 までを安全に通すことに集中する。
- `bool` 分岐が `int` 分岐より先に評価される順序を維持し、`True` / `False` が `1` / `0` の整数として扱われないようにする (現状維持)。
- `nb::cast<int64_t>(value)` の戻り値を直接 `boost::json::value` に代入できることをローカルでビルドして確認する。

## 完了条件

- Python から `int32` 範囲を超える整数 (例: `2 ** 40`) を JSON 値として渡しても例外にならず、`boost::json::value` 側でも値が保存されること。
- 既存の `int32` 範囲内の整数で動作が変わらないこと。
- `bool` の `True` / `False` が引き続き bool として変換され、`0` / `1` の整数として誤分類されないこと。
- 既存の e2e テスト・ユニットテストが引き続き通ること。
- 必要であれば `ConvertJsonValue` 経路を直接呼ぶ Python テストを追加し、大きな整数値の往復が壊れないことを確認する。

## 解決方法

コミット `1636221` (PR #345) で `src/sora.cpp:336` の `nb::cast<int>(value)` を `nb::cast<int64_t>(value)` に変更済み。`bool` 分岐は先に維持されている。CHANGES.md の develop セクションに `[FIX]` エントリ記載済み。
