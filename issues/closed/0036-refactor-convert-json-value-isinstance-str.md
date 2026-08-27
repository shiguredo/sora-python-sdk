# Sora::ConvertJsonValue の文字列判定・取得を nb::str / std::string ベースに統一する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/refactor-convert-json-value-isinstance-str
- Completed: 2026-08-01
- Polished: 2026-07-30

## 目的

`src/sora.cpp` の `Sora::ConvertJsonValue` は文字列の型判定に `nb::isinstance<const char*>(value)` を、値取得に `nb::cast<const char*>(value)` を使っている。nanobind では Python オブジェクトの型判定に `nb::isinstance<nb::str>` を使うのが慣用であり、`const char*` での判定は意図が読み取りづらい。また `nb::cast<const char*>` が返すポインタのライフタイムは Python 側 `str` オブジェクトに依存するため、コード読者にとって安全性が自明でない。本 issue では型判定と値取得を `nb::str` / `std::string` ベースに書き換え、nanobind の慣用に揃えて可読性を上げる。

## 優先度根拠

Medium とする。

- 現行コードでは `nb::cast<const char*>` の戻り値を同一フル式内で `boost::json::value` に渡しており、`boost::json::value(string_view)` が即座にコピーを取るため、ライフタイムバグは成立しない。直ちに変更しなければ壊れるわけではない。
- 一方で nanobind の慣用と乖離した書き方は後続の修正者が読み解きづらく、同種の書き方が他の場所にコピーされやすい。可読性・一貫性の観点から早期に揃える価値がある。
- 修正は 3 箇所の型・cast 差し替えで済み、振る舞いが変わらないためリスクが低い。

## 現状

`src/sora.cpp` の `Sora::ConvertJsonValue` 関数の該当箇所は以下の通り。

```cpp
} else if (nb::isinstance<const char*>(value)) {
  return nb::cast<const char*>(value);
}
```

加えて同関数内の dict の key 取得でも `nb::cast<const char*>(k)` が使われており、文字列の扱いに `const char*` が散在している。

## 設計方針

- 型判定: `nb::isinstance<const char*>(value)` を `nb::isinstance<nb::str>(value)` に変更する。
- 値取得: `nb::cast<const char*>(value)` を `nb::cast<std::string>(value)` に変更し、`std::string` で明示的にコピーを取る。`std::string` は `boost::json::value(string_view)` コンストラクタへの暗黙変換でそのまま代入可能。
- dict の key 取得 (`nb::cast<const char*>(k)`) も同様に `nb::cast<std::string>(k)` に揃える。
- 振る舞いは変わらない。現行の `nb::isinstance<const char*>` も内部的に `PyUnicode_Check` を使うため `str` のみを受け付け、`bytes` は既に `throw nb::type_error` に落ちる。`nb::isinstance<nb::str>` も同様に `str` のみを受け付けるため、`bytes` 入力の挙動は変更前後で同一である。
- 関数シグネチャの `const char* error_message` パラメータは C 文字列リテラルであり、Python オブジェクトの `const char*` 扱いとは無関係のため本 issue の対象外。

## 完了条件

- `Sora::ConvertJsonValue` 内の文字列判定が `nb::isinstance<nb::str>` を使う形になっていること。
- 文字列取得が `nb::cast<std::string>` 経由になっており、生の `const char*` を `boost::json::value` まで持ち回らないこと。
- dict の key も同様に `std::string` 経由になっていること。
- 既存の e2e テスト・ユニットテストが引き続き通ること。
- Python 側のユースケース (`metadata` などに任意の文字列キー・値を渡すケース) で挙動が変わらないこと。

## 解決方法

`Sora::ConvertJsonValue` の文字列判定・取得を `nb::isinstance<nb::str>` / `nb::cast<std::string>` ベースに統一した。

- 型判定: `nb::isinstance<const char*>(value)` を `nb::isinstance<nb::str>(value)` に変更した。
- 値取得: `nb::cast<const char*>(value)` を `nb::cast<std::string>` に変更し、`std::string` で明示的にコピーを取るようにした。
- dict の key 取得 (`nb::cast<const char*>(k)`) も `nb::cast<std::string>(k)` に揃えた。
- `nanobind/stl/string.h` をインクルードした (`nb_cast.h` には `std::string` の caster が無いため)。
- 設計方針の「`std::string` は `boost::json::value(string_view)` コンストラクタへの暗黙変換でそのまま代入可能」は誤りだった。`std::string` → `string_view` → `value` は 2 段階のユーザー定義変換になりコンパイルできないため、`boost::json::string` を明示的に挟んで `boost::json::value(boost::json::string(s))` とした。
- `CHANGES.md` の `## develop` → `### misc` に [UPDATE] を追記した。
