# sora-rust-sdk / shiguredo_webrtc 受け口調査レポート

issue 0098 の「検討が必要な事項」1〜12 について、最新版のソースコードを実際に読んで受け口の有無を確認した結果です。

## 調査対象バージョンと取得元

| クレート | 種別 | バージョン | 公開日時 (crates.io `created_at`) |
| --- | --- | --- | --- |
| `sora_sdk` | 安定版 | `2026.1.0` | 2026-08-25T08:20:26Z |
| `sora_sdk` | canary 版 (最新) | `2026.2.0-canary.6` | 2026-09-15T05:54:04Z |
| `shiguredo_webrtc` | 安定版 = 最新 | `0.154.0` | 2026-09-10T00:09:32Z |
| `shiguredo_webrtc` | canary 版 | `0.152.1-canary.3` | 2026-09-02T02:55:02Z |

`shiguredo_webrtc` の canary 系列は `0.152.1-canary.*` で止まっており、`0.153.1` / `0.154.0` の安定版の方が新しい。`sora_sdk 2026.2.0-canary.6` が要求するのは `shiguredo_webrtc ~0.154` なので、`0.154.0` が実際に使われる版になる。

取得元 URL:

- メタデータ: `https://crates.io/api/v1/crates/sora_sdk` / `https://crates.io/api/v1/crates/shiguredo_webrtc` (User-Agent 付きで curl)
- ソース: `https://static.crates.io/crates/sora_sdk/sora_sdk-2026.2.0-canary.6.crate` / `sora_sdk-2026.1.0.crate` / `https://static.crates.io/crates/shiguredo_webrtc/shiguredo_webrtc-0.154.0.crate`
- 展開先: 作業用の一時ディレクトリ (リポジトリ外)
- リポジトリ (未 clone、URL のみ): `https://github.com/shiguredo/sora-rust-sdk` / `https://github.com/shiguredo/webrtc-rs`

crate に同梱される `webrtc/` ディレクトリ (C++ ラッパー) も確認対象に含めた。`shiguredo_webrtc` の `build.rs` は `package.metadata.external-dependencies.webrtc-build` の `version = "m154.8037.1.1"` で prebuilt libwebrtc を取得する。

## 1. `SoraConnection.on_disconnect` (切断結果の取得)

- 結論: **受け口なし**
- 根拠:
  - `sora_sdk-2026.2.0-canary.6/src/connection_event_handler.rs` の `SoraConnectionEventHandler` トレイトには `on_disconnect` が無い。トレイトが持つメソッドは `on_signaling_message` / `on_notify` / `on_push` / `on_track` / `on_remove_track` / `on_switched` / `on_websocket_close` / `on_message` / `on_data_channel` / `on_data_channel_open` / `on_data_channel_message` / `on_data_channel_close` の 12 個。
  - サーバーの close は 2 経路とも破棄される。
    - WebSocket 経路: `src/connection.rs:1414`
      ```rust
      IncomingMessageData::Close { .. } => {
          rtc_log_info!("Disconnected from Sora server");
          break;
      }
      ```
      `code` と `reason` は `{ .. }` で捨てられる。比較として `src/signaling_types.rs:69-72` では `IncomingMessageData::Close { code: u16, reason: String }` として保持されている。
    - DataChannel 経路: `src/connection.rs:2149`
      ```rust
      IncomingMessageData::Close { code, reason } if is_server_close_label(label) => {
          return Ok(HandleDataChannelMessageResult::ServerClose { code, reason });
      }
      ```
      ここでは保持されるが、`src/connection.rs:1098-1113` でログ出力と `server_close_received = true` に使うだけである。
  - `SoraConnection::run(self) -> Result<()>` (戻り値 `src/connection.rs:900`) も close code / reason を返さない。`Error` 列挙 (`src/error.rs`) に切断結果を表すバリアントは無い。
  - 唯一取得できるのは `on_websocket_close(&mut self, _code: Option<u16>, _reason: &str)` (WebSocket レイヤの close) で、これは Sora の `Close` メッセージとは別物。`src/connection.rs:1434` で `ConnectionEvent::Close { code, reason }` から呼ばれる。
