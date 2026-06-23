# Sora::ConvertJsonValue で nb::isinstance<const char*> を nb::isinstance<nb::str> に置き換える

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/refactor-convert-json-value-isinstance-str

## 目的

`src/sora.cpp` の `Sora::ConvertJsonValue` は文字列判定に `nb::isinstance<const char*>(value)` を使い、続けて `nb::cast<const char*>(value)` で値を取り出している。nanobind の慣用としては Python オブジェクトの型判定には `nb::isinstance<nb::str>` を使うべきで、`const char*` での判定は意図が読み取りづらい上、取り出した `const char*` のライフタイムが Python 側 `str` オブジェクトの生存期間に縛られて危険な書き方になりやすい。`boost::json::value` への代入時には内部でコピーされるはずだが、依存はせず明示的に `std::string` でコピーを取った方が安全で読みやすい。本 issue では型判定と値取得を `nb::str` ベースに書き換え、関数全体を nanobind の慣用に揃える。

## 優先度根拠

Medium とする。

- 直ちにバグを引き起こす書き方ではないが、`const char*` のライフタイムは Python オブジェクトに紐付くため、保持の仕方を間違えると即時クラッシュにつながる脆い書き方。
- nanobind の慣用と乖離しているため、後続の修正者が読み解きづらく、同種の脆さを他の場所にコピーされやすい。
- 修正自体は型と cast を 2 行差し替える程度で済み、リスクが低い。観測される実害ゼロでも、`const char*` のライフタイム管理のような潜在的に危険な書き方は早期に潰すべきため High ではなく Medium とする。

## 現状

`src/sora.cpp` の該当箇所は以下の通り。

```cpp
} else if (nb::isinstance<const char*>(value)) {
  return nb::cast<const char*>(value);
}
```

加えて同関数内の dict の key 取得でも `nb::cast<const char*>(k)` が使われており、文字列の扱いに `const char*` が散在している。

- `nb::isinstance<const char*>(value)` は nanobind 上は動作するが、`nb::isinstance` の慣用テンプレート引数として `nb::str` を渡すのが nanobind 流である。
- `nb::cast<const char*>(value)` で取り出した `const char*` は `value` (= 元の `nb::str`) が生存している間しか有効でなく、`boost::json::value` への代入で内部コピーが取られるかどうかはコード読者にとって自明でない。明示的に `std::string` を経由した方が安全で読みやすい。
- 同関数内の dict の key も同じ書き方で、まとめて整理した方が一貫性が出る。

## 設計方針

- 型判定: `nb::isinstance<const char*>(value)` を `nb::isinstance<nb::str>(value)` に変更する。
- 値取得: `nb::cast<const char*>(value)` を `nb::cast<std::string>(value)` に変更し、`std::string` でコピーを取る。`boost::json::value` は `std::string` も `string_view` 経由で受け取れるため、`boost::json::value(nb::cast<std::string>(value))` のような形でそのまま代入可能 (本実装でも `return` 文の文脈で成立)。
- dict の key 取得 (`nb::cast<const char*>(k)`) も同様に `nb::cast<std::string>(k)` に揃える。`boost::json::object::emplace` は `string_view` を受けるため、引数として `std::string` を渡しても問題ない。
- 振る舞いは型レベルで変わらないが、Python の `bytes` を渡してきた場合に分岐がどう動くかなど、エッジケースの挙動を変えないよう注意する。`nb::str` は `bytes` を受けないため、本来意図されていない `bytes` 入力は最後の `throw nb::type_error(error_message)` に落ちる挙動になる (これは妥当)。

## 完了条件

- `Sora::ConvertJsonValue` 内の文字列判定が `nb::isinstance<nb::str>` を使う形になっていること。
- 文字列取得が `nb::cast<std::string>` 経由になっており、生の `const char*` を `boost::json::value` まで持ち回らないこと。
- dict の key も同様に `std::string` 経由になっていること。
- 既存の e2e テスト・ユニットテストが引き続き通ること。
- Python 側のユースケース (`metadata` などに任意の文字列キー・値を渡すケース) で挙動が変わらないこと。
