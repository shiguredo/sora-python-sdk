# Rust ベースで残差 API を再現する

- Created: 2026-09-05
- Completed: -
- Branch: feature/add-sora-rust-sdk-prototype
- Polished: {YYYY-MM-DD}

## 目的

受信系と送信系の再現後に残った公開 API の差分をなくし、
既存 `sora_sdk` からの置き換え範囲を広げる。

## 現状

- `SoraAudioSource::on_data` は ndarray 経由のみで、
  ポインタ直渡しの多重定義がない。
- `create_connection` の送信設定
  (コーデック指定やビットレート等) が未対応である。
  `sora_sdk` の組み立て器には対応する設定項目がある。
- `SoraSignalingErrorCode` と `on_set_offer` / `on_disconnect` / `on_rpc`、
  `send_data_channel` が未対応である。
  イベント処理器に直接の受け口はないが、
  送受信記録の転用と切断結果の合成で再現できる。
- `SoraMediaTrack` の `state` / `stream_id` は、
  公開バインディングに対応する取得口がなく対象外とする。
  取得口の公開を依頼してから対応する。

## 設計方針

- ポインタ直渡しは引数の型で配送し、ndarray 経路と束ねる。
- 送信設定は辞書を受け取り、組み立て器の型付き項目に変える。
  対応する項目がない設定は受け付けず、差分として記録する。
- `on_set_offer` は受信した offer 系記録から合成し、
  `on_disconnect` は切断完了時に結果から合成する。
  `on_rpc` は受け口だけ用意し、到達経路がない旨を記録する。
- メッセージング送受信は実 Sora への送受で確認する。

## 完了条件

- ポインタ直渡しと送信設定と残差コールバックの pytest が通ること。
- 送受信設定の差分一覧が整理されていること。