- 補足: Sora の切断理由 (`DISCONNECT` / `AUTH_FAILED` / `TYPE-DISCONNECT` など) は受け取れない。`on_signaling_message` (Received) で生 JSON を拾えば `{"type":"close","code":...,"reason":...}` は見えるが、これは SDK の公開 API として意味づけられた切断結果ではない。
- 安定版との差: `2026.1.0` の `connection_event_handler.rs` は `2026.2.0-canary.6` と完全一致 (diff なし)。canary だから受け口が増えたわけではない。

## 2. `SoraConnection.on_set_offer` (受信 offer の SDP 取得)

- 結論: **受け口なし**
- 根拠:
  - `SoraConnectionEventHandler` トレイトに `on_set_offer` が無い (項目 1 と同じ 12 メソッド)。
  - offer の SDP は SDK 内部でのみ扱われる。`src/connection.rs:1329-1352`:
    ```rust
    IncomingMessageData::Offer {
        sdp,
        ice_servers,
        data_channels,
        simulcast,
        encodings,
    } => {
        handler.on_signaling_message(
            SignalingType::WebSocket,
            SignalingDirection::Received,
            &text,
        );
        ...
        let answer_sdp = self.handle_offer(&sdp, &ice_servers).await?;
    ```
    `sdp` は `handle_offer` に渡るだけで、ハンドラへは渡らない。
  - re-offer も同様 (`src/connection.rs:1354-1370`)。
  - offer のパース結果は `src/signaling_types.rs:47-53` の `pub(crate) enum IncomingMessageData::Offer { sdp: String, ... }` であり、`pub(crate)` なので crate 外からは触れない。
- 補足: `on_signaling_message(SignalingType::WebSocket, SignalingDirection::Received, &text)` の `text` は `{"type":"offer","sdp":"...","config":{...}}` の生 JSON 文字列。JSON を自前でパースすれば SDP は取得できるが、SDK が提供する受け口ではない。
- 安定版との差: なし。

## 3. サーバーからの RPC 要求を受信する受け口

- 結論: **受け口なし**
- 根拠:
  - 送信は `src/connection.rs:530` に存在する。
    ```rust
    pub async fn send_rpc_request(
        &self,
        method: &str,
        params: Option<JsonString>,
        options: RpcRequestOptions,
    ) -> Result<Option<RpcResponse>> {
    ```
  - `src/rpc.rs` は 732 行あるが、公開シンボルは `RpcRequestOptions` と `RpcResponse` (`src/lib.rs:87` で re-export) とその実装のみ。受信要求を表す型・トレイト・コールバックは無い。
  - 受信経路は `src/connection.rs:2157` 以降の `"rpc"` ラベル分岐だけで、`RpcResponse::parse` の結果を `pending_rpc_responses` と突き合わせる自己相関のみを行う。`method` を持つ受信メッセージ (JSON-RPC request) を解釈する分岐は無い。
  - `SoraEvent` 列挙 (`src/connection.rs:646-656`) にも RPC 要求を受ける variant は無く、`SoraConnectionCommand` (`src/connection.rs:658-675`) は送信系のみ。
- 補足: 現行 Python SDK は受信 (`on_rpc`) のみを公開しており、この機能は Rust 側では完全に失われる。`on_signaling_message` でも `rpc` ラベルの DataChannel メッセージは流れない (`src/connection.rs:2083` のコメント「signaling ラベルのみ on_signaling_message を呼ぶ」)。
- 安定版との差: なし。

## 4. `on_switched` のシグネチャ

- 結論: **受け口あり。ただし引数を取らない**
- 根拠: `src/connection_event_handler.rs:54-56`
  ```rust
  /// WebSocket シグナリングから DataChannel シグナリングへの切替が
  /// 完了したときに呼ばれる。
  fn on_switched(&mut self) {}
  ```
  呼び出し側は `src/connection.rs:1388-1393`:
  ```rust
  IncomingMessageData::Switched {
      ignore_disconnect_websocket: iws,
  } => {
      switched_received = true;
      switched_ignore_disconnect_websocket = iws;
      handler.on_switched();
  ```
  `iws` (`ignore_disconnect_websocket`) は保持されるが `on_switched` には渡らない。
