# `Sora::ConvertForwardingFilter` と `ConvertForwardingFilters` の 30 行超の完全重複を共通ヘルパに切り出す

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/convert-forwarding-filter-dedup

## 目的

`Sora::ConvertForwardingFilter` (単一フィルタ用) と `Sora::ConvertForwardingFilters` (配列用) が、フィルタ 1 件をパースする `action` / `rules` / `version` / `metadata` / `name` / `priority` のすべての処理を 30 行以上にわたって完全重複させている。Sora の `forwarding_filter` / `forwarding_filters` 仕様に変更が入ったとき、片方を直してもう片方を直し忘れる事故が容易に起き、放置すると挙動の食い違いとして表面化する。フィルタ 1 件分のパースを共通ヘルパに集約し、単一版・配列版がそのヘルパに従う構造に直す。

## 優先度根拠

Medium とする。

- 現状で挙動が壊れているわけではないため High ではない。
- ただし 30 行を機械コピペしたコードを 2 箇所維持する状態は典型的な broken windows。`metadata` / `priority` の型解釈、`is_null()` ガードの位置、例外メッセージなど、片方だけ変えたい誘惑が常に発生する。
- 修正は private ヘルパ 1 関数の切り出しと呼び出し側 2 箇所の置換で済む。リスクが小さい割に重複削減効果が大きい。
- 一方で「2 箇所書いている現状でも動いている」ため、緊急対応ではない。Low に落とすほど軽微でもなく、Medium が妥当。

## 現状

### 単一フィルタ (`src/sora.cpp:382-428`)

```cpp
std::optional<sora::SoraSignalingConfig::ForwardingFilter>
Sora::ConvertForwardingFilter(const nb::handle value) {
  auto forwarding_filter_value =
      ConvertJsonValue(value, "Invalid JSON value in forwarding_filter");
  if (forwarding_filter_value.is_null()) {
    return std::nullopt;
  }

  sora::SoraSignalingConfig::ForwardingFilter filter;

  try {
    auto object = forwarding_filter_value.as_object();
    if (!object["action"].is_null()) {
      filter.action = std::string(object["action"].as_string());
    }
    for (auto or_rule : object["rules"].as_array()) {
      std::vector<sora::SoraSignalingConfig::ForwardingFilter::Rule> rules;
      for (auto and_rule_value : or_rule.as_array()) {
        auto and_rule = and_rule_value.as_object();
        sora::SoraSignalingConfig::ForwardingFilter::Rule rule;
        rule.field = and_rule["field"].as_string();
        rule.op = and_rule["operator"].as_string();
        for (auto value : and_rule["values"].as_array()) {
          rule.values.push_back(value.as_string().c_str());
        }
        rules.push_back(rule);
      }
      filter.rules.push_back(rules);
    }
    if (!object["version"].is_null()) {
      filter.version = std::string(object["version"].as_string());
    }
    if (!object["metadata"].is_null()) {
      filter.metadata = object["metadata"];
    }
    if (!object["name"].is_null()) {
      filter.name = std::string(object["name"].as_string());
    }
    if (!object["priority"].is_null()) {
      filter.priority = boost::json::value_to<int>(object["priority"]);
    }
  } catch (std::exception&) {
    throw nb::type_error("Invalid forwarding_filter");
  }

  return filter;
}
```

### 配列フィルタ (`src/sora.cpp:330-380`)

配列版は `forwarding_filter_value.as_array()` をループするだけで、ループの中身は単一版の `try` ブロックと完全一致する。`action` / `rules` / `version` / `metadata` / `name` / `priority` のいずれのパース処理も同じ式で書かれている。

## 設計方針

`ConvertSingleForwardingFilter(const boost::json::value&)` を private ヘルパとして切り出す。

```cpp
sora::SoraSignalingConfig::ForwardingFilter ConvertSingleForwardingFilter(
    const boost::json::value& v) {
  sora::SoraSignalingConfig::ForwardingFilter filter;
  try {
    auto object = v.as_object();
    if (!object["action"].is_null()) {
      filter.action = std::string(object["action"].as_string());
    }
    // ... 既存の rules / version / metadata / name / priority のパースをここに集約
  } catch (std::exception&) {
    throw nb::type_error("Invalid forwarding_filter");
  }
  return filter;
}
```

呼び出し側:

```cpp
std::optional<sora::SoraSignalingConfig::ForwardingFilter>
Sora::ConvertForwardingFilter(const nb::handle value) {
  auto v = ConvertJsonValue(value, "Invalid JSON value in forwarding_filter");
  if (v.is_null()) {
    return std::nullopt;
  }
  return ConvertSingleForwardingFilter(v);
}

std::optional<std::vector<sora::SoraSignalingConfig::ForwardingFilter>>
Sora::ConvertForwardingFilters(const nb::handle value) {
  auto v = ConvertJsonValue(value, "Invalid JSON value in forwarding_filters");
  if (v.is_null()) {
    return std::nullopt;
  }
  std::vector<sora::SoraSignalingConfig::ForwardingFilter> result;
  for (auto& elem : v.as_array()) {
    result.push_back(ConvertSingleForwardingFilter(elem));
  }
  return result;
}
```

例外メッセージ:

- 単一版・配列版で投げる例外メッセージは `"Invalid forwarding_filter"` で揃っているが、配列版で配列要素の何番目が不正かを示すヒント (例: `"Invalid forwarding_filter at index N"`) を出すかは判断ポイント。少なくとも既存の挙動を退化させない方針にする。

`as_object()` や `as_array()` が投げる例外のキャッチ位置・型は現状を維持する。

## 完了条件

- フィルタ 1 件分のパース処理が `ConvertSingleForwardingFilter` (または同等の private ヘルパ) に 1 か所だけ存在する状態になっていること。
- `ConvertForwardingFilter` / `ConvertForwardingFilters` がそのヘルパを呼び出すだけの薄いラッパになっていること。
- 既存テスト (forwarding_filter / forwarding_filters を使う E2E 含む) が通ること。
- フィルタの新しいフィールドを追加するときに修正箇所が 1 か所で済むこと。
