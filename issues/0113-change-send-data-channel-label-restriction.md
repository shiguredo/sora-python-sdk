# `send_data_channel()` の送信先制限を `## develop` に `[CHANGE]` として追記する

- Created: 2026-10-10
- Completed: 2026-10-10
- Branch: feature/change-send-data-channel-label-restriction
- Polished: 2026-10-10

## 目的

`CHANGES.md` の `## develop` にある canary.8 のエントリはバージョンと `WEBRTC_BUILD_VERSION` だけを記載しており、同じバージョンアップに含まれる `SoraSignaling::SendDataChannel()` の送信先制限が変更履歴に残っていない。

この制限は sora-python-sdk の `SoraConnection.send_data_channel()` の戻り値と送信可否を後方互換を壊す形で変える。canary.8 より前はラベルを検証せず `DataChannel::Send()` を呼んで `true` を返していたため、Sora が管理するラベル (`signaling` / `stats` / `notify` / `push` / `rpc`) へ送信しても `true` が返り、実際に送信されていた。canary.8 以降は送信自体が行われず `false` が返るため、これらのラベルへ送信していたアプリケーションはコードの変更を迫られる。

変更履歴に記載されないままリリースされると利用者が挙動変更を把握できないため、`## develop` に `[CHANGE]` エントリを追記してリリースノートに残る状態にする。

## 現状

- `CHANGES.md` の `## develop` の canary.8 エントリは次の 2 項目のみ
  - `Sora C++ SDK のバージョンを 2026.3.0-canary.8 に上げる`
  - `WEBRTC_BUILD_VERSION を m155.8059.4.1 に上げる`
- Sora C++ SDK `2026.3.0-canary.8` の `SoraSignaling::SendDataChannel()` は `#` で始まるユーザー定義ラベルだけを送信対象にし、Sora が管理するラベル (`signaling` / `stats` / `notify` / `push` / `rpc`) と offer に含まれないラベル、開いていないラベルへは送信せず `false` を返す (sora-cpp-sdk の issue 0107)
- canary.8 より前の `SoraSignaling::SendDataChannel()` はラベルを検証せず `DataChannel::Send()` を呼び、その戻り値を捨てて `true` を返していた
- `src/sora_connection.cpp` の `SoraConnection::SendDataChannel()` は `conn_->SendDataChannel()` の戻り値をそのまま Python へ返すため、`send_data_channel()` の戻り値と送信可否がこの制限の影響を受ける
- 2026.2.1 のエントリでは、依存側の互換性を壊さない修正を `[UPDATE]` のサブ項目として記載している (Sora C++ SDK の SIGSEGV 修正の例)。一方 2025.1.0 では、C++ SDK 側の仕様変更で Python 側 API の使い方が非互換になった `client_cert` / `client_key` の変更を独立した `[CHANGE]` エントリとして記載している
- `skills/sora-python-sdk/SKILL.md` は送信できるラベルの制限に触れていないが、この追記は issue 0112 で扱う

## 設計方針

- `CHANGES.md` の `## develop` の先頭 (既存の `[ADD]` エントリより前) にトップレベル `[CHANGE]` エントリを 1 件追加する。`shiguredo-changelog` 規約の種別の並び (CHANGE → ADD → UPDATE → FIX) に従う
- エントリから次が読み取れるようにする
  - `send_data_channel()` が Sora 管理ラベル (`signaling` / `stats` / `notify` / `push` / `rpc`) と offer に含まれないラベル、開いていないラベルへ送信しなくなり `false` を返すこと
  - 後方互換のない変更であること (以前はラベルを検証せず送信を試みて `true` を返していたこと、Sora C++ SDK `2026.3.0-canary.8` の `SoraSignaling::SendDataChannel()` の送信先制限によるもの)
  - `rpc` ラベルへリクエストを送る場合は `send_rpc()` を使うこと
- `[UPDATE]` の canary.8 エントリにはサブ項目を追加しない。同じ内容を 2 か所に書くと更新時に食い違うため、`[CHANGE]` エントリにだけ記載する
- `CHANGES.md` に issue 番号や issue への言及を書かない (`shiguredo-issues` 規約)
- `shiguredo-changelog` 規約のサブ項目のインデント、担当者の記載位置を守る
- 全角と半角の間に半角スペースを入れる

## 完了条件

- `CHANGES.md` の `## develop` の先頭にトップレベル `[CHANGE]` エントリが追加されていること
- そのエントリから次が読み取れること
  - `send_data_channel()` が Sora 管理ラベルと offer に含まれないラベル、開いていないラベルへ送信しなくなり `false` を返す
  - 以前はラベルを検証せず送信を試みて `true` を返していたこと (後方互換のない変更であること)
  - `rpc` ラベルへリクエストを送る場合は `send_rpc()` を使う
- `shiguredo-changelog` 規約 (種別の並び、サブ項目のインデント、担当者の記載位置) を満たしていること
- `CHANGES.md` に issue 番号・issue への言及が含まれていないこと
- 既存エントリの内容と順序が壊れていないこと
- 全角と半角の間に半角スペースが入っていること

## 変更対象

- `CHANGES.md`

## 解決方法

- `CHANGES.md` の `## develop` の先頭にトップレベル `[CHANGE]` エントリを 1 件追加した
  - `send_data_channel()` が Sora が管理するラベル (`signaling` / `stats` / `notify` / `push` / `rpc`) と offer に含まれないラベル、開いていないラベルへ送信せず `False` を返すようになったこと
  - 以前はラベルを検証せず送信を試みて `True` を返していたこと (後方互換のない変更であること)
  - `#` で始まるラベルでも、開く前に送っていた場合は `False` になることと、`on_data_channel` が発火してチャネルが開くまで待ってから送るという対応
  - Sora C++ SDK `2026.3.0-canary.8` の `SoraSignaling::SendDataChannel()` が送信先を `#` で始まるユーザー定義ラベルに制限したためであること
  - `rpc` ラベルへリクエストを送る場合は `send_rpc()` を使うこと、それ以外の Sora が管理するラベルを使っていた場合は送信をやめること
- `[UPDATE]` の canary.8 エントリにはサブ項目を追加していない (同じ内容を 2 か所に書かないため)
- `skills/sora-python-sdk/SKILL.md` への送信できるラベルの制限の追記と `send_rpc()` の追加は issue 0112 のマージで完了しており、同じリリースに含まれる

### 確認したこと

- `uv run pytest tests/ -n auto` が 82 passed / 98 skipped / 1 xfailed で通ること (実際の Sora に接続)
- 追加した記述が Sora C++ SDK `2026.3.0-canary.8` の実装 (`src/sora_signaling.cpp` の `SendDataChannel()` / `DoSendDataChannel()` と `src/data_channel.cpp` の `DataChannel::Send()`) と一致すること
- canary.8 より前の実装 (`2026.3.0-canary.7` と `2026.2.1`) が `dc_->Send()` の戻り値を捨てて `true` を返していたこと
- 実際の Sora で `send_data_channel()` が `#test` (開いた後) で `True`、`signaling` / `stats` / `notify` / `push` / `rpc`、offer に含まれないラベル、開く前の `#test` で `False` になること
- `send_rpc()` が `rpc` ラベルへ送信でき (制限の対象外)、応答が `on_rpc` に届くこと
- `uv run python run.py format` が差分を出さないこと
- `git diff develop` が追加のみで、既存エントリの内容と順序が変わっていないこと
- `CHANGES.md` に issue 番号・issue への言及が含まれていないこと
- 追加した行に全角と半角の間の半角スペースの抜けが無いこと