- 補足: 現行 Python SDK は切替内容の JSON 文字列を渡す。同等の情報を得るには `on_signaling_message` (Received) で `{"type":"switched","ignore_disconnect_websocket":...}` を拾って自前で組み立てる必要がある。
- 安定版との差: なし。

## 5. 音声の encoded transform

- 結論: **受け口なし (映像のみ受け口あり)**
- 根拠: `src/connection.rs:84-85` (ビルダーのフィールド)
  ```rust
  sender_video_transform: Option<Box<dyn FrameTransformerHandler + Send>>,
  receiver_video_transform: Option<Box<dyn FrameTransformerHandler + Send>>,
  ```
  対応するビルダーメソッドは `src/connection.rs:184` (`sender_video_transform`) と `src/connection.rs:198` (`receiver_video_transform`) の 2 つだけ。`sender_audio_transform` / `receiver_audio_transform` は存在しない。
- 補足:
  - 適用箇所は映像限定。`src/connection.rs:1124` で `matches!(receiver.track().kind().as_deref(), Ok("video"))` を条件にしている。doc コメントにも「音声トラックには適用されない」(184 行・198 行) と明記されている。
  - 下位の `shiguredo_webrtc` には `RtpSender::set_frame_transformer` / `RtpReceiver::set_frame_transformer` があり、`libwebrtc` の `FrameTransformerInterface` は音声の encoded frame も変換できる型ではあるが、`sora_sdk` のビルダーには音声用の入口が無い。
  - `2026.2.0-canary.6` と `2026.1.0` の `SoraConnectionBuilder` のフィールド diff は、この `sender_video_transform` / `receiver_video_transform` の 2 行が canary で追加された差分のみである。つまり映像 transform は canary で入った新しい受け口で、音声は依然として無い。

## 6. 送信設定 (`degradation_preference` / `audio_streaming_language_code` / `spotlight_number` / 送信側 simulcast rid)

- 結論: **4 項目すべて sora_sdk の接続設定としては受け口なし**。`degradation_preference` と rid は `shiguredo_webrtc` の低レベル API としては存在する。
- 根拠 (`SoraConnectionBuilder` の全フィールド。`src/connection.rs:76-114`):
  ```rust
  pub struct SoraConnectionBuilder {
      signaling_urls: Vec<String>,
      channel_id: String,
      role: Role,

      event_handler: Option<Box<dyn SoraConnectionEventHandler + Send>>,
      sender_video_track: Option<VideoTrack>,
      sender_audio_track: Option<AudioTrack>,
      sender_video_transform: Option<Box<dyn FrameTransformerHandler + Send>>,
      receiver_video_transform: Option<Box<dyn FrameTransformerHandler + Send>>,

      // connect 時の設定
      client_id: Option<String>,
      bundle_id: Option<String>,
      metadata: Option<JsonString>,
      audio: Option<Audio>,
      video: Option<Video>,
      data_channel_signaling: Option<bool>,
      ignore_disconnect_websocket: Option<bool>,
      simulcast: Option<bool>,
      simulcast_request_rid: Option<String>,
      spotlight: Option<bool>,
      spotlight_focus_rid: Option<String>,
      spotlight_unfocus_rid: Option<String>,
      signaling_notify_metadata: Option<JsonString>,
      data_channels: Option<Vec<ConnectDataChannel>>,
      forwarding_filters: Option<Vec<ForwardingFilter>>,
      turn_tls_insecure: bool,
      turn_tls_ca_cert: Option<Vec<u8>>,
      ice_server_url_configurer: Option<Box<IceServerUrlConfigurer>>,
      proxy: Option<ProxyInfo>,
      websocket_connection_timeout: Duration,
      websocket_close_timeout: Duration,
      disconnect_wait_timeout: Duration,
      tls_config: TlsConfig,
      user_agent: Option<String>,
      // 他の保持オブジェクトより最後に破棄する必要がある。
      context: Arc<SoraConnectionContext>,
  }
  ```
  ビルダーメソッドは `src/connection.rs:165-465` に 30 個あるが、`degradation_preference` / `audio_streaming_language_code` / `spotlight_number` に対応するものは無い (grep で `src/` 全体を検索して 0 件)。
  - 送信側 simulcast rid について: `simulcast_request_rid` は「サイマルキャスト利用時に**受信側として要求する** rid」であり (`src/connection.rs:287-292`)、送信側の rid 設定ではない。送信側 rid は Sora サーバーの offer の `encodings` から `SimulcastEncodingConfig` として受け取り、`apply_simulcast_encodings` (`src/connection.rs:1664-1700`) で `encoding.set_rid(&cfg.rid)` として適用する。ユーザーが任意の rid を指定する入口は無い。
  - connect メッセージの JSON にも該当フィールドは無い。`src/signaling_types.rs:389-444` が `OutgoingMessage::Connect` の全 member を列挙しており、`audio_streaming_language_code` と `spotlight_number` は存在しない (`type` / `channel_id` / `client_id` / `bundle_id` / `redirect` / `role` / `sora_client` / `libwebrtc` / `environment` / `metadata` / `data_channel_signaling` / `ignore_disconnect_websocket` / `simulcast` / `simulcast_request_rid` / `spotlight` / `spotlight_focus_rid` / `spotlight_unfocus_rid` / `signaling_notify_metadata` / `data_channels` / `forwarding_filters` / `audio` / `video`)。
  - `Audio` (`src/types.rs:292`) の `Opus` variant が持つのは `bit_rate` + `AudioOpusParams` (`channels` / `maxplaybackrate` / `minptime` / `ptime` / `stereo` / `sprop_stereo` / `useinbandfec` / `usedtx`) のみ (`src/types.rs:163-180`)。
  - `shiguredo_webrtc 0.154.0` 側には `src/api/rtp.rs:1051-1058` に `pub enum DegradationPreference { MaintainFramerateAndResolution, MaintainFramerate, MaintainResolution, Balanced, Unknown(i32) }` があり、`RtpParameters::set_degradation_preference` (`src/api/rtp.rs:1185`) と `RtpEncodingParameters::set_rid` / `rid` (`src/api/rtp.rs:502` / `506`) が存在する。ただし `sora_sdk` はこれらを公開していないので、接続設定としては使えない。
