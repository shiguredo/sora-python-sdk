# SoraFactory コンストラクタの throw std::exception() を意味のあるメッセージ付き例外に置き換える

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-sora-factory-throw-exception-without-message
- Polished: 2026-07-28

## 目的

`src/sora_factory.cpp` の `SoraFactory` コンストラクタは `sora::SoraClientContext::Create(context_config)` が `nullptr` を返した場合に `throw std::exception();` だけを投げており、メッセージを持たない例外として Python 側に伝播する。Python から `SoraFactory(...)` をインスタンス化した瞬間に発生するため、初期化失敗の原因 (OpenH264 のロード失敗・コーデックファクトリ生成失敗など) を切り分ける手掛かりが何も得られない。本 issue では、原因に辿り着くために必要な最低限の文脈を含むメッセージ付き例外に置き換え、ユーザおよびサポート対応者が一次切り分けを進められるようにする。

## 優先度根拠

Medium とする。

- 正常系の動作には影響しないが、初期化失敗という最も再現困難で問い合わせコストの高いケースで、原因不明のまま `std::exception` だけが上がるのは利用者・開発者双方にとって体験が悪い。
- 修正は 1 行を `std::runtime_error("...")` に変更する程度で済み、リスクが極小。
- ただし `SoraClientContext::Create` 失敗の原因は OpenH264 のロード失敗・PeerConnectionFactory の依存生成失敗など複数の経路がありえ、メッセージの設計には少しだけ意図が必要。即時バグというより「不親切なエラー報告」の改善であるため High ではなく Medium とする。

## 現状

`src/sora_factory.cpp` の該当箇所は以下の通り。

```cpp
context_ = sora::SoraClientContext::Create(context_config);
if (context_ == nullptr) {
  throw std::exception();
}
```

- `std::exception` の既定コンストラクタはメッセージを持たず、`what()` は実装依存の固定文字列 (例: `std::exception`) を返すのみ。nanobind の例外ブリッジを通すと Python 側では `RuntimeError` 相当として上がるが、`message` はほぼ空となり、初期化失敗の原因切り分けに使えない。
- `context_` が `nullptr` になる経路は `sora::SoraClientContext::Create` の内部失敗 (PeerConnectionFactory の依存生成失敗・OpenH264 等の動的ロード失敗・スレッド作成失敗など) を集約したものだが、現在のコードからは「どの段階で失敗したか」「ユーザに何を確認すべきか」が全く伝わらない。
- 同プロジェクト内の他ファイル (`sora_connection.cpp` 等) では `std::runtime_error` を使っており、一貫性を欠いている。

## 設計方針

- `throw std::exception();` を `throw std::runtime_error("Failed to create SoraClientContext");` のようにメッセージ付き例外へ置き換える。メッセージは libwebrtc のログ規約 (英語) に合わせる。
- 可能であれば「どの設定が効いているとき何が失敗しがちか」のヒントを含める (例: `openh264` を渡している場合は OpenH264 のロード失敗を疑う旨を示唆できると望ましいが、過剰になるなら最初のステップではシンプルな固定メッセージで十分)。
- 例外型は `std::runtime_error` が無難。nanobind は `std::runtime_error` を Python の `RuntimeError` に自動変換するため、Python 側のユーザは `try/except RuntimeError as e: print(e)` で具体的なメッセージを得られる。
- `src/` 全体で `throw std::exception()` の素投げが他に残っていないことを確認する (現状 `sora_factory.cpp:65` の 1 箇所のみ)。

## 完了条件

- `SoraClientContext::Create` が `nullptr` を返したケースで投げられる例外が、Python 側で `RuntimeError` として上がり、メッセージから「Sora の初期化に失敗したこと」が読み取れること。
- `src/` 全体に `throw std::exception();` (メッセージ無し) が残っていないこと。
- 既存の動作 (正常系) に影響がないこと。
