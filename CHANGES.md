# 変更履歴

- CHANGE
    - 下位互換のない変更
- UPDATE
    - 下位互換がある変更
- ADD
    - 下位互換がある追加
- FIX
    - バグ修正

## develop

- [UPDATE] Sora::ConvertDataChannels() の実装をリファクタリング

    - @sile
- [ADD] データチャネルを使ったサンプルを追加する
    - 以下の三つを追加:
        - test/messaging_readonly.py
        - test/messaging_sendonly.py
        - test/messaging_sendrecv.py
    - @sile
- [CHANGE] `SoraConnection.on_message()` コールバックの第二引数の方を `str` から `bytes` に変更する
    - 文字列以外の任意のバイト列が送受信可能なため
    - @sile
- [ADD] `SoraConnection` クラスに `send_data_channel(label: str, data: bytes)` メソッドを追加する
    - データチャネル経由でメッセージを送信するためのメソッド
    - 使用するためには `Sora.create_connection()` で以下のオプションを指定する必要がある:
        - `data_channel_signaling=True`
        - `data_channels=[{"label": ..., "direction": ..., ...}, ...]`
    - なお `create_connection()` の後、 `SoraConnection.on_data_channel(label: str)` コールバックが呼び出されるまでは、該当ラベルに対するメッセージ送信は行えないので注意が必要
    - @sile
- [ADD] `Sora.create_connection()` メソッドにデータチャネル関連の引数を追加する
    - 追加したのは以下の引数:
        - `data_channels`
        - `data_channel_signaling`
        - `ignore_disconnect_websocket`
    - @sile