- 補足: 現行 Python SDK の `degradation_preference` は映像送信の設定である。`shiguredo_webrtc` の `RtpSender::set_parameters` を自前で呼べば原理的には設定できるが、`sora_sdk` は `video_sender` を `SoraConnection` 内部に保持しており (`src/connection.rs:614`)、crate 外へ取り出す公開 API が無い。
- 安定版との差: ビルダーのフィールド差分は項目 5 の 2 行のみで、項目 6 の 4 設定はどちらの版にも無い。

## 7. libcamera 対応

- 結論: **受け口あり**
- 根拠:
  - feature 定義 (`Cargo.toml`):
    ```toml
    [features]
    amf = ["dep:shiguredo_amf"]
    default = ["openh264"]
    libcamera = [
        "dep:libc",
        "dep:shiguredo_libcamera",
    ]
    ```
  - `src/lib.rs:61-62` と `src/lib.rs:83-86`:
    ```rust
    #[cfg(feature = "libcamera")]
    mod libcamera;
    ...
    #[cfg(feature = "libcamera")]
    pub use crate::libcamera::{
        LibcameraNativeFrameBuffer, LibcameraVideoCapturer, LibcameraVideoCapturerBuilder,
    };
    ```
  - API の形 (`src/libcamera.rs`):
    - `LibcameraVideoCapturer::builder() -> LibcameraVideoCapturerBuilder` (145 行)
    - `camera_index(mut self, camera_index: u32) -> Self` (57 行)
    - `width(mut self, width: i32) -> Self` (65 行)
    - `height(mut self, height: i32) -> Self` (73 行)
    - `native_frame_output(mut self, native_frame_output: bool) -> Self` (83 行)
    - `control(mut self, key: impl Into<String>, value: impl Into<String>) -> Self` (91 行)
    - `controls(mut self, controls: Vec<(String, String)>) -> Self` (99 行)
    - `build(self) -> Result<LibcameraVideoCapturer>` (105 行)
    - `start(&mut self) -> Result<()>` (150 行) / `stop(&mut self)` (186 行) / `video_source(&self) -> VideoTrackSource` (194 行)
    - `LibcameraNativeFrameBuffer` のアクセサ: `fd() -> i32` / `size() -> usize` / `stride() -> i32` / `raw_width() -> i32` / `raw_height() -> i32` / `scaled_width() -> i32` / `scaled_height() -> i32` / `is_i420() -> bool` / `is_nv12() -> bool` (268-308 行)
  - デフォルト値: `camera_index = 0` / `width = 640` / `height = 480` / `native_frame_output = false` / `controls = []` (`src/libcamera.rs:24-28`, `41-51`)
  - `build()` は `width <= 0 || height <= 0` を `Error::LibcameraMessage` で弾く (106-113 行)。
