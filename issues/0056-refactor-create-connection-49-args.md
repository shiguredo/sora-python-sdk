# `Sora::CreateConnection` の 49 引数を 3 箇所で機械同期している巨大関数を構造体ベースに分割する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/create-connection-config-struct

## 目的

`Sora::CreateConnection` は約 49 個の引数を取る巨大関数で、宣言が `src/sora.h:103-156`、定義が `src/sora.cpp:34-243` にあり、さらに nanobind バインディング `src/sora_sdk_ext.cpp:733-820` で `"_a"` リテラル付きの引数列と `nb::sig` のシグネチャを「機械的に」同期させている。新しいパラメータを 1 つ追加するだけで、

1. `src/sora.h` の関数宣言
2. `src/sora.cpp` の関数定義 (引数列 + `config.xxx = ...` 代入)
3. `src/sora_sdk_ext.cpp` の `"_a"` 引数列
4. 必要なら `nb::sig` の手書きシグネチャ

の 3〜4 箇所を同時に編集しないとビルドが通らない、または通っても挙動がずれる、という負債が積み上がっている。

この構造を維持したまま新しい Sora 機能 (frame transformer, simulcast 系の追加 RID, forwarding filter の新フィールド等) を追加し続けるのは持続不能であり、`SoraConnectionConfig` のような中間構造体を経由する形に直す。

## 優先度根拠

Medium とする。

- 既存ユーザーから見える挙動は変わらないため緊急ではない。High ではない。
- ただし「新パラメータ追加のたびに 3〜4 箇所同時修正」状態は、レビュー時の見落としや片方だけ更新したミスを誘発し、過去にも実際に挙動と宣言の食い違いが起きやすい構造。今のうちに分割しておかないと、将来 Sora 側で追加された新パラメータをサポートするときの摩擦が線形に増える。
- 引数 49 の関数は人間がレビューで全項目チェックできる限界を越えており、broken windows と判定すべき水準。Low では収まらない。
- 一方で互換性影響が大きいため、即着手はせず設計判断 (config 構造体の粒度・公開範囲・Python 側 API) をまとめてから取り掛かる必要がある。「High で即着手」ではなく Medium が妥当。

## 現状

### C++ 宣言: 49 引数

`src/sora.h:103-156` (抜粋):

```cpp
nb::ref<SoraConnection> CreateConnection(
    const nb::handle& signaling_urls,
    const std::string& role,
    const std::string& channel_id,
    std::optional<std::string> client_id,
    std::optional<std::string> bundle_id,
    const nb::handle& metadata,
    const nb::handle& signaling_notify_metadata,
    nb::ref<SoraTrackInterface> audio_source,
    nb::ref<SoraTrackInterface> video_source,
    SoraAudioFrameTransformer* audio_frame_transformer,
    SoraVideoFrameTransformer* video_frame_transformer,
    std::optional<bool> audio,
    // ... 残り 30 行以上続く
    std::optional<webrtc::DegradationPreference> degradation_preference,
    std::optional<std::string> user_agent);
```

### C++ 定義側でも同じ並びを再現 (`src/sora.cpp:34-243`)

引数列を維持したまま、本文で `config.xxx = ...` の代入を 49 個並べている。

### nanobind バインディング (`src/sora_sdk_ext.cpp:733-820`)

```cpp
.def("create_connection", &Sora::CreateConnection,
     "signaling_urls"_a,
     "role"_a,
     "channel_id"_a,
     // ... 49 個の "_a" が続く
     nb::sig("def create_connection(...) -> SoraConnection"))
```

`"_a"` 列で引数名と既定値を指定し、必要に応じて `nb::sig` で手書きシグネチャを与える。引数の追加 / 並び替え / 既定値変更のたびに、C++ 宣言・C++ 定義・`"_a"` 列・`nb::sig` の 4 箇所を整合させる必要がある。

## 設計方針

中期 (本 issue で目指す姿):

1. `SoraConnectionConfig` 構造体を `src/sora.h` 付近に定義し、現在 49 個の引数で受け取っているフィールドをすべてここに集約する。signaling 必須 (URL / role / channel_id) と optional 群を 1 つの `struct` に押し込み、`std::optional<>` をフィールド側で表現する。
2. `Sora::CreateConnection(const SoraConnectionConfig&)` に置き換え、C++ 側の本体実装は `config.xxx` を `sora::SoraSignalingConfig` に転写する純粋なマッピングにする。
3. Python 側 API は `connect(config: SoraConnectionConfig)` または `connect(**kwargs)` のヘルパーを介す。後方互換のため、現状の `connect(signaling_urls=..., role=..., ...)` を一定期間維持できるラッパを残す。

短期 (中期に踏み出す前の防御策):

- 引数列を 1 か所のソースから生成する仕組みを導入する。例えば `.def` / `.h` / `.cpp` / `nb::sig` を 1 つの定義テーブル (`x-macros` or 簡易コード生成) から展開できれば、新パラメータ追加の同期作業が機械化される。
- 短期策単独では「巨大関数のままレビュー困難」問題は解決しないため、中期策を完了させるまでの暫定。

Python 側 API の互換性については CHANGES.md に明記し、`connect()` のシグネチャを変える場合は移行手順を案内する。

## 完了条件

- `Sora::CreateConnection` の引数列が `SoraConnectionConfig` などの構造体 1 つに集約され、`src/sora.h` / `src/sora.cpp` / `src/sora_sdk_ext.cpp` の引数列の機械同期が不要になっていること。
- 新しい接続パラメータを追加する際、C++ 構造体への 1 フィールド追加 + Python 側マッピング 1 行で済むこと (`.def` の `"_a"` 列・`nb::sig` の手書きが不要)。
- Python 側 API について、後方互換を維持する場合と切る場合のいずれかが選択され、選択結果が CHANGES.md に記載されていること。
- 既存の E2E テスト・サンプルコードが新しい API で動くこと。
