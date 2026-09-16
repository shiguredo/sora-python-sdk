# sora-rust-sdk + PyO3 + maturin 移行の設計判断

現行の Sora C++ SDK + nanobind + 独自ビルド基盤を、sora-rust-sdk + PyO3 + maturin へ置き換えるための設計判断をまとめる。実装単位の issue を起票するための入力であり、判断の根拠と未確定事項を明示する。

上流の受け口の有無を 1 項目ずつ確認した結果は `docs/sora-rust-sdk-investigation.md` にある。本書はその結果を入力とした決定と、実装へ渡す仕様を扱う。

## 調査条件

上流の受け口は次の版のソースコードを取得して確認した。推測ではなく、クレートのソースに存在するシンボルで確認している。

| 対象 | 確認した版 | 公開日 |
| --- | --- | --- |
| `sora_sdk` | `2026.2.0-canary.6` | 2026-09-15 |
| `shiguredo_webrtc` | `0.154.0` | 2026-09-10 |

`sora_sdk` の安定版は `2026.1.0`、`shiguredo_webrtc` の最新は `0.154.0` である。`sora_sdk 2026.2.0-canary.6` は `shiguredo_webrtc` を `~0.154` に解決する。

## 上流に受け口が無いものの再確認結果

すべて「受け口なし」を確認した。4 か月前の試作時点から解消していない。

### sora-rust-sdk 側

| # | 現行 API | 確認結果 | 根拠 |
| --- | --- | --- | --- |
| 1 | `SoraConnection.on_disconnect` (エラーコードと理由文) | 受け口なし | `src/connection_event_handler.rs` の `SoraConnectionEventHandler` は `on_signaling_message` / `on_notify` / `on_push` / `on_track` / `on_remove_track` / `on_switched` / `on_websocket_close` / `on_message` / `on_data_channel` / `on_data_channel_open` / `on_data_channel_message` / `on_data_channel_close` の 12 メソッドのみ |
| 2 | `SoraConnection.on_set_offer` (受信 offer の SDP) | 受け口なし | 同上。offer を通知するメソッドが存在しない |
| 3 | `SoraConnection.on_rpc` (サーバーからの RPC 要求) | 受け口なし | `SoraConnectionHandle::send_rpc_request` (`src/connection.rs`) は送信のみ。ハンドラに受信メソッドが無い |
| 4 | `SoraConnection.on_switched` の引数 | 引数なし | `fn on_switched(&mut self) {}`。切替内容は渡らない |
| 6 | 音声 encoded transform | 受け口なし | `SoraConnectionBuilder::sender_video_transform` / `receiver_video_transform` のみ。音声版が無い |
| 7 | `degradation_preference` / `audio_streaming_language_code` / `spotlight_number` / 送信側 `simulcast_rid` | 受け口なし | `SoraConnectionBuilder` の公開メソッドに該当項目が無い。`ForwardingFilter` / `VideoCodecPreference` にも相当する項目が無い |
| 11 | libcamera | 受け口あり | `libcamera` feature で `LibcameraVideoCapturerBuilder` (`camera_index` / `width` / `height` / `native_frame_output` / `control` / `controls` / `build`) と `LibcameraVideoCapturer` (`start` / `stop` / `video_source`) が公開される |

`SoraConnectionBuilder` の公開メソッドは次である。この一覧に無い送信設定は上流へ依頼するか、公開 API から外すかを決める必要がある。

- トラックと変換: `sender_video_track` / `sender_audio_track` / `sender_video_transform` / `receiver_video_transform`
- 識別: `client_id` / `bundle_id` / `metadata` / `signaling_notify_metadata`
- 可否: `audio` / `video` / `data_channel_signaling` / `ignore_disconnect_websocket` / `simulcast` / `spotlight`
- 同時配信と注視: `simulcast_request_rid` / `spotlight_focus_rid` / `spotlight_unfocus_rid`
- 転送: `forwarding_filters` / `data_channels`
- 待ち上限: `websocket_connection_timeout` / `websocket_close_timeout` / `disconnect_wait_timeout`
- 接続仲介と証明書: `ice_server_url_configurer` / `proxy` / `insecure` / `turn_tls_insecure` / `ca_cert` / `turn_tls_ca_cert` / `client_cert` / `user_agent`

