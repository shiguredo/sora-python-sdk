# デフォルト User-Agent 文字列が "Sora Unity SDK" になっているのを "Sora Python SDK" に修正する

- Priority: High
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-user-agent-says-unity-sdk

## 目的

`Sora::CreateConnection` で `user_agent` を呼び出し側が指定しなかった場合のデフォルト User-Agent 文字列が、別 SDK である `Sora Unity SDK` のままになっている。Sora Python SDK が Sora サーバ側で `Sora Unity SDK` として観測される運用上のバグ。Sora サーバの統計・接続ログでクライアント識別を誤らせ、Python SDK 利用者の振る舞いが Unity SDK のものとして集計される。

## 優先度根拠

High とする。

- 公開リリースされる SDK のデフォルト挙動が他 SDK を名乗っており、ブランド・統計・サポート切り分けの全てに影響する。
- 修正は文字列 1 箇所の書き換えで、副作用は無い。
- 同じファイル 226 行目の `config.sora_client` は `Sora Python SDK` で正しく、対比でコピペバグが明白。CHANGES.md 過去エントリ (2025.5.0 リリースの「sora_client に "Sora Python SDK {PYTHON_SDK_VERSION}" を設定する」) とも矛盾している。

## 現状

`src/sora.cpp:217-220`:

```cpp
// 無指定時はデフォルトの User-Agent を設定する
config.user_agent = std::optional<std::string>(
    "Mozilla 5.0 (Sora Unity SDK/" BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION) ")");
```

直後の `src/sora.cpp:225-226`:

```cpp
config.sora_client =
    "Sora Python SDK " BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION);
```

`sora_client` は正しく `Sora Python SDK` を名乗っているのに、`user_agent` だけが `Sora Unity SDK` のまま。明確なコピペ取り残し。

## 設計方針

`src/sora.cpp:219` の `Sora Unity SDK` を `Sora Python SDK` に修正する。`sora_client` と同じ書式・順序にする。

`CHANGES.md` の `## develop` セクションに `[FIX]` エントリを追加する (`shiguredo-changelog` 規約に従う)。

## 完了条件

- `src/sora.cpp` 内に `Sora Unity SDK` の文字列リテラルが存在しないこと。
- ユーザーが `user_agent` を指定せずに `Sora::CreateConnection` を呼んだとき、Sora サーバへ送出される User-Agent ヘッダが `Mozilla 5.0 (Sora Python SDK/<version>)` であること。
- `CHANGES.md` の `## develop` セクションに `[FIX]` エントリが追加されていること。
