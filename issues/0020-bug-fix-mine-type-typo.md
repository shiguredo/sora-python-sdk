# `SoraTransformableFrame` の Python 公開プロパティ `mine_type` を `mime_type` に修正する

- Priority: High
- Created: 2026-06-23
- Completed: 2026-07-16
- Model: Opus 4.7
- Branch: feature/fix-mine-type-typo

## 目的

`SoraTransformableFrame` の Python 公開プロパティ名が `mine_type` というタイポになっている (正しくは `mime_type`)。C++ 側のメソッド名は `GetMimeType` で正しく綴られており、nanobind バインディング側の文字列だけが誤っている。一度公開した API 名のため、無修正のままにすると Python 利用者が誤った属性名でコードを書き、後方互換性の負債が積み重なる。正式リリース前に修正する。

## 優先度根拠

High とする。

- 公開 API の名称誤り。正式リリース前ならまだ alias を用意して破壊的変更にせずに直せる時間的余裕がある。
- 正式リリース後に直すと既存利用者の `frame.mine_type` 参照を破壊するか、永遠に `mine_type` を残すかの二択になり、いずれも望ましくない。
- 修正は nanobind バインディング 1 行の追記 + 既存名の deprecation。コスト極小。

## 現状

`src/sora_sdk_ext.cpp:535`:

```cpp
.def_prop_ro("mine_type", &SoraTransformableFrame::GetMimeType);
```

C++ 側 `src/sora_frame_transformer.h:158`:

```cpp
std::string GetMimeType() { return std::move(frame_->GetMimeType()); }
```

Python 側からは `frame.mine_type` でアクセスする形になっており、`mime_type` という綴りでは AttributeError になる。`SoraTransformableFrame` は Encoded Transform で `on_transform_` コールバックに渡されるフレームのプロパティ。

## 設計方針

- `src/sora_sdk_ext.cpp:535` の文字列を `mime_type` に修正する。
- 後方互換のため、既存の `mine_type` プロパティを deprecated alias として残すかどうかを判断する。
  - alias を残す案: `.def_prop_ro("mime_type", &SoraTransformableFrame::GetMimeType)` と `.def_prop_ro("mine_type", &SoraTransformableFrame::GetMimeType)` の両方を bind し、Python 側で `DeprecationWarning` を発する仕組みを併設する。
  - alias を残さない案: 正式リリース前なら `mine_type` を直接削除する。canary バージョンしか公開されていない場合に妥当。
- `CHANGES.md` の `## develop` セクションに `[FIX]`（alias 残す場合）または `[CHANGE]`（alias 残さない場合）エントリを追加する。

## 完了条件

- `frame.mime_type` で Python 側から正しいプロパティとして MIME type が取得できる。
- alias を残す場合: `frame.mine_type` も当面動作し、利用時に deprecation 警告が出る。
- alias を残さない場合: `frame.mine_type` は AttributeError になり、CHANGES.md の `[CHANGE]` エントリで後方互換破壊を明示する。
- `tests/test_encoded_transform.py` の Encoded Transform テストで `frame.mime_type` 経由のアサーションが通ること。

## 解決方法

正式リリース前 (VERSION は `2026.1.0.dev12`) かつプロジェクト規約で後方互換を取らない方針のため、`mine_type` の alias は残さず削除した。

- `src/sora_sdk_ext.cpp` の `.def_prop_ro("mine_type", ...)` を `.def_prop_ro("mime_type", ...)` に書き換えた。型スタブ `sora_sdk_ext.pyi` はビルド時生成のため、次回ビルドで追随する。
- `CHANGES.md` の `## develop` に `[CHANGE]` エントリを追記した。
- `tests/test_encoded_transform.py` の sendonly / recvonly 双方の `on_transform` で `frame.mime_type` が `audio/` または `video/` で始まることを assert するよう追加した。