### shiguredo_webrtc 側

| # | 現行 API | 確認結果 | 根拠 |
| --- | --- | --- | --- |
| 5 | `SoraTrackInterface.state` | 受け口なし | `src/api/rtp.rs` の `MediaStreamTrack` は `kind` / `id` / `enabled` / `set_enabled` / `cast_to_video_track` / `cast_to_audio_track` のみ |
| 5 | `SoraMediaTrack.stream_id` | 受け口なし | `src/api/rtp.rs` の `RtpReceiver` は `track` / `set_frame_transformer` のみ |
| 8 | VAD | 受け口なし | `voice_activity_detection` は `RTCOfferAnswerOptions` のフラグであり、`VoiceActivityDetectorWrapper` の露出ではない。クレート全体に VAD の型が無い |
| 10 | 音声リサンプラ | 受け口なし | クレート全体に `PushResampler` 相当の型が無い |
| 12 | `AudioMixer` | 受け口なし | クレート全体に `AudioMixer` の型が無い。ただし `AudioDeviceModuleHandler` (`Send + Sync`) と `AudioDeviceModule::new_with_handler` があり、任意 PCM の再生・録音を駆動する経路は公開されている |
| 12 | `AdmConfig` | 受け口あり | `sora_sdk` の `src/connection_context.rs` に `NoAudioDevice` / `UseBuiltIn` / `UseExternal(AudioDeviceModule)` の 3 種がある |

### 参考: 利用できる主要な受け口

- `SoraConnectionContext::new` / `new_with_config` / `create_audio_source` / `create_audio_track` / `create_video_track`
- `AudioTrackSinkHandler` (`on_data` で生 PCM) と `VideoSinkHandler` (`on_frame` で `VideoFrameRef`)
- `FrameTransformerHandler` (`Send + Sync` が必要。エンコーダー / ネットワークスレッド上で呼ばれる)
- ログ: `shiguredo_webrtc::log` の `LoggingConfig` / `Severity` / `LogSink` / `LogSinkHandler` / `initialize_logging` / `print`
- `Error` の `Display` は日本語であるため、Python に渡すメッセージは英語へ変換する必要がある

## 決定事項

次のとおり確定した。各項目の根拠は上記の再確認結果と `docs/sora-rust-sdk-investigation.md` にある。

| # | 項目 | 決定 |
| --- | --- | --- |
| 1〜4 | 切断結果 / 受信 offer / 受信 RPC / 切替内容の受け口 | sora-rust-sdk へ追加を依頼する |
| 5 | `SoraTrackInterface.state` / `SoraMediaTrack.stream_id` | webrtc-rs へ追加を依頼する |
| 6 | 音声 encoded transform | sora-rust-sdk へ追加を依頼する |
| 7 | 送信設定 4 項目 | sora-rust-sdk へ追加を依頼する。`degradation_preference` と rid は webrtc-rs 側に部品があるため、sora-rust-sdk が公開するだけで足りる |
| 8 | VAD | webrtc-rs へ `VoiceActivityDetectorWrapper` の露出を依頼する。閾値判定で代替しない |
| 9 | `force_i420_conversion` | 公開 API から削除する |
| 10 | 音声リサンプル | webrtc-rs へ `PushResampler` 相当の露出を依頼する。直線補間で代替しない |
| 11 | libcamera | `libcamera` feature を有効化して `create_libcamera_source` を実装する |
| 12 | 受信音声の駆動方式 | `AudioDeviceModuleHandler` を実装した偽オーディオデバイスで再生を駆動する。`AudioMixer` の露出は依頼しない |
| 13 | free-threading | `#[pymodule(gil_used = false)]` を宣言する |
| 14 | コールバックの Python 中継方式 | キュー経由で専用スレッドへ渡す |
| 15 | 対応プラットフォーム | 現行 8 プラットフォームを維持し、armv8 系のクロスコンパイルを実証する。成立しないものは実証結果に基づいて落とす |
| 16 | wheel の tag と同梱物 | maturin で表現する。Raspberry Pi OS の `libcamerac.so` 同梱は libcamera の実装 issue で扱う |
| 17 | Jetson | 移行後に再構築する。`issues/pending/` の Jetson 4 件は pending のまま残す |
| 18 | E2E の対象 | Python 3.12 / 3.13 / 3.14 の全版を対象にする |
| 19 | 影響を受ける既存 issue | 移行後のコードが確定してから 1 件ずつ判定する。`tests/` を前提にする 6 件は 0107、残り 38 件は 0108 で判定する |