- 補足:
  - `controls` の型は `Vec<(String, String)>` (キーと値の両方が文字列)。`shiguredo_libcamera` のクレート (依存版 `~2026.1`) を使う。未知の control は実行時に `Error::UnknownLibcameraControl` になる (`src/error.rs:228-230`)。
  - `native_frame_output = true` のときは `LibcameraNativeFrameBuffer` (DMA-BUF) を `VideoFrameBufferHandler` 経由で出力する。`false` のときは I420 / NV12 のコピー出力。
  - 安定版 `2026.1.0` にも `src/libcamera.rs` は存在し、`pub fn` の一覧は `2026.2.0-canary.6` と同一である。`libcamera` feature 自体も `2026.1.0` の Cargo.toml に存在する。
  - 対応プラットフォームは README に「Raspberry Pi 向け libcamera による映像入力対応」と記載されている。`shiguredo_webrtc` の `sysroot/` に `raspberry-pi-os_armv8.json` がある。

## 8. `MediaStreamTrack.state()` / `RtpReceiver.stream_id()`

- 結論: **どちらも受け口なし**
- 根拠:
  - `MediaStreamTrack` の定義は `shiguredo_webrtc-0.154.0/src/api/rtp.rs:1447`:
    ```rust
    /// webrtc::MediaStreamTrackInterface のラッパー。
    pub struct MediaStreamTrack {
        raw_ref: ScopedRef<MediaStreamTrackHandle>,
    }
    ```
    メソッドは `as_refcounted_ptr` / `kind()` / `id()` / `enabled()` / `set_enabled()` / `cast_to_video_track()` / `cast_to_audio_track()` のみ (`src/api/rtp.rs:1453-1520`)。`state()` / `set_state()` に相当するものは無い。
  - `RtpReceiver` の定義は `src/api/rtp.rs:1347`。メソッドは `track()` (1358 行) と `set_frame_transformer()` (1371 行) の 2 つだけ。`stream_id()` は無い。
  - `stream_id` を crate 全体で grep すると、`PeerConnectionFactory::create_local_media_stream(stream_id)` (`src/api/peer_connection.rs:352`) / `PeerConnection::add_track(track, stream_ids)` (`src/api/peer_connection.rs:1837`) / `RtpTransceiverInit::stream_ids()` (`src/api/rtp.rs:1272`) の 3 箇所のみ。受信側から stream_id を読む API は無い。
- 補足: `webrtc::MediaStreamTrackInterface::state()` は libwebrtc の C++ API には存在するが、shiguredo の C ラッパー (`webrtc/src/webrtc_c/api/media_stream_interface.h`) に露出していないため Rust 側にも無い。`stream_id` も同様に `webrtc::RtpReceiverInterface::streams()` が未露出である。
- 安定版との差: `shiguredo_webrtc` の canary 最新は `0.152.1-canary.3` で `0.154.0` より古い。したがって「最新版」は `0.154.0` であり、それに受け口が無いことを確認した。

## 9. VAD (Voice Activity Detection)

