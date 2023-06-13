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

- [CHANGE] メッセージング系のサンプルでは音声および映像を無効にする
   - `messaging_{sendrecv,sendonly,recvonly}.py` では `Sora.create_connectoin(audio=False, video=False, ...)` を指定する
   - @sile
- [ADD] Python SDK では常にマルチストリームを有効にする
   - デフォルト値を使うのではなく `sora::SoraSignalingConfig::multistream` フィールドに明示的に `true` を指定する
   - @sile
- [ADD] Sora.create_connection() メソッドに音声・映像コーデックを指定するための引数を追加する
    - `audio_codec_type` および `video_codec_type` 引数
    - デフォルトは未指定
    - @sile
- [ADD] Sora.create_connection() メソッドに音声・映像の有効無効を指定するための引数を追加する
    - `audio` および `video` 引数
    - デフォルトはどちらも `true`
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