`sora_sdk` は canary 系列 (`2026.2.0-canary.6`) に追従し、安定版が出た時点で切り替える。

### 決定の補足

#### 8. VAD

現行の `SoraVAD` は libwebrtc の `webrtc::VoiceActivityDetectorWrapper` を使い、確率を返す。上流に露出が無いため、webrtc-rs へ `VoiceActivityDetectorWrapper` の露出を依頼する。現行と同じ判定結果を維持できる唯一の方式であり、閾値判定による代替は設計方針で禁止されている。別クレートの利用は現行と出力が一致する保証が無く、公開 API からの削除は機能の消失になる。

#### 9. `force_i420_conversion`

C++ SDK 固有の概念で、Rust 側に対応する設定が無い。次から選ぶ。

1. 公開 API から削除する
2. 同名の引数を残し、意味を「入力フレームを常に I420 として扱う」と再定義して自前で実装する

推奨は 1 である。後方互換を考慮しない方針であり、I420 変換は `shiguredo_webrtc` の `convert_from_i420` / `to_i420` で明示的に行えるため、SDK の設定として持つ意味が無い。

#### 10. 音声リサンプル

現行は libwebrtc の `webrtc::PushResampler<int16_t>` を使う。上流に露出が無いため自前実装も検討したが、直線補間のような簡易実装は設計方針で禁止されており、現行と同等の出力品質を自前で検証する費用が大きい。`SoraAudioSink` の `output_frequency` / `output_channels` を外すと利用者への影響も大きい。したがって webrtc-rs へ `PushResampler` 相当の露出を依頼する。

#### 11. libcamera

上流に `libcamera` feature と `LibcameraVideoCapturerBuilder` があるため、これを有効化して `create_libcamera_source` を実装する。feature を常時有効にすると Raspberry Pi OS 以外でビルドできない可能性があるため、対象プラットフォームでのみ有効化する。

引数は上流の API でそのまま表現できる。現行の `native_frame_output` は `LibcameraVideoCapturerBuilder::native_frame_output`、`controls` は `control` / `controls` (`Vec<(String, String)>`) に対応する。

feature の有効化方法 (常時 / 対象プラットフォームのみ / 別 wheel) は libcamera の実装 issue で確定する。

#### 12. 受信音声の駆動方式

現行は `context_config.configure_dependencies` で `dependencies.audio_mixer` に自前の `DummyAudioMixer` を差し込む。Rust 側に `AudioMixer` の露出が無いため、`AudioDeviceModuleHandler` (`Send + Sync`) と `AudioDeviceModule::new_with_handler` を実装した偽オーディオデバイスで再生を駆動する。

試作がループバックで音声 980 フレームの受信を実証しており、追加の上流依頼が不要である。実マイクを使わないヘッドレス環境でも受信できる点が現行方式より有利である。`AudioMixer` の露出は依頼しない。

#### 13. free-threading

`#[pymodule(gil_used = false)]` を宣言する。宣言できる根拠は次である。