- 結論: **受け口なし**
- 根拠:
  - `shiguredo_webrtc-0.154.0` の `src/` 全体を `voice_activity` / `VoiceActivityDetector` / `vad` で検索すると、ヒットするのは `PeerConnectionOfferAnswerOptions::voice_activity_detection()` / `set_voice_activity_detection()` (`src/api/peer_connection.rs:857-869`) のみである。これは libwebrtc の `RTCOfferAnswerOptions::voice_activity_detection` (offer 生成時に VAD を使うかのフラグ) であり、`webrtc::VoiceActivityDetectorWrapper` (音声フレーム列に対する VAD) ではない。
  - C++ ラッパー側も `webrtc/src/webrtc_c/api/peer_connection_interface.cc:771-785` の `RTCOfferAnswerOptions` のフラグのみで、`VoiceActivityDetectorWrapper` を包む C 関数は存在しない。
  - `src/lib.rs` の re-export 一覧にも VAD 関連のシンボルは無い。
- 補足: 現行 Python SDK の `SoraVAD` (`src/sora_vad.cpp`) は `webrtc::VoiceActivityDetectorWrapper` (`modules/audio_processing/agc2/vad_wrapper.h`) を利用している。同等機能を得るには上流 (`shiguredo/webrtc-rs` の C API) への追加が必要。
- 安定版との差: `0.152.1-canary.3` も同様と推定されるが、`0.154.0` を「最新版」として確認した結果、受け口は無い。

## 10. 音声のリサンプラ (`PushResampler<int16_t>` 相当)

- 結論: **受け口なし**
- 根拠:
  - `shiguredo_webrtc-0.154.0` の `src/` 全体を `resampl` / `PushResampler` で検索して 0 件。
  - C++ ラッパー `webrtc/src/webrtc_c/` 全体を `resampl` / `PushResampler` で検索して 0 件。`webrtc/src/webrtc_c/modules/` 配下にあるのは `audio_processing` 関連ではなく `video_coding` 系のみである。
  - `src/lib.rs` の `pub use` 一覧にリサンプラは無い (libyuv 系はあるが音声は無い)。
- 補足: 現行は `src/sora_audio_sink.h` と `src/sora_audio_stream_sink.h` で `webrtc::PushResampler<int16_t>` を使っている。代替は「上流へ追加依頼」「別クレート」「自前実装」のいずれか。自前実装の場合は出力品質の同等性検証が必要。
- 安定版との差: なし。

## 11. `AudioMixer` のバインディング / `configure_dependencies` / `AdmConfig` の種類

- 結論:
  - `AudioMixer`: **受け口なし**
  - `configure_dependencies` 相当: **同名の API は無い**。ただし `PeerConnectionFactoryDependencies::set_audio_device_module` + `AdmConfig::UseExternal` という限定的な差し替え経路はある
  - `AdmConfig` の種類: **3 種類**
- 根拠:
  - `AudioMixer` を `shiguredo_webrtc-0.154.0` の `src/` と `webrtc/` の両方で grep すると、ヒットは `webrtc/src/whip.cpp:128` と `webrtc/src/whep.cpp:115` の `dependencies.audio_mixer = nullptr;` のみ。Rust バインディングにも C API にも露出していない。
  - `configure_dependencies` は `shiguredo_webrtc-0.154.0` の `src/` と `webrtc/` の両方で 0 件。
  - 代わりに `src/api/peer_connection.rs` の `PeerConnectionFactoryDependencies` に個別 setter がある:
    ```rust
    pub fn set_network_thread(&mut self, thread: &Thread)
    pub fn set_worker_thread(&mut self, thread: &Thread)
    pub fn set_signaling_thread(&mut self, thread: &Thread)
    pub fn set_audio_encoder_factory(&mut self, factory: &AudioEncoderFactory)
    pub fn set_audio_decoder_factory(&mut self, factory: &AudioDecoderFactory)
    pub fn set_audio_processing_builder(&mut self, builder: AudioProcessingBuilder)
    pub fn set_event_log_factory(&mut self, factory: RtcEventLogFactory)
    pub fn set_video_encoder_factory(&mut self, factory: VideoEncoderFactory)
    pub fn set_video_decoder_factory(&mut self, factory: VideoDecoderFactory)
    pub fn set_audio_device_module(&mut self, adm: &AudioDeviceModule)
    pub fn enable_media(&mut self)
    ```
    `audio_mixer` 用の setter は無い。
  - `sora_sdk` の `AdmConfig` (`src/connection_context.rs:21-29`):
    ```rust
    pub enum AdmConfig {
        /// Dummy の AudioDeviceModule を使用する。
        #[default]
        NoAudioDevice,
        /// PlatformDefault の AudioDeviceModule を使用する。
        UseBuiltIn,
        /// 外部の AudioDeviceModule を使用する。
        UseExternal(shiguredo_webrtc::AudioDeviceModule),
    }
    ```
    `SoraConnectionContext::new_with_config` の `match adm_config` (`src/connection_context.rs:157-170`) で `deps.set_audio_device_module(&adm)` に落ちる。
  - `AudioDeviceModule::new_with_handler(handler: Box<dyn AudioDeviceModuleHandler>)` (`shiguredo_webrtc-0.154.0/src/api/audio_device_module.rs:31`) で自前 ADM を作れるので、`AdmConfig::UseExternal` + `AudioDeviceModuleHandler` 実装で受信音声の駆動を差し替えられる。
