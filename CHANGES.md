# 変更履歴

- CHANGE
  - 後方互換性のない変更
- UPDATE
  - 後方互換性がある変更
- ADD
  - 後方互換性がある追加
- FIX
  - バグ修正

## develop

- [CHANGE] SoraAudioSource.on_data, SoraVideoSource.on_captured, SoraVAD.analyze の引数名を変更
  - @tnoho
- [UPDATE] SoraMediaTrack を追加し、 SoraConnection.on_track の引数を SoraMediaTrack に変更
  - @tnoho
- [ADD] 発話区間の検出が可能な SoraVAD の追加
  - @tnoho
- [ADD] リアルタイム性を重視した AudioStreamSink の追加
  - @tnoho
- [ADD] AudioStreamSink が返す音声フレームとして pickel が可能な AudioFrame を追加
  - @tnoho
- [UPDATE] Sora C++ SDK のバージョンを 2023.17.0 に上げる
  - WebRTC m116 で cricket::Codec は protected になったので cricket::CreateVideoCodec に修正する
  - WebRTC m118 でパッケージディレクトリが変更されたためそれに追従する
  - WebRTC m120 の webrtc::EncodedImage API の変更に追従する
  - WEBRTC_BUILD_VERSION を `m120.6099.1.2` に上げる
  - BOOST_VERSION を `1.83.0` に上げる
  - CMAKE_VERSION を `3.27.7` に上げる
  - @voluntas @miosakuma

## 2023.3.1

**2023-07-13**

- [FIX] C++ SDK のバージョンを 2023.7.2 にあげる
  - 特定のタイミングで切断が発生すると Closing 状態で止まってしまう問題が修正された
  - @sile

## 2023.3.0

**2023-07-06**

- [CHANGE] Sora.create_connection() が複数のシグナリング URL を受け取れるようにする
  - C++ SDK の仕様に合わせるための破壊的な変更
  - `signaling_url` は廃止して `signaling_urls` で置き換える
  - `signaling_urls` は `List[str]` を受け取る
  - @sile

## 2023.2.0

**2023-07-03**

- [ADD] OpenH264 に対応
  - Ubunut 22.04 x86_64 でのみ対応
  - @melpon

## 2023.1.2

**2023-06-28**

- [FIX] Windows の Python 用ライブラリが dll ではなく pyd だったのを修正する
  - @melpon

## 2023.1.1

**2023-06-27**

- [FIX] connect 直後に disconnect すると落ちるのを修正
  - @melpon
- [FIX] C++ SDK のバージョンを 2023.7.1 に上げる
  - @voluntas

## 2023.1.0

**2023-06-20**

- [UPDATE] `create_video_source()` と `set_enabled()` の引数に名前をつける（キーワード引数で呼べるようにする）
  - @sile
- [UPDATE] C++ SDK のバージョンを 2023.7.0 に上げる
  - @sile
- [UPDATE] 映像コーデックパラメータを指定可能にする
  - `Sora.create_connection()` の引数に以下を追加:
    - `video_vp9_params`
    - `video_av1_params`
    - `video_h264_params`
  - @sile
- [FIX] 転送フィルターのルールの "operator" フィールドが誤って "op" になっていたのを修正する
  - @sile
- [UPDATE] nanobind の最小バージョンを 1.4.0 にする
  - @voluntas
- [UPDATE] sora_client に "Sora Python SDK {PYTHON_SDK_VERSION}" を設定する
  - 今までは C++ SDK のデフォルト値が使用されていた
  - PYTHON_SDK_VERSION の部分には pyproject.toml の project.version に記載の値が使用される
  - @sile
- [FIX] 0 を途中で含むデータを送受信すると途中で途切れる問題を修正
  - @sile
- [ADD] libwebrtc のログを有効にするための `enable_libwebrtc_log()` 関数を追加する
  - `sora_sdk.enable_libwebrtc_log(sora_sdk.SoraLoggingSeverity.INFO)` といった感じで使用する
  - ログレベル (severity) は libwebrtc 準拠で `VERBOSE`, `INFO`, `WARNIGN`, `ERROR`, `NONE` の五段階
  - @sile
- [CHANGE] デフォルトでは libwebrtc のログは出さないようにする
  - @sile
- [CHANGE] audio および video パラメータが None を受け取れるようにする
  - 今までは `bool` だったのを他のパラメータに合わせて `opitonal<bool>` に変更
  - @sile
- [ADD] C++ SDK が提供して Python SDK が未提供だったシグナリングパラメータを追加する
  - 以下のパラメータを追加する:
    - bundle_id
    - signaling_notify_metadata
    - video_bit_rate
    - audio_bit_rate
    - simulcast
    - spotlight
    - spotlight_nubmer
    - simulcast_rid
    - spotlight_focus_rid
    - spotlight_unfocus_rid
    - forwarding_filter
    - data_channel_signaling_timeout
    - disconnect_wait_timeout
    - websocket_close_timeout
    - websocket_connection_timeout
    - audio_codec_lyra_bitrate
    - audio_codec_lyra_usedtx
    - check_lyra_version
    - audio_streaming_language_code
    - insecure
    - client_cert
    - client_key
    - proxy_url
    - proxy_username
    - proxy_password
    - proxy_agent
  - いずれも未指定の場合には C++ SDK のデフォルト値が採用される
  - @sile
- [UPDATE] boost のバージョンを 1.82.0 に更新する
- [UPDATE] libwebrtc のバージョンを m114.5735.2.0 に更新する
- [UPDATE] Sora C++ SDK のバージョンを 2023.6.0 に更新する
  - @sile
- [UPDATE] `Sora.connect()` メソッドにバリデーションを追加する
  - 以下のケースでは例外を送出するようにする:
    - `connect()` 呼び出し後に、同じインスタンスで再度 `connect()` を呼び出した場合
    - `disconnect()` 呼び出し後に、同じインスタンスで `connect()` を呼び出した場合
  - @sile
- [UPDATE] SIGSEGV などの異常終了を発生しにくくする
  - 合わせてサンプルコードの整理（e.g., シグナルハンドラを使わなくする）も行っている
  - @sile
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
- [ADD] PyPI に登録する GitHub Actions を追加する
  - @melpon
- [ADD] rye を使ってビルドとパッケージングが出来るようにする
  - @melpon
- [ADD] nanobind を利用して Sora C++ SDK ベースの Python SDK を追加する
  - @tnoho