- sora-rust-sdk のコールバックは Rust / tokio スレッド内で完結する
- blocking な接続処理は `Python::detach` で GIL を外して実行できる
- フレーム受け渡しは numpy 配列の生成時にのみ GIL を取る

#### 14. コールバックの Python 中継方式

上流のコールバックはブロック禁止であり、Python callable を直接呼ぶと GIL 取得でブロックしうる。キュー経由で専用スレッドへ渡す方式を採用する。

- Rust 側のコールバックはロックフリーなキューへ push して即座に戻る
- Python 側は専用スレッドがキューから取り出して callable を呼ぶ
- 順序は上流が単一タスクから直列に呼ぶため、キューで保存される

## Python 公開 API の設計方針

後方互換は考慮しない。`Sora.create_connection` の 49 引数を構造体ベースへ変更し、引数の機械同期をなくす。

- 接続設定は `SoraConnectionConfig` 相当のデータクラスで受け取る
- 型ヒントはビルド時に生成される `.pyi` に依存せず、`python/sora_sdk` の実装に直接書く
- `src/sora_sdk/__init__.py` の track 参照保持ラッパーは、Rust 側で参照カウンタが正しく扱えるなら不要になる。必要かどうかは実装時に検証する
- `force_i420_conversion` は削除する
- `SoraVAD` / `SoraTrackInterface.state` / `SoraMediaTrack.stream_id` / `SoraAudioFrameTransformer` は上流の依頼 (H / G / E) が受理されるまで実装できない。受理されない場合は公開 API から削除する。`SoraVideoFrameTransformer` は上流に受け口があるため残す
- 列挙 `SoraDegradationPreference` / `SoraTrackState` は、上流の依頼 (F / G) が受理された時点で上流の型から変換する。受理されない場合は削除する
- `SoraSignalingErrorCode` は上流の依頼 (A) が受理された時点で上流のエラー型から変換する

### 現行公開面の棚卸し

`src/sora_sdk/sora_sdk_ext.pyi` (503 行) が現行の公開面の正本である。移行時に次の単位で扱う。

| 区分 | 現行シンボル |
| --- | --- |
| 列挙 | `SoraSignalingErrorCode` / `SoraSignalingType` / `SoraSignalingDirection` / `SoraDegradationPreference` / `SoraTrackState` / `SoraLoggingSeverity` / `SoraTransformableFrameDirection` / `SoraTransformableAudioFrameType` |
| ログ | `enable_libwebrtc_log` / `rtc_log` |
| トラック | `SoraTrackInterface` / `SoraMediaTrack` |
| 送信元 | `SoraAudioSource` / `SoraVideoSource` |
| 受信 | `SoraAudioSinkImpl` / `SoraAudioStreamSinkImpl` / `SoraVideoSinkImpl` / `SoraAudioFrame` / `SoraVideoFrame` |
| VAD | `SoraVAD` |
| 接続 | `SoraConnection` (コールバック 12 種) |
| 変換 | `SoraFrameTransformer` / `SoraAudioFrameTransformer` / `SoraVideoFrameTransformer` / `SoraTransformableFrame` / `SoraTransformableAudioFrame` / `SoraTransformableVideoFrame` |
| ファクトリ | `Sora` (`create_connection` / `create_audio_source` / `create_video_source` / `create_libcamera_source` / `version`) |

## 対応プラットフォームと配布

現行 8 プラットフォームを維持し、armv8 系のクロスコンパイルを実証する。成立しないものは実証結果に基づいて落とす。対象は次のとおり。

- ubuntu-26.04 / ubuntu-24.04 の x86_64 と armv8
- raspberry-pi-os_armv8
- macos-15 / macos-26 の arm64
- windows-2025_x86_64

各プラットフォームで Python 3.12 / 3.13 / 3.14 の wheel を作る。

