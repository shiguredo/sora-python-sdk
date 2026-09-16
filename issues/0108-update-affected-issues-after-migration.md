# 移行で影響を受ける既存 issue の処遇を確定する

- Created: 2026-09-16
- Completed: -
- Branch: feature/update-affected-issues-after-migration
- Polished: {YYYY-MM-DD}

## 目的

移行で前提が失われる既存 issue を 1 件ずつ判定し、閉じるもの・Rust 向けに起票し直すもの・そのまま残すものを確定する。判定を放置すると、存在しない C++ 実装や削除済みのビルド基盤を前提にした issue が残り続ける。

## 現状

移行で影響を受ける issue は 44 件で、3 分類に分かれる。

- C++ 実装 (`src/`)、C++ 用ビルド基盤 (`CMakeLists.txt` / `setup.py` / `run.py` / `buildbase.py` / `pypath.py` / `sysroot_builder.py` / `DEPS`)、nanobind、削除対象の `.github/workflows/build.yml` / `dev.py`、Jetson、または現行 Python API の引数形を前提にするもの: open 14 件 (`0044` / `0050` / `0055` / `0056` / `0059` / `0062` / `0068` / `0075` / `0076` / `0077` / `0081` / `0082` / `0083` / `0097`)、pending 18 件 (`0043` / `0045` / `0072` / `0073` / `0078` / `0079` / `0080` / `0084` / `0085` / `0086` / `0087` / `0088` / `0089` / `0091` / `0092` / `0093` / `0095` / `0096`)
- 現行の WebRTC スタック (Sora C++ SDK が使う libwebrtc) の挙動を前提にするもの: open 1 件 (`0015`)、pending 1 件 (`0090`)
- 移行で作り替える `tests/` を前提にするもの: open 6 件 (`0037` / `0038` / `0040` / `0041` / `0064` / `0065`)。この 6 件はテスト移行の issue で扱う。

Jetson は移行後に再構築する方針であり、`issues/pending/` の Jetson 4 件は pending のまま残す。

## 設計方針

- `docs/migration-to-sora-rust-sdk.md` の決定事項 17 と 19 に従う。
- 本 issue は上記 3 分類のうち、テストを前提にする 6 件を除く 38 件を扱う。
- 1 件ずつ次の 3 分類で処遇を判定する。
  - 移行で解消する: 対象のコードが消える、または移行により問題自体が発生しなくなる。closed にする。
  - Rust 向けに起票し直す: 問題は残るが対象が Rust 実装へ変わる。新しい issue を起票して元の issue を closed にする。
  - そのまま残す: 対象が移行の影響を受けない。状態を変えない。
- 判定は推測で行わない。移行後のコードを実際に読んで確認する。
- 判定の根拠を各 issue ファイルに記録する。closed にする場合は `shiguredo-issues` 規約に従い、理由の追記コミットと移動コミットに分ける。
- pending の issue は勝手に closed にしない。pending から closed にする判断はユーザーに確認する。
- 新しい issue を起票する場合は `create-issue` スキルを使い、`issues/SEQUENCE` を更新する。

## 完了条件

- 対象 38 件すべてについて処遇が確定し、判定の根拠が各 issue ファイルまたは本 issue に記録されていること。
- 移行で解消する issue が closed になっていること。
- Rust 向けに起票し直す issue が新規に起票されていること。
- 判定結果の一覧が `docs/migration-to-sora-rust-sdk.md` に反映されていること。

## 依存

- 先行: 受信系 API、送信系 API、コールバック中継、接続設定、リサンプラと VAD、libcamera の各 issue。移行後のコードが確定している必要がある。
- 上流: 無し。
- 後続: ドキュメント追従の issue が本 issue に依存する。

## 解決方法