- 補足: `AdmConfig` に `AudioMixer` を差し込む経路は無い (`SoraConnectionContextConfig` のフィールドは `adm_config` / `video_codec_preference` / `video_codec_capabilities` の 3 つ。`src/connection_context.rs:32-48`)。現行の `DummyAudioMixer` 方式をそのまま移植することはできない。

## 12. `AudioDeviceModuleHandler` の定義

- 結論: **受け口あり** (トレイト定義は `shiguredo_webrtc-0.154.0/src/api/audio_device_module.rs:765`)
- 根拠: トレイト宣言と全メソッド (既定実装付き):
  ```rust
  pub trait AudioDeviceModuleHandler: Send + Sync {
      fn active_audio_layer(&self, audio_layer: &mut i32) -> i32 { *audio_layer = 0; 0 }
      fn register_audio_callback(&self, audio_transport: Option<AudioTransportRef>) -> i32 { 0 }
      fn init(&self) -> i32 { 0 }
      fn terminate(&self) -> i32 { 0 }
      fn initialized(&self) -> bool { false }
      fn playout_devices(&self) -> i16 { 0 }
      fn recording_devices(&self) -> i16 { 0 }
      fn playout_device_name(&self, index: u16) -> Option<(String, String)> { ... }
      fn recording_device_name(&self, index: u16) -> Option<(String, String)> { ... }
      fn set_playout_device(&self, index: u16) -> i32 { 0 }
      fn set_playout_device_with_windows_device_type(&self, device: i32) -> i32 { 0 }
      fn set_recording_device(&self, index: u16) -> i32 { 0 }
      fn set_recording_device_with_windows_device_type(&self, device: i32) -> i32 { 0 }
      fn playout_is_available(&self, available: &mut bool) -> i32 { *available = false; 0 }
      fn init_playout(&self) -> i32 { 0 }
      fn playout_is_initialized(&self) -> bool { true }
      fn recording_is_available(&self, available: &mut bool) -> i32 { *available = false; 0 }
      fn init_recording(&self) -> i32 { 0 }
      fn recording_is_initialized(&self) -> bool { true }
      fn start_playout(&self) -> i32 { 0 }
      fn stop_playout(&self) -> i32 { 0 }
      fn playing(&self) -> bool { false }
      fn start_recording(&self) -> i32 { 0 }
      fn stop_recording(&self) -> i32 { 0 }
      fn recording(&self) -> bool { false }
      fn init_speaker(&self) -> i32 { 0 }
      fn speaker_is_initialized(&self) -> bool { true }
      fn init_microphone(&self) -> i32 { 0 }
      fn microphone_is_initialized(&self) -> bool { true }
      fn speaker_volume_is_available(&self, available: &mut bool) -> i32 { *available = false; 0 }
      fn set_speaker_volume(&self, volume: u32) -> i32 { 0 }
      fn speaker_volume(&self, volume: &mut u32) -> i32 { *volume = 0; 0 }
      fn max_speaker_volume(&self, volume: &mut u32) -> i32 { *volume = 0; 0 }
      fn min_speaker_volume(&self, volume: &mut u32) -> i32 { *volume = 0; 0 }
      fn microphone_volume_is_available(&self, available: &mut bool) -> i32 { *available = false; 0 }
      fn set_microphone_volume(&self, volume: u32) -> i32 { 0 }
      fn microphone_volume(&self, volume: &mut u32) -> i32 { *volume = 0; 0 }
      fn max_microphone_volume(&self, volume: &mut u32) -> i32 { *volume = 0; 0 }
      fn min_microphone_volume(&self, volume: &mut u32) -> i32 { *volume = 0; 0 }
      fn speaker_mute_is_available(&self, available: &mut bool) -> i32 { *available = false; 0 }
      fn set_speaker_mute(&self, enable: bool) -> i32 { 0 }
      fn speaker_mute(&self, enabled: &mut bool) -> i32 { *enabled = false; 0 }
      fn microphone_mute_is_available(&self, available: &mut bool) -> i32 { *available = false; 0 }
      fn set_microphone_mute(&self, enable: bool) -> i32 { 0 }
      fn microphone_mute(&self, enabled: &mut bool) -> i32 { *enabled = false; 0 }
      fn stereo_playout_is_available(&self, available: &mut bool) -> i32 { *available = false; 0 }
      fn set_stereo_playout(&self, enable: bool) -> i32 { 0 }
      fn stereo_playout(&self, enabled: &mut bool) -> i32 { *enabled = false; 0 }
      fn stereo_recording_is_available(&self, available: &mut bool) -> i32 { *available = false; 0 }
      fn set_stereo_recording(&self, enable: bool) -> i32 { 0 }
      fn stereo_recording(&self, enabled: &mut bool) -> i32 { *enabled = false; 0 }
      fn playout_delay(&self, delay_ms: &mut u16) -> i32 { ... }
      fn built_in_aec_is_available(&self) -> bool
      fn built_in_agc_is_available(&self) -> bool
      fn built_in_ns_is_available(&self) -> bool
      fn enable_built_in_aec(&self, enable: bool) -> i32
      fn enable_built_in_agc(&self, enable: bool) -> i32
      fn enable_built_in_ns(&self, enable: bool) -> i32
      fn get_playout_underrun_count(&self) -> i32
      fn get_playout_audio_parameters(&self, params: &mut Option<AudioParameters>) -> i32
      fn get_record_audio_parameters(&self, params: &mut Option<AudioParameters>) -> i32
      fn get_stats(&self) -> Option<AudioDeviceModuleStats>
  }
  ```