- 上流の prebuilt libwebrtc は linux x86_64 / aarch64 (ubuntu-22.04 / 24.04 / 26.04、raspberry-pi-os)、macos aarch64、windows x86_64 を対象とする
- armv8 と raspberry-pi-os は x86_64 runner からのクロスコンパイルになり、`WEBRTC_C_TARGET` と sysroot / リンカ設定で成立するかを実証する
- PyPI への公開対象は ubuntu-24.04 の x86_64 / armv8、macos-15 / 26 の arm64、windows-2025_x86_64、raspberry-pi-os_armv8 の 6 プラットフォームとする
- 現行の手動 manylinux tag 設定と Raspberry Pi OS 向け `libcamerac.so` 同梱は maturin で表現する

## 移行で影響を受ける既存 issue

現行 issue が列挙する 44 件を 3 分類で扱う。1 件ずつの処遇判定は移行後のコードが確定してから行う。

| 分類 | 件数 | 内訳 |
| --- | --- | --- |
| C++ 実装・ビルド基盤・nanobind・Jetson・現行引数形を前提にするもの | open 14 件 / pending 18 件 | `0044` `0050` `0055` `0056` `0059` `0062` `0068` `0075` `0076` `0077` `0081` `0082` `0083` `0097` / `0043` `0045` `0072` `0073` `0078` `0079` `0080` `0084` `0085` `0086` `0087` `0088` `0089` `0091` `0092` `0093` `0095` `0096` |
| 現行の WebRTC スタックの挙動を前提にするもの | open 1 件 / pending 1 件 | `0015` / `0090` |
| 移行で作り替える `tests/` を前提にするもの | open 6 件 | `0037` `0038` `0040` `0041` `0064` `0065` |

Jetson は移行後に再構築する。`issues/pending/` の Jetson 4 件は pending のまま残し、移行の完了後に扱いを再検討する。

## 実装単位の分割案

依存関係を明示する。「上流」は上流への追加が前提であることを示す。

| 順 | 内容 | 依存 |
| --- | --- | --- |
| 1 | ビルド基盤を maturin + PyO3 へ置き換える (C++ 実装と CMake / setup 系の削除を含む) | なし |
| 2 | 受信系 API (Sink / フレーム / `on_track`) を実装する | 1、上流 (5) |
| 3 | 送信系 API (Source / `on_data` / `on_captured`) を実装する | 1、2 |
| 4 | コールバックの Python 中継を実装する | 1 |
| 5 | 接続設定を構造体ベースへ変更し、残差 API を実装する | 1、4、上流 (7) |
| 6 | 音声リサンプルと VAD を実装する | 1、2、上流 (8、10) |
| 7 | libcamera 入力を実装する | 1、3 |
| 8 | CI を maturin 化し、wheel とクロスコンパイルを実証する | 1〜7 |
| 9 | 既存テストを移行し、実 Sora に対して通す | 2〜7 |
| 10 | 移行で影響を受ける既存 issue (テストを前提にするものを除く) の処遇を確定する | 2〜7 |
| 11 | ドキュメントを追従させる | 8〜10 |

分割案の 1〜11 は、起票した issue 0099〜0109 に順に対応する。

## 上流へ依頼する項目

### 依頼先と依頼内容

依頼は 2 リポジトリへ 9 件である。`sora-rust-sdk` 5 件、`webrtc-rs` 4 件。

