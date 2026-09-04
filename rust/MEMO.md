# プロトタイプのメモ

sora-rust-sdk ベースへの切り替え可否を判断するための試行記録である。

## 依存先

- リポジトリ: https://github.com/shiguredo/sora-rust-sdk
- クレート: `sora_sdk` (crates.io)
- 利用版: `2026.2.0-canary.2` (試行時点の最新。安定版の最新は `2026.1.0`)
- 同梱解決された主な版 (`Cargo.lock` より):
  - `shiguredo_webrtc` は `0.152.1-canary.3`
  - `pyo3` は `0.29.2`
  - `tokio` は `1.53.1`
- ビルドバックエンド: `maturin==1.14.1` (試行時点の最新)
- ライセンス: Apache-2.0 (sora_sdk、プロトタイプともに)

## 版参照手段

- Python からは `sora_rust_sdk.__version__` でプロトタイプ自体の版を参照する。
- sora_sdk 側に公開の版取得 API はない (`src/version.rs` は `pub(crate)` のみ)。
  そのため依存版は `Cargo.lock` に記録する運用とする。

## モジュール名

- 拡張モジュール名は `sora_rust_sdk` とした。
- 既存パッケージ `sora_sdk` と同名にすると import が衝突するため避けた。
- 全面移行時は `sora_sdk` 名の扱いを別途決める必要がある。

## `gil_used = false` の判定

- `#[pymodule(gil_used = false)]` を付けた。
- 理由: イベントハンドラは空実装で Python に触れず、blocking な接続処理は
  `Python::detach` で GIL を外して実行し、sora_sdk 側コールバックも
  Rust / tokio スレッド内で完結するため。

## sora_sdk の API 対応メモ

- 接続の組み立ては `SoraConnectionContext::new`、
  `SoraConnection::builder`、`build`、`connection.run` の順で行う。
- ロールは `Role::parse` で `"sendonly"` / `"recvonly"` / `"sendrecv"` を受けられる。
- 認証に access_token 概念はなく、JWT は `metadata` の JSON に載せる
  (既存 E2E と同じく `{"access_token": ...}` 形式)。
  JSON 文字列の検証には `JsonString` の `FromStr` を使う。
- イベントハンドラは `SoraConnectionEventHandler` を空実装するだけでよい
  (全メソッドにデフォルト空実装あり。実装型に要求されるのは `Send` のみ)。
- 切断は `SoraConnectionHandle::disconnect` を別タスクから呼ぶ。
  `run` は切断までブロックするため、指定秒数後に切断するタスクを spawn した。
- ランタイムは sora_sdk の利用例と同じ current-thread を使った。

## PyO3 0.29 での差分

- `#[pyattr]` は廃止されていたため、関数形式の `#[pymodule]` で
  `m.add("__version__", ...)` する形にした。
- `Python::allow_threads` は廃止されていたため、`Python::detach` を使う。

## 検証結果

- `uv run maturin build` で wheel を生成できる。
- `uv run maturin develop` で venv に導入し、`import sora_rust_sdk` できる。
- 引数検証 (空 URL、不正 role、空 channel_id、不正 JSON、不正 duration) は
  `ValueError` で弾けることを確認した。
- `check_connect.py` で実 Sora に recvonly 接続し、PeerConnection の Connected と
  DataChannel 群の open を経て切断できることを確認した (終了コード 0)。
  接続設定は既存 E2E と同じ環境変数を使った。

## 後続作業の洗い出し

- イベントコールバックの Python 中継設計 (GIL 取得スレッド、キュー方式の検討)。
- 送信トラック (音声 / 映像) 対応とフレーム受け渡し方式の決定。
- 既存 `sora_sdk` Python API との対応表と移行単位の切り分け。
- ビルド体系の置き換え (CMake / setup.py / run.py の扱いと対応 platform)。
- E2E テストの移行と CI 組み込み。
- wheel 公開名とモジュール名 (`sora_sdk` 衝突) の最終決定。
