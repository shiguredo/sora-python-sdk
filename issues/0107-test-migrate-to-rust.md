# 既存テストを Rust 実装へ移行し実 Sora に対して通す

- Created: 2026-09-16
- Completed: -
- Branch: feature/test-migrate-to-rust
- Polished: {YYYY-MM-DD}

## 目的

`tests/` の既存テストを sora-rust-sdk + PyO3 の実装へ移行し、実 Sora に対して通す。移行で前提が失われるテストを選別し、残すテストの合否基準を確定する。

## 現状

- `tests/` には 40 の Python ファイルがある。`api.py` / `client.py` / `conftest.py` / `simulcast.py` が共通で、残りがテストである。
- テストは実 Sora に対して接続し、`TEST_SIGNALING_URLS` / `TEST_CHANNEL_ID_PREFIX` / `TEST_API_URL` / `TEST_SECRET_KEY` などの環境変数を使う。`.env.template` が項目を定めている。
- 試作ブランチの `MEMO.md` が「旧 tests の選別結果」を記録している。通らないのは、encoded transform、degradation preference、切替継続の終了符号を求めるもの、同時配信の符号化器表記を求めるもの、単体転送選別器を求めるもの、機器依存のもの (Raspberry Pi 等) である。ファイル単位の特定は移行時に確定する。
- 現行のテストは `pytest` / `pytest-repeat` / `pytest-xdist` を使い、`pyproject.toml` の `testpaths` が `tests` を指す。
- 移行で作り替える `tests/` を前提にする open issue が 6 件ある (`0037` / `0038` / `0040` / `0041` / `0064` / `0065`)。

## 設計方針

- `docs/migration-to-sora-rust-sdk.md` の決定事項 18 と 19 に従う。
- モックとスタブを使わない (`shiguredo-python` 規約)。E2E は実 Sora に対して行う。
- テストのログメッセージは日本語にする。テスト関数の説明は docstring に書く。
- 上流の受け口が無い機能を検証するテストは、上流の依頼が受理されるまで移行しない。受理されない場合は該当のテストを削除し、その判断を記録する。
- 移行で作り替える `tests/` を前提にする 6 件の issue は、本 issue の中で 1 件ずつ処遇を判定する。判定結果は各 issue ファイルに記録する。判定は「移行で解消する / Rust 向けに起票し直す / そのまま残す」の 3 分類とする。
- pytest の実行時間が長い場合は `pytest-timeout` を導入し、timeout は 10 秒以内に収める。

## 完了条件

- 移行対象の既存テストが実 Sora に対して通ること。
- 移行しないテストとその理由が issue に記録されていること。
- `tests/` から移行対象のモジュールに対応するテストが揃っていること (`shiguredo-python` 規約のファイル命名に従う)。
- `tests/` を前提にする open issue 6 件の処遇が確定していること。
- モックとスタブを使っていないこと。

## 依存

- 先行: 受信系 API、送信系 API、コールバック中継、接続設定、リサンプラと VAD、libcamera の各 issue。
- 上流: 該当機能の依頼が受理されていること。
- 後続: ドキュメント追従の issue が本 issue に依存する。

## 解決方法