| # | 依頼先 | 内容 | 対応する検討事項 |
| --- | --- | --- | --- |
| A | sora-rust-sdk | `SoraConnectionEventHandler` に切断結果 (エラーコードと理由文) を受け取るメソッドを追加する | 1 |
| B | sora-rust-sdk | `SoraConnectionEventHandler` に受信 offer の SDP を受け取るメソッドを追加する | 2 |
| C | sora-rust-sdk | `SoraConnectionEventHandler` にサーバーからの RPC 要求を受け取るメソッドを追加する | 3 |
| D | sora-rust-sdk | 切替内容を取得する受け口を追加する (`on_switched` の引数化を含む) | 4 |
| E | sora-rust-sdk | 音声の encoded transform の受け口を追加する | 6 |
| F | sora-rust-sdk | `degradation_preference` / `audio_streaming_language_code` / `spotlight_number` / 送信側 `simulcast_rid` の設定を追加する | 7 |
| G | webrtc-rs | `MediaStreamTrack` に状態取得、`RtpReceiver` に `stream_id` を追加する | 5 |
| H | webrtc-rs | VAD (`webrtc::VoiceActivityDetectorWrapper` 相当) の露出を追加する | 8 |
| I | webrtc-rs | 音声リサンプラ (`webrtc::PushResampler<int16_t>` 相当) の露出を追加する | 10 |

F のうち `degradation_preference` と rid は `shiguredo_webrtc` 側に部品がある。`DegradationPreference` enum、`RtpParameters::set_degradation_preference`、`RtpEncodingParameters::set_rid` が公開済みであり、`sora_sdk` が映像送信器を内部保持して外へ出す API を持たないために使えない。したがって依頼先は sora-rust-sdk で足りる。

### 依頼文のドラフト

`sora-rust-sdk` へ出す依頼文。1 件ずつ別 issue として出す。

**A. 切断結果をイベントハンドラで受け取れるようにする**

```
タイトル: SoraConnectionEventHandler に切断結果を受け取るメソッドを追加する

**要望**

Sora サーバーからの切断 (WebSocket close) の code と reason を、
SoraConnectionEventHandler で受け取れるようにしてください。

**背景**

Python SDK の on_disconnect は SoraSignalingErrorCode と理由文を利用者へ渡しています。
現状の SoraConnectionEventHandler には切断結果を受け取るメソッドが無く、
on_websocket_close は生の code と reason のみを渡すため、SDK の終了符号へ変換できません。

**現状の実装**

src/connection_event_handler.rs の SoraConnectionEventHandler は 12 メソッドで、
on_websocket_close(code: Option<u16>, reason: &str) はありますが、
切断の完了と終了結果を通知するメソッドがありません。

**提案**

次のいずれか、または同等の形を検討いただけないでしょうか。

- on_disconnect(&mut self, code: Option<u16>, reason: &str) を追加する
- SoraConnection::run(self) の戻り値で終了結果を返す
```

**B. 受信した offer の SDP をイベントハンドラで受け取れるようにする**

```
タイトル: SoraConnectionEventHandler に受信 offer の SDP を渡すメソッドを追加する

**要望**

Sora サーバーから受信した offer の SDP を、
SoraConnectionEventHandler で受け取れるようにしてください。

**背景**

Python SDK の on_set_offer は受信した offer の SDP を利用者へ渡しています。
現状は IncomingMessageData::Offer が crate 内に閉じており、
SDP は内部の handle_offer へ渡されるだけです。

**提案**

on_set_offer(&mut self, sdp: &str) を追加する。
```

**C. サーバーからの RPC 要求を受け取れるようにする**

```
タイトル: サーバーからの RPC 要求を受け取るメソッドを追加する

**要望**

サーバーから送られてくる JSON-RPC 2.0 の要求を、
SoraConnectionEventHandler で受け取れるようにしてください。

**背景**

現状の公開 API は送信の SoraConnectionHandle::send_rpc_request のみで、
受信した要求を渡す受け口がありません。RpcRequestOptions / RpcResponse は公開されていますが、
受信要求を表す型と通知経路がありません。

**提案**

- 受信した要求を表す型を追加する
- on_rpc(&mut self, request: RpcRequest) などで通知する
- 応答を返す手段 (SoraConnectionHandle 経由など) を用意する
```

**D. 切替内容を取得できるようにする**