- 補足:
  - トレイト境界は `Send + Sync`。全メソッドが `&self` (内部可変性が必要)。
  - 録音駆動側の受け口は別トレイト `AudioTransportHandler` (`src/api/audio_device_module.rs:495`、境界は `Send` のみ) で、`recorded_data_is_available` / `need_more_play_data` / `pull_render_data` の 3 メソッドを持つ。`AudioTransport::new_with_handler` (378 行) で生成する。
  - crate ルートから `pub use api::*;` で re-export される (`src/lib.rs`)。feature gate は無く、`shiguredo_webrtc` の既定 feature のみで使える。

## まとめ表

| # | 項目 | 結論 |
| --- | --- | --- |
| 1 | `on_disconnect` (切断結果) | 受け口なし |
| 2 | `on_set_offer` (offer SDP) | 受け口なし |
| 3 | サーバーからの RPC 要求受信 | 受け口なし |
| 4 | `on_switched` | 受け口あり (引数なし) |
| 5 | 音声 encoded transform | 受け口なし (映像のみ) |
| 6 | `degradation_preference` / `audio_streaming_language_code` / `spotlight_number` / 送信側 simulcast rid | 4 項目とも sora_sdk の接続設定としては受け口なし |
| 7 | libcamera | 受け口あり (`libcamera` feature) |
| 8 | `MediaStreamTrack.state()` / `RtpReceiver.stream_id()` | どちらも受け口なし |
| 9 | VAD | 受け口なし |
| 10 | 音声リサンプラ | 受け口なし |
| 11 | `AudioMixer` / `configure_dependencies` / `AdmConfig` | AudioMixer なし / 同名 API なし (ADM 限定の差し替え経路あり) / `AdmConfig` は 3 種 |
| 12 | `AudioDeviceModuleHandler` | 受け口あり |

判定不能の項目は無い。12 項目すべてについて crate 同梱のソースを読んで確認した。