```
タイトル: on_switched で切替内容を取得できるようにする

**要望**

WebSocket から DataChannel への切替時に、
切替内容 (シグナリングの切替を指示したメッセージ) を取得できるようにしてください。

**背景**

Python SDK の on_switched は切替内容の JSON 文字列を利用者へ渡しています。
現状は fn on_switched(&mut self) と引数を取らないため、切替内容を再現できません。

**提案**

on_switched(&mut self, text: &str) のように切替内容を渡すか、
切替内容を取得する API を追加してください。
```

**E. 音声の encoded transform を追加する**

```
タイトル: 音声の encoded transform の受け口を追加する

**要望**

音声の encoded transform を登録できるようにしてください。

**背景**

現状は sender_video_transform / receiver_video_transform のみで、
音声には相当する受け口がありません。
Python SDK は音声の encoded transform を公開しており、移行時に失われます。

**提案**

sender_audio_transform / receiver_audio_transform を追加する。
```

**F. 送信設定を追加する**

```
タイトル: 送信設定 (degradation_preference / audio_streaming_language_code / spotlight_number / 送信側 simulcast rid) を追加する

**要望**

次の 4 つの送信設定を SoraConnectionBuilder から指定できるようにしてください。

- degradation_preference
- audio_streaming_language_code
- spotlight_number
- 送信側 simulcast の rid

**背景**

Python SDK が公開している設定ですが、SoraConnectionBuilder の 30 のビルダーメソッドに
対応するものがありません。connect メッセージの member にも存在しません。

degradation_preference と rid は shiguredo_webrtc 側に部品があります。
DegradationPreference enum、RtpParameters::set_degradation_preference、
RtpEncodingParameters::set_rid は公開済みですが、
sora_sdk が映像送信器を内部に保持して外へ出す API を持たないため利用できません。

**提案**

- degradation_preference と rid は、内部の映像送信器へ設定する経路を公開する
- audio_streaming_language_code と spotlight_number は connect メッセージへ載せる
```

`webrtc-rs` へ出す依頼文。

**G. トラックの状態と受信器の stream_id**

```
タイトル: MediaStreamTrack の状態取得と RtpReceiver の stream_id を追加する

**要望**

- webrtc::MediaStreamTrackInterface::state() に相当する取得を追加してください
- webrtc::RtpReceiverInterface::streams() に相当する stream_id の取得を追加してください

**背景**

Python SDK の SoraTrackInterface.state と SoraMediaTrack.stream_id に対応する受け口が無く、
移行時に失われます。libwebrtc の C++ API には存在しますが、
C ラッパー (webrtc/src/webrtc_c/api/media_stream_interface.h) に露出していないため
Rust 側から参照できません。

**現状**

- MediaStreamTrack のメソッドは kind / id / enabled / set_enabled / cast 系のみ
- RtpReceiver のメソッドは track / set_frame_transformer のみ
- stream_id は create_local_media_stream / add_track / RtpTransceiverInit::stream_ids の 3 箇所にのみ存在する
```

**H. VAD の露出**

```
タイトル: VAD (VoiceActivityDetectorWrapper) を露出する

**要望**

webrtc::VoiceActivityDetectorWrapper を Rust から利用できるようにしてください。

**背景**

Python SDK の SoraVAD は libwebrtc の VAD を使い、音声フレームごとに音声確率を返します。
閾値による簡易判定で代替すると出力が一致しないため、同じ実装が必要です。

**現状**

voice_activity_detection は RTCOfferAnswerOptions のフラグとしてのみ存在し、
VAD 本体をラップする C 関数がラッパーにありません。
```

**I. 音声リサンプラの露出**

```
タイトル: 音声リサンプラ (PushResampler) を露出する

**要望**

webrtc::PushResampler<int16_t> 相当のリサンプルを Rust から利用できるようにしてください。

**背景**

Python SDK の SoraAudioSink / SoraAudioStreamSink は
output_frequency / output_channels を指定して受信 PCM をリサンプルします。
自前実装では現行と同等の出力品質を保証できないため、同じ実装が必要です。

**現状**

src/ と C++ ラッパーの両方にリサンプラの型がありません。
```
