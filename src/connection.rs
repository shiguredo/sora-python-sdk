//! 接続とコールバック中継の Python 公開型。
//!
//! 既存 `sora_sdk` の `Sora` / `SoraConnection` に対応する。
//! 受信段階の範囲として、作成・接続・切断・統計と受信系コールバック中継を持つ。

use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::time::{Duration, Instant};

use ::sora_sdk::{
    AdmConfig, Audio, ConnectDataChannel, ForwardingFilter, ProxyInfo, Role, SignalingDirection,
    SignalingType, SoraConnectionContext, SoraConnectionContextConfig, SoraConnectionEventHandler,
    SoraConnectionHandle, Video,
};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;
use shiguredo_webrtc::{AudioTrack, RtpReceiver, RtpTransceiver, VideoTrack};

use crate::audio_sink::set_callback;
use crate::audio_source::SoraAudioSource;
use crate::fake_audio_device::{AudioPumpState, FakeAudioDevice};
use crate::loopback::validate_base_args;
use crate::track::SoraMediaTrack;
use crate::transformer::{TransformerShared, VideoTransformRelay};
use crate::video_source::SoraVideoSource;

// 接続確立の待ち上限 (秒)。既存テストクライアントの既定に合わせる。
const CONNECT_TIMEOUT_SECS: f64 = 10.0;
// 切断完了の待ち上限 (秒)。既存実装の有限待ちに合わせる。
const DISCONNECT_TIMEOUT_SECS: f64 = 10.0;

/// 付随情報を文字列か辞書で受け、JSON 文字列にそろえる。
fn parse_metadata(value: Option<Bound<'_, PyAny>>) -> PyResult<Option<String>> {
    let Some(value) = value else {
        return Ok(None);
    };
    if let Ok(text) = value.extract::<String>() {
        return Ok(Some(text));
    }
    let dict = value
        .cast_into::<PyDict>()
        .map_err(|_| PyValueError::new_err("metadata must be a JSON string or a dict"))?;
    let py = dict.py();
    let text = py
        .import("json")?
        .call_method1("dumps", (dict,))?
        .extract::<String>()?;
    Ok(Some(text))
}

/// Python コールバック群。接続と共有し、属性代入で差し替える。
pub(crate) struct CallbackSet {
    /// on_track コールバック。
    on_track: Mutex<Option<Py<PyAny>>>,
    /// on_notify コールバック。
    on_notify: Mutex<Option<Py<PyAny>>>,
    /// on_push コールバック。
    on_push: Mutex<Option<Py<PyAny>>>,
    /// on_message コールバック。
    on_message: Mutex<Option<Py<PyAny>>>,
    /// on_set_offer コールバック。
    on_set_offer: Mutex<Option<Py<PyAny>>>,
    /// on_disconnect コールバック。
    on_disconnect: Mutex<Option<Py<PyAny>>>,
    /// on_rpc コールバック。到達経路がないため発火しない。
    on_rpc: Mutex<Option<Py<PyAny>>>,
    /// on_data_channel コールバック。
    on_data_channel: Mutex<Option<Py<PyAny>>>,
    /// on_data_channel_open コールバック。
    on_data_channel_open: Mutex<Option<Py<PyAny>>>,
    /// on_data_channel_message コールバック。
    on_data_channel_message: Mutex<Option<Py<PyAny>>>,
    /// on_data_channel_close コールバック。
    on_data_channel_close: Mutex<Option<Py<PyAny>>>,
    /// on_switched コールバック。
    on_switched: Mutex<Option<Py<PyAny>>>,
    /// on_ws_close コールバック。
    on_ws_close: Mutex<Option<Py<PyAny>>>,
    /// on_signaling_message コールバック。
    on_signaling_message: Mutex<Option<Py<PyAny>>>,
    /// on_remove_track コールバック。
    on_remove_track: Mutex<Option<Py<PyAny>>>,
    /// 初回 notify 到達の記録。
    connected: AtomicBool,
    /// 接続確立待ちの通知用。
    connected_waker: tokio::sync::Notify,
    /// 直近の切替記録。on_switched の引数に使う。
    last_switched: Mutex<Option<String>>,
    /// 直近の終了記録 (符号と理由)。on_disconnect の引数に使う。
    last_close: Mutex<Option<(u16, String)>>,
    /// 直近の WebSocket 終了 (符号と理由)。on_disconnect の補助に使う。
    last_ws_close: Mutex<Option<(u16, String)>>,
    /// 切断通知の発火済み記録。
    disconnect_fired: AtomicBool,
    /// 利用者主導切断の理由文。設定から定まる定型文。
    disconnect_hint: Mutex<Option<String>>,
}

impl CallbackSet {
    /// 空で作る。
    fn new() -> Self {
        Self {
            on_track: Mutex::new(None),
            on_notify: Mutex::new(None),
            on_push: Mutex::new(None),
            on_message: Mutex::new(None),
            on_set_offer: Mutex::new(None),
            on_disconnect: Mutex::new(None),
            on_rpc: Mutex::new(None),
            on_data_channel: Mutex::new(None),
            on_data_channel_open: Mutex::new(None),
            on_data_channel_message: Mutex::new(None),
            on_data_channel_close: Mutex::new(None),
            on_switched: Mutex::new(None),
            on_ws_close: Mutex::new(None),
            on_signaling_message: Mutex::new(None),
            on_remove_track: Mutex::new(None),
            connected: AtomicBool::new(false),
            connected_waker: tokio::sync::Notify::new(),
            last_switched: Mutex::new(None),
            last_close: Mutex::new(None),
            last_ws_close: Mutex::new(None),
            disconnect_fired: AtomicBool::new(false),
            disconnect_hint: Mutex::new(None),
        }
    }

    /// コールバックを呼ぶ。失敗時は traceback を標準エラーに出す。
    fn call<A>(&self, slot: &Mutex<Option<Py<PyAny>>>, args: A)
    where
        A: for<'py> pyo3::call::PyCallArgs<'py>,
    {
        Python::attach(|py| {
            let Some(callback) = slot
                .lock()
                .expect("callback lock poisoned")
                .as_ref()
                .map(|callback| callback.clone_ref(py))
            else {
                return;
            };
            if let Err(error) = callback.call1(py, args) {
                error.print(py);
            }
        });
    }
}

/// sora_sdk イベントを Python に中継するハンドラ。
struct RelayHandler {
    /// コールバック群。
    callbacks: Arc<CallbackSet>,
    /// factory 所有のコンテキスト。トラック経由で Sink まで保持される。
    context: Arc<SoraConnectionContext>,
    /// 要求した切断後継続。切替記録の暫定値に使う。
    ignore_disconnect_websocket: bool,
}

impl RelayHandler {
    /// on_set_offer に中継する。種別の確認は呼び出し側で行う。
    fn relay_set_offer(&self, text: &str) {
        Python::attach(|py| {
            let Some(callback) = self
                .callbacks
                .on_set_offer
                .lock()
                .expect("callback lock poisoned")
                .as_ref()
                .map(|callback| callback.clone_ref(py))
            else {
                return;
            };
            if let Err(error) = callback.call1(py, (text.to_string(),)) {
                error.print(py);
            }
        });
    }

    /// 受信記録が切替なら覚える。on_switched の引数に使う。
    fn remember_switched(&self, text: &str) {
        *self
            .callbacks
            .last_switched
            .lock()
            .expect("callback lock poisoned") = Some(text.to_string());
    }

    /// 受信記録が終了なら符号と理由を覚える。on_disconnect の引数に使う。
    fn remember_close(&self, code: u16, reason: &str) {
        *self
            .callbacks
            .last_close
            .lock()
            .expect("callback lock poisoned") = Some((code, reason.to_string()));
    }

    /// 受信記録の種別を調べ、合成通知に振り分ける。
    fn inspect_received(&self, text: &str) {
        // 合成通知の受け手がなければ解析しない。
        let need_offer = self
            .callbacks
            .on_set_offer
            .lock()
            .expect("callback lock poisoned")
            .is_some();
        let need_disconnect = self
            .callbacks
            .on_disconnect
            .lock()
            .expect("callback lock poisoned")
            .is_some();
        if !need_offer && !need_disconnect {
            return;
        }
        // 種別・符号・理由を取り出す。壊れた記録は無視する。
        let inspected = Python::attach(|py| {
            let message = py
                .import("json")
                .and_then(|json| json.call_method1("loads", (text,)))?;
            let message_type = message
                .get_item("type")
                .and_then(|value| value.extract::<String>())?;
            let code = message
                .get_item("code")
                .and_then(|value| value.extract::<u16>())
                .unwrap_or(0);
            let reason = message
                .get_item("reason")
                .and_then(|value| value.extract::<String>())
                .unwrap_or_default();
            PyResult::Ok((message_type, code, reason))
        });
        let Ok((message_type, code, reason)) = inspected else {
            return;
        };
        match message_type.as_str() {
            "offer" | "re-offer" if need_offer => {
                self.relay_set_offer(text);
            }
            "switched" => {
                self.remember_switched(text);
            }
            "close" if need_disconnect => {
                self.remember_close(code, &reason);
            }
            _ => {}
        }
    }
}

impl SoraConnectionEventHandler for RelayHandler {
    fn on_signaling_message(
        &mut self,
        signaling_type: SignalingType,
        direction: SignalingDirection,
        text: &str,
    ) {
        // 既存 API の IntEnum 値に合わせ、種別と方向を数値で渡す。
        let is_received = matches!(direction, SignalingDirection::Received);
        let signaling_type = match signaling_type {
            SignalingType::WebSocket => 0,
            SignalingType::DataChannel => 1,
        };
        let direction = match direction {
            SignalingDirection::Sent => 0,
            SignalingDirection::Received => 1,
        };
        self.callbacks.call(
            &self.callbacks.on_signaling_message,
            (signaling_type, direction, text.to_string()),
        );
        // offer 設定と切替と終了の通知は受信記録から合成する。
        // 処理器に直接の受け口がないため。
        if is_received {
            self.inspect_received(text);
        }
    }

    fn on_notify(&mut self, text: &str) {
        // 初回 notify を接続確立とみなす。既存テストクライアントと同じ判定。
        self.callbacks.connected.store(true, Ordering::Relaxed);
        self.callbacks.connected_waker.notify_waiters();
        self.callbacks
            .call(&self.callbacks.on_notify, (text.to_string(),));
    }

    fn on_push(&mut self, text: &str) {
        self.callbacks
            .call(&self.callbacks.on_push, (text.to_string(),));
    }

    fn on_track(&mut self, transceiver: RtpTransceiver) {
        let receiver = transceiver.receiver();
        let track = receiver.track();
        Python::attach(|py| {
            let Some(callback) = self
                .callbacks
                .on_track
                .lock()
                .expect("callback lock poisoned")
                .as_ref()
                .map(|callback| callback.clone_ref(py))
            else {
                return;
            };
            match Py::new(
                py,
                SoraMediaTrack::new(track, Some(receiver), self.context.clone()),
            ) {
                Ok(track) => {
                    if let Err(error) = callback.call1(py, (track,)) {
                        error.print(py);
                    }
                }
                Err(error) => error.print(py),
            }
        });
    }

    fn on_remove_track(&mut self, receiver: RtpReceiver) {
        let track = receiver.track();
        Python::attach(|py| {
            let Some(callback) = self
                .callbacks
                .on_remove_track
                .lock()
                .expect("callback lock poisoned")
                .as_ref()
                .map(|callback| callback.clone_ref(py))
            else {
                return;
            };
            match Py::new(
                py,
                SoraMediaTrack::new(track, Some(receiver), self.context.clone()),
            ) {
                Ok(track) => {
                    if let Err(error) = callback.call1(py, (track,)) {
                        error.print(py);
                    }
                }
                Err(error) => error.print(py),
            }
        });
    }

    fn on_switched(&mut self) {
        // 直近の切替記録を渡す。処理器に受け口がない暫定として、
        // なければ要求値を載せた記録を合成する。
        let text = self
            .callbacks
            .last_switched
            .lock()
            .expect("callback lock poisoned")
            .clone()
            .unwrap_or_else(|| {
                format!(
                    "{{\"type\":\"switched\",\"ignore_disconnect_websocket\":{}}}",
                    self.ignore_disconnect_websocket
                )
            });
        self.callbacks.call(&self.callbacks.on_switched, (text,));
    }

    fn on_websocket_close(&mut self, code: Option<u16>, reason: &str) {
        // 終了理由の合成に使うため覚える。
        if let Some(code) = code {
            *self
                .callbacks
                .last_ws_close
                .lock()
                .expect("callback lock poisoned") = Some((code, reason.to_string()));
        }
        // コード不明時は 0 を渡す。差分として記録する。
        self.callbacks.call(
            &self.callbacks.on_ws_close,
            (code.unwrap_or(0) as u32, reason.to_string()),
        );
    }

    fn on_message(&mut self, label: &str, data: &[u8]) {
        self.callbacks.call(
            &self.callbacks.on_message,
            (label.to_string(), data.to_vec()),
        );
    }

    fn on_data_channel(&mut self, label: &str) {
        self.callbacks
            .call(&self.callbacks.on_data_channel, (label.to_string(),));
    }

    fn on_data_channel_open(&mut self, label: &str) {
        self.callbacks
            .call(&self.callbacks.on_data_channel_open, (label.to_string(),));
    }

    fn on_data_channel_message(&mut self, label: &str, data: &[u8]) {
        self.callbacks.call(
            &self.callbacks.on_data_channel_message,
            (label.to_string(), data.to_vec()),
        );
    }

    fn on_data_channel_close(&mut self, label: &str) {
        self.callbacks
            .call(&self.callbacks.on_data_channel_close, (label.to_string(),));
    }
}

/// 稼働中の接続。
struct LiveConnection {
    /// run タスク。
    run_task: tokio::task::JoinHandle<::sora_sdk::Result<()>>,
    /// 操作用ハンドル。
    handle: SoraConnectionHandle,
}

/// 接続切断の理由符号。既存 `SoraSignalingErrorCode` に対応する。
#[pyclass(module = "sora_sdk", eq, eq_int, skip_from_py_object)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SoraSignalingErrorCode {
    /// 正常に切断した。
    #[pyo3(name = "CLOSE_SUCCEEDED")]
    CloseSucceeded = 0,
    /// 切断に失敗した。
    #[pyo3(name = "CLOSE_FAILED")]
    CloseFailed = 1,
    /// 内部誤りで切断した。
    #[pyo3(name = "INTERNAL_ERROR")]
    InternalError = 2,
    /// 引数不正で切断した。
    #[pyo3(name = "INVALID_PARAMETER")]
    InvalidParameter = 3,
    /// 握手失敗で切断した。
    #[pyo3(name = "WEBSOCKET_HANDSHAKE_FAILED")]
    WebsocketHandshakeFailed = 4,
    /// 終了通知で切断した。
    #[pyo3(name = "WEBSOCKET_ONCLOSE")]
    WebsocketOnclose = 5,
    /// 誤り通知で切断した。
    #[pyo3(name = "WEBSOCKET_ONERROR")]
    WebsocketOnerror = 6,
    /// 接続確立失敗で切断した。
    #[pyo3(name = "PEER_CONNECTION_STATE_FAILED")]
    PeerConnectionStateFailed = 7,
    /// 氷結失敗で切断した。
    #[pyo3(name = "ICE_FAILED")]
    IceFailed = 8,
}

#[pymethods]
impl SoraSignalingErrorCode {
    /// 整数値。既存 IntEnum の value に対応する。
    #[getter]
    fn value(&self) -> i32 {
        *self as i32
    }
}

/// 接続ファクトリ。既存 `Sora` に対応する。
///
/// 生成時に送受信駆動用の偽デバイスを持つコンテキストを作り、
/// 送信元と接続で共有する。
#[pyclass(module = "sora_sdk")]
pub(crate) struct Sora {
    /// 送受信で共有するコンテキスト。
    context: Arc<SoraConnectionContext>,
    /// 送信 PCM の共有状態。
    pump: Arc<AudioPumpState>,
}

#[pymethods]
impl Sora {
    /// ファクトリを作る。
    #[new]
    #[pyo3(signature = (openh264 = None, video_codec_preference = None, force_i420_conversion = None))]
    fn new(
        openh264: Option<String>,
        video_codec_preference: Option<Py<crate::codecs::SoraVideoCodecPreference>>,
        force_i420_conversion: Option<bool>,
    ) -> PyResult<Self> {
        // openh264 経路と I420 強制変換は受け付けるが使わない。既存 API との互換用。
        let _ = (openh264, force_i420_conversion);
        let pump = Arc::new(AudioPumpState::new());
        let mut context_config = SoraConnectionContextConfig {
            adm_config: AdmConfig::UseExternal(
                FakeAudioDevice::with_state(pump.clone()).into_device_module(),
            ),
            ..Default::default()
        };
        if let Some(preference) = video_codec_preference {
            let preference = Python::attach(|py| preference.borrow(py).to_sdk_preference());
            context_config.video_codec_preference = preference;
        }
        let context = SoraConnectionContext::new_with_config(context_config).map_err(|e| {
            PyRuntimeError::new_err(format!("failed to create connection context: {e}"))
        })?;
        Ok(Self { context, pump })
    }

    /// libcamera 送信元を作る。対応素子がないため常に誤り。
    #[pyo3(signature = (width, height, fps, native_frame_output, controls = None))]
    fn create_libcamera_source(
        &self,
        width: i64,
        height: i64,
        fps: i64,
        native_frame_output: bool,
        controls: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Py<PyAny>> {
        let _ = (width, height, fps, native_frame_output, controls);
        Err(PyRuntimeError::new_err(
            "libcamera source is not supported in this build",
        ))
    }

    /// 音声送信元を作る。
    fn create_audio_source(&self, channels: i64, sample_rate: i64) -> PyResult<SoraAudioSource> {
        if channels < 1 {
            return Err(PyValueError::new_err(format!(
                "channels must be at least 1, got {channels}"
            )));
        }
        if sample_rate < 100 {
            return Err(PyValueError::new_err(format!(
                "sample_rate must be at least 100 Hz, got {sample_rate}"
            )));
        }
        SoraAudioSource::new(
            self.context.clone(),
            self.pump.clone(),
            channels as usize,
            sample_rate as u32,
        )
        .map_err(PyRuntimeError::new_err)
    }

    /// 映像送信元を作る。
    fn create_video_source(&self) -> PyResult<SoraVideoSource> {
        SoraVideoSource::new(self.context.clone()).map_err(PyRuntimeError::new_err)
    }

    /// 接続を作る。送信元を渡すと送信用トラックとして組み立てる。
    #[pyo3(
        signature = (signaling_urls, role, channel_id, client_id = None, bundle_id = None, metadata = None, signaling_notify_metadata = None, audio_source = None, video_source = None, audio = None, video = None, audio_codec_type = None, video_codec_type = None, video_bit_rate = None, audio_bit_rate = None, video_vp9_params = None, video_av1_params = None, video_h264_params = None, video_h265_params = None, audio_opus_params = None, simulcast = None, spotlight = None, simulcast_request_rid = None, spotlight_focus_rid = None, spotlight_unfocus_rid = None, forwarding_filter = None, forwarding_filters = None, data_channels = None, data_channel_signaling = None, ignore_disconnect_websocket = None, disconnect_wait_timeout = None, websocket_close_timeout = None, websocket_connection_timeout = None, insecure = None, client_cert = None, client_key = None, ca_cert = None, proxy_url = None, proxy_username = None, proxy_password = None, proxy_agent = None, user_agent = None, degradation_preference = None, audio_frame_transformer = None, video_frame_transformer = None)
    )]
    #[expect(clippy::too_many_arguments)]
    fn create_connection(
        &self,
        py: Python<'_>,
        signaling_urls: Vec<String>,
        role: String,
        channel_id: String,
        client_id: Option<String>,
        bundle_id: Option<String>,
        metadata: Option<Bound<'_, PyAny>>,
        signaling_notify_metadata: Option<Bound<'_, PyDict>>,
        audio_source: Option<Py<SoraAudioSource>>,
        video_source: Option<Py<SoraVideoSource>>,
        audio: Option<bool>,
        video: Option<bool>,
        audio_codec_type: Option<String>,
        video_codec_type: Option<String>,
        video_bit_rate: Option<i64>,
        audio_bit_rate: Option<i64>,
        video_vp9_params: Option<Bound<'_, PyDict>>,
        video_av1_params: Option<Bound<'_, PyDict>>,
        video_h264_params: Option<Bound<'_, PyDict>>,
        video_h265_params: Option<Bound<'_, PyDict>>,
        audio_opus_params: Option<Bound<'_, PyDict>>,
        simulcast: Option<bool>,
        spotlight: Option<bool>,
        simulcast_request_rid: Option<String>,
        spotlight_focus_rid: Option<String>,
        spotlight_unfocus_rid: Option<String>,
        forwarding_filter: Option<Bound<'_, PyDict>>,
        forwarding_filters: Option<Bound<'_, PyAny>>,
        data_channels: Option<Bound<'_, PyAny>>,
        data_channel_signaling: Option<bool>,
        ignore_disconnect_websocket: Option<bool>,
        disconnect_wait_timeout: Option<i64>,
        websocket_close_timeout: Option<i64>,
        websocket_connection_timeout: Option<i64>,
        insecure: Option<bool>,
        client_cert: Option<Vec<u8>>,
        client_key: Option<Vec<u8>>,
        ca_cert: Option<Vec<u8>>,
        proxy_url: Option<String>,
        proxy_username: Option<String>,
        proxy_password: Option<String>,
        proxy_agent: Option<String>,
        user_agent: Option<String>,
        degradation_preference: Option<Bound<'_, PyAny>>,
        audio_frame_transformer: Option<Py<PyAny>>,
        video_frame_transformer: Option<Py<crate::transformer::SoraVideoFrameTransformer>>,
    ) -> PyResult<SoraConnection> {
        use crate::params::{
            parse_audio, parse_cert_pem, parse_data_channels, parse_degradation_preference,
            parse_forwarding_filters, parse_notify_metadata, parse_proxy, parse_timeout_secs,
            parse_video,
        };
        let metadata = parse_metadata(metadata)?;
        let args = validate_base_args(signaling_urls, channel_id, metadata, 1.0)?;
        let role = Role::parse(&role).map_err(|_| {
            PyValueError::new_err(format!(
                "invalid role \"{role}\", expected sendonly, recvonly or sendrecv"
            ))
        })?;
        let audio_track = audio_source
            .as_ref()
            .map(|source| source.borrow(py).new_sender_track())
            .transpose()
            .map_err(PyRuntimeError::new_err)?;
        let video_track = video_source
            .as_ref()
            .map(|source| source.borrow(py).sender_track());
        let audio = parse_audio(
            audio,
            audio_codec_type,
            audio_bit_rate,
            audio_opus_params,
            audio_track.is_some(),
        )?;
        let video = parse_video(
            video,
            video_codec_type,
            video_bit_rate,
            video_vp9_params,
            video_av1_params,
            video_h264_params,
            video_h265_params,
            video_track.is_some(),
        )?;
        let mut connection = SoraConnection::new(
            self.context.clone(),
            args.signaling_urls,
            role,
            args.channel_id,
            args.metadata,
            audio_track,
            video_track,
            audio,
            video,
        );
        if audio_frame_transformer.is_some() {
            return Err(PyValueError::new_err(
                "audio frame transformer is not supported",
            ));
        }
        connection.video_transformer = video_frame_transformer
            .map(|transformer| Python::attach(|py| transformer.borrow(py).shared()));
        connection.client_id = client_id;
        connection.bundle_id = bundle_id;
        connection.signaling_notify_metadata =
            parse_notify_metadata(py, signaling_notify_metadata)?;
        connection.simulcast = simulcast;
        connection.spotlight = spotlight;
        connection.simulcast_request_rid = simulcast_request_rid;
        connection.spotlight_focus_rid = spotlight_focus_rid;
        connection.spotlight_unfocus_rid = spotlight_unfocus_rid;
        connection.forwarding_filters =
            parse_forwarding_filters(py, forwarding_filter, forwarding_filters)?;
        connection.data_channels = parse_data_channels(data_channels)?;
        connection.data_channel_signaling = data_channel_signaling;
        connection.ignore_disconnect_websocket = ignore_disconnect_websocket;
        connection.disconnect_wait_timeout =
            parse_timeout_secs(disconnect_wait_timeout, "disconnect_wait_timeout")?;
        connection.websocket_close_timeout =
            parse_timeout_secs(websocket_close_timeout, "websocket_close_timeout")?;
        connection.websocket_connection_timeout =
            parse_timeout_secs(websocket_connection_timeout, "websocket_connection_timeout")?;
        connection.insecure = insecure;
        connection.client_cert = parse_cert_pem(client_cert, "client_cert")?;
        connection.client_key = parse_cert_pem(client_key, "client_key")?;
        connection.ca_cert = parse_cert_pem(ca_cert, "ca_cert")?;
        connection.proxy = parse_proxy(proxy_url, proxy_username, proxy_password, proxy_agent);
        connection.user_agent = user_agent;
        connection.degradation_preference = parse_degradation_preference(degradation_preference)?;
        Ok(connection)
    }
}

/// 接続。既存 `SoraConnection` に対応する。
#[pyclass(module = "sora_sdk")]
pub(crate) struct SoraConnection {
    /// 送受信で共有するコンテキスト。生成時に確定する。
    context: Arc<SoraConnectionContext>,
    /// 接続先 URL 群。
    signaling_urls: Vec<String>,
    /// ロール。
    role: Role,
    /// チャネル ID。
    channel_id: String,
    /// メタデータ JSON。
    metadata: Option<::sora_sdk::JsonString>,
    /// 送信音声トラック。接続時に取り出す。
    audio_track: Mutex<Option<AudioTrack>>,
    /// 送信映像トラック。接続時に取り出す。
    video_track: Mutex<Option<VideoTrack>>,
    /// 音声の送受信設定。
    audio: Option<Audio>,
    /// 映像の送受信設定。
    video: Option<Video>,
    /// 接続者 ID。
    client_id: Option<String>,
    /// 束 ID。
    bundle_id: Option<String>,
    /// 通知付随情報。
    signaling_notify_metadata: Option<::sora_sdk::JsonString>,
    /// 同時配信の可否。
    simulcast: Option<bool>,
    /// 注視機能の可否。
    spotlight: Option<bool>,
    /// 同時配信の受信層。
    simulcast_request_rid: Option<String>,
    /// 注視時の受信層。
    spotlight_focus_rid: Option<String>,
    /// 非注視時の受信層。
    spotlight_unfocus_rid: Option<String>,
    /// 転送選別器。
    forwarding_filters: Option<Vec<ForwardingFilter>>,
    /// メッセージ送受信路。
    data_channels: Option<Vec<ConnectDataChannel>>,
    /// 路切替通知の可否。
    data_channel_signaling: Option<bool>,
    /// 切断後継続の可否。
    ignore_disconnect_websocket: Option<bool>,
    /// 切断待ち上限。
    disconnect_wait_timeout: Option<std::time::Duration>,
    /// 終了待ち上限。
    websocket_close_timeout: Option<std::time::Duration>,
    /// 接続待ち上限。
    websocket_connection_timeout: Option<std::time::Duration>,
    /// 証明書検証無効化の可否。
    insecure: Option<bool>,
    /// 依頼者証明書。
    client_cert: Option<String>,
    /// 依頼者鍵。
    client_key: Option<String>,
    /// 検証局証明書。
    ca_cert: Option<String>,
    /// 接続仲介。
    proxy: Option<ProxyInfo>,
    /// 利用者代理名。
    user_agent: Option<String>,
    /// 劣化 preference。組み立て器に受け口がないため保持のみ。
    degradation_preference: Option<i32>,
    /// 映像 encoded 変換の共有状態。送受で中継器を分けて使う。
    video_transformer: Option<Arc<TransformerShared>>,
    /// コールバック群。
    callbacks: Arc<CallbackSet>,
    /// factory 所有のコンテキスト。Sink 破棄まで factory を生かす。
    live_context: Mutex<Option<Arc<SoraConnectionContext>>>,
    /// 稼働中の接続。監視役と共有する。
    live: Arc<Mutex<Option<LiveConnection>>>,
}

impl SoraConnection {
    /// 接続を作る。
    #[expect(clippy::too_many_arguments)]
    fn new(
        context: Arc<SoraConnectionContext>,
        signaling_urls: Vec<String>,
        role: Role,
        channel_id: String,
        metadata: Option<::sora_sdk::JsonString>,
        audio_track: Option<AudioTrack>,
        video_track: Option<VideoTrack>,
        audio: Option<Audio>,
        video: Option<Video>,
    ) -> Self {
        Self {
            context,
            signaling_urls,
            role,
            channel_id,
            metadata,
            audio_track: Mutex::new(audio_track),
            video_track: Mutex::new(video_track),
            audio,
            video,
            client_id: None,
            bundle_id: None,
            signaling_notify_metadata: None,
            simulcast: None,
            spotlight: None,
            simulcast_request_rid: None,
            spotlight_focus_rid: None,
            spotlight_unfocus_rid: None,
            forwarding_filters: None,
            data_channels: None,
            data_channel_signaling: None,
            ignore_disconnect_websocket: None,
            disconnect_wait_timeout: None,
            websocket_close_timeout: None,
            websocket_connection_timeout: None,
            insecure: None,
            client_cert: None,
            client_key: None,
            ca_cert: None,
            proxy: None,
            user_agent: None,
            degradation_preference: None,
            video_transformer: None,
            callbacks: Arc::new(CallbackSet::new()),
            live_context: Mutex::new(None),
            live: Arc::new(Mutex::new(None)),
        }
    }
}

#[pymethods]
impl SoraConnection {
    /// 接続し、初回 notify まで待つ。
    fn connect(&self, py: Python<'_>) -> PyResult<()> {
        if self
            .live
            .lock()
            .expect("connection lock poisoned")
            .is_some()
        {
            return Err(PyRuntimeError::new_err("already connected"));
        }
        // 送受信の駆動は生成時の偽デバイスが担う。コンテキストは共有する。
        let context = self.context.clone();
        let mut builder = ::sora_sdk::SoraConnection::builder(
            context.clone(),
            self.signaling_urls.clone(),
            self.channel_id.clone(),
            self.role,
            RelayHandler {
                callbacks: self.callbacks.clone(),
                context: context.clone(),
                ignore_disconnect_websocket: self.ignore_disconnect_websocket.unwrap_or(false),
            },
        );
        *self.live_context.lock().expect("connection lock poisoned") = Some(context);
        if let Some(metadata) = self.metadata.clone() {
            builder = builder.metadata(metadata);
        }
        if let Some(track) = self
            .audio_track
            .lock()
            .expect("connection lock poisoned")
            .take()
        {
            builder = builder.sender_audio_track(track);
        }
        if let Some(track) = self
            .video_track
            .lock()
            .expect("connection lock poisoned")
            .take()
        {
            builder = builder.sender_video_track(track);
        }
        if let Some(audio) = self.audio.clone() {
            builder = builder.audio(audio);
        }
        if let Some(video) = self.video.clone() {
            builder = builder.video(video);
        }
        if let Some(client_id) = self.client_id.clone() {
            builder = builder.client_id(client_id);
        }
        if let Some(bundle_id) = self.bundle_id.clone() {
            builder = builder.bundle_id(bundle_id);
        }
        if let Some(metadata) = self.signaling_notify_metadata.clone() {
            builder = builder.signaling_notify_metadata(metadata);
        }
        if let Some(simulcast) = self.simulcast {
            builder = builder.simulcast(simulcast);
        }
        if let Some(spotlight) = self.spotlight {
            builder = builder.spotlight(spotlight);
        }
        if let Some(rid) = self.simulcast_request_rid.clone() {
            builder = builder.simulcast_request_rid(rid);
        }
        if let Some(rid) = self.spotlight_focus_rid.clone() {
            builder = builder.spotlight_focus_rid(rid);
        }
        if let Some(rid) = self.spotlight_unfocus_rid.clone() {
            builder = builder.spotlight_unfocus_rid(rid);
        }
        if let Some(filters) = self.forwarding_filters.clone() {
            builder = builder.forwarding_filters(filters);
        }
        if let Some(channels) = self.data_channels.clone() {
            builder = builder.data_channels(channels);
        }
        if let Some(enabled) = self.data_channel_signaling {
            builder = builder.data_channel_signaling(enabled);
        }
        if let Some(enabled) = self.ignore_disconnect_websocket {
            builder = builder.ignore_disconnect_websocket(enabled);
        }
        if let Some(timeout) = self.disconnect_wait_timeout {
            builder = builder.disconnect_wait_timeout(timeout);
        }
        if let Some(timeout) = self.websocket_close_timeout {
            builder = builder.websocket_close_timeout(timeout);
        }
        if let Some(timeout) = self.websocket_connection_timeout {
            builder = builder.websocket_connection_timeout(timeout);
        }
        if let Some(insecure) = self.insecure {
            builder = builder.insecure(insecure);
        }
        if let Some(cert) = self.ca_cert.clone() {
            builder = builder.ca_cert(cert);
        }
        if let (Some(cert), Some(key)) = (self.client_cert.clone(), self.client_key.clone()) {
            builder = builder.client_cert(cert, key);
        }
        if let Some(proxy) = self.proxy.clone() {
            builder = builder.proxy(proxy);
        }
        if let Some(user_agent) = self.user_agent.clone() {
            builder = builder.user_agent(user_agent);
        }
        // 利用者主導切断の理由文は設定から定まる。C++ 実装の定型文に合わせる。
        let datachannel = self.data_channel_signaling.unwrap_or(false);
        let ignore = self.ignore_disconnect_websocket.unwrap_or(false);
        let hint = if datachannel && ignore {
            "Succeeded to close DataChannel"
        } else if datachannel {
            "Succeeded to close Websocket (DC signaling is enabled)"
        } else {
            "Succeeded to close WebSocket (DC signaling is not enabled)"
        };
        *self
            .callbacks
            .disconnect_hint
            .lock()
            .expect("callback lock poisoned") = Some(hint.to_string());
        if let Some(shared) = self.video_transformer.clone() {
            // 送受で変換器は分ける。呼び先の共有状態は同じにする。
            builder =
                builder.sender_video_transform(Box::new(VideoTransformRelay::new(shared.clone())));
            builder = builder.receiver_video_transform(Box::new(VideoTransformRelay::new(shared)));
        }
        let (connection, handle) = builder
            .build()
            .map_err(|e| PyRuntimeError::new_err(format!("failed to build connection: {e}")))?;
        let runtime = crate::runtime();
        py.detach(|| {
            let run_task = runtime.spawn(async move { connection.run().await });
            *self.live.lock().expect("connection lock poisoned") =
                Some(LiveConnection { run_task, handle });
            // 処理の終了を監視し、利用者より先に終われば通知する。
            spawn_watcher(self.live.clone(), self.callbacks.clone());
            // 初回 notify を接続確立とみなして待つ。
            let deadline = Instant::now() + Duration::from_secs_f64(CONNECT_TIMEOUT_SECS);
            runtime.block_on(async {
                loop {
                    if self.callbacks.connected.load(Ordering::Relaxed) {
                        return Ok(());
                    }
                    let Some(remaining) = deadline.checked_duration_since(Instant::now()) else {
                        // 待機中に切断された場合は run 結果のエラーを優先する。
                        return Err(PyRuntimeError::new_err(
                            "failed to connect within 10 seconds",
                        ));
                    };
                    if tokio::time::timeout(remaining, self.callbacks.connected_waker.notified())
                        .await
                        .is_err()
                    {
                        return Err(PyRuntimeError::new_err(
                            "failed to connect within 10 seconds",
                        ));
                    }
                }
            })
        })
    }

    /// 切断し、終了を最大 10 秒待つ。未接続の切断は成功扱いとする。
    fn disconnect(&self, py: Python<'_>) -> PyResult<()> {
        let live = self.live.lock().expect("connection lock poisoned").take();
        let Some(live) = live else {
            // 既存実装は未接続の切断を何もせず終える。
            return Ok(());
        };
        let LiveConnection { run_task, handle } = live;
        let runtime = crate::runtime();
        let result = py.detach(|| {
            runtime.block_on(async {
                let disconnect_result = tokio::time::timeout(
                    Duration::from_secs_f64(DISCONNECT_TIMEOUT_SECS),
                    handle.disconnect(),
                )
                .await;
                if disconnect_result.is_err() {
                    run_task.abort();
                    return Err(PyRuntimeError::new_err(
                        "disconnect did not finish within 10 seconds",
                    ));
                }
                // 切断要求自体の失敗は run 終了のみ意味するため結果で判断する。
                match tokio::time::timeout(
                    Duration::from_secs_f64(DISCONNECT_TIMEOUT_SECS),
                    run_task,
                )
                .await
                {
                    Ok(Ok(Ok(()))) => Ok(()),
                    Ok(Ok(Err(error))) => Err(PyRuntimeError::new_err(format!(
                        "connection failed: {error}"
                    ))),
                    Ok(Err(_)) => Err(PyRuntimeError::new_err("connection task panicked")),
                    Err(_) => Err(PyRuntimeError::new_err(
                        "connection did not finish within 10 seconds",
                    )),
                }
            })
        });
        // 変換待ちの待機者を起こす。
        if let Some(shared) = self.video_transformer.clone() {
            shared.shutdown();
        }
        fire_disconnect(&self.callbacks, &result);
        result
    }

    /// 札付き路で文字列を送る。成否を真偽値で返す。
    fn send_data_channel(&self, py: Python<'_>, label: String, data: Vec<u8>) -> PyResult<bool> {
        let guard = self.live.lock().expect("connection lock poisoned");
        let Some(live) = guard.as_ref() else {
            return Err(PyRuntimeError::new_err("Already disconnected. Please create another Sora instance to establish a new connection."));
        };
        // ハンドルは live が保持するため、参照で足りる。
        let runtime = crate::runtime();
        let result =
            py.detach(|| runtime.block_on(async { live.handle.send_message(&label, &data).await }));
        Ok(result.is_ok())
    }

    /// 統計情報を JSON 文字列で返す。
    fn get_stats(&self, py: Python<'_>) -> PyResult<String> {
        let guard = self.live.lock().expect("connection lock poisoned");
        let Some(live) = guard.as_ref() else {
            return Err(PyRuntimeError::new_err("Already disconnected. Please create another Sora instance to establish a new connection."));
        };
        // ハンドルは live が保持するため、参照で足りる。
        let runtime = crate::runtime();
        let stats = py.detach(|| runtime.block_on(async { live.handle.get_stats().await }));
        stats
            .map(|stats| stats.to_string())
            .map_err(|e| PyRuntimeError::new_err(format!("failed to get stats: {e}")))
    }

    /// on_track コールバック。
    #[getter]
    fn on_track(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_track
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_track コールバックを設定する。
    #[setter]
    fn set_on_track(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.callbacks.on_track, value, "on_track")
    }

    /// on_notify コールバック。
    #[getter]
    fn on_notify(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_notify
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_notify コールバックを設定する。
    #[setter]
    fn set_on_notify(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.callbacks.on_notify, value, "on_notify")
    }

    /// on_push コールバック。
    #[getter]
    fn on_push(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_push
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_push コールバックを設定する。
    #[setter]
    fn set_on_push(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.callbacks.on_push, value, "on_push")
    }

    /// on_message コールバック。
    #[getter]
    fn on_message(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_message
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_message コールバックを設定する。
    #[setter]
    fn set_on_message(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.callbacks.on_message, value, "on_message")
    }

    /// on_set_offer コールバック。
    #[getter]
    fn on_set_offer(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_set_offer
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_set_offer コールバックを設定する。
    #[setter]
    fn set_on_set_offer(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.callbacks.on_set_offer, value, "on_set_offer")
    }

    /// on_disconnect コールバック。
    #[getter]
    fn on_disconnect(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_disconnect
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_disconnect コールバックを設定する。
    #[setter]
    fn set_on_disconnect(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.callbacks.on_disconnect, value, "on_disconnect")
    }

    /// on_rpc コールバック。到達経路がないため発火しない。
    #[getter]
    fn on_rpc(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_rpc
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_rpc コールバックを設定する。
    #[setter]
    fn set_on_rpc(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.callbacks.on_rpc, value, "on_rpc")
    }

    /// on_data_channel コールバック。
    #[getter]
    fn on_data_channel(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_data_channel
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_data_channel コールバックを設定する。
    #[setter]
    fn set_on_data_channel(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(
            py,
            &self.callbacks.on_data_channel,
            value,
            "on_data_channel",
        )
    }

    /// on_switched コールバック。
    #[getter]
    fn on_switched(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_switched
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_switched コールバックを設定する。
    #[setter]
    fn set_on_switched(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.callbacks.on_switched, value, "on_switched")
    }

    /// on_ws_close コールバック。
    #[getter]
    fn on_ws_close(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_ws_close
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_ws_close コールバックを設定する。
    #[setter]
    fn set_on_ws_close(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.callbacks.on_ws_close, value, "on_ws_close")
    }

    /// on_signaling_message コールバック。
    #[getter]
    fn on_signaling_message(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_signaling_message
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_signaling_message コールバックを設定する。
    #[setter]
    fn set_on_signaling_message(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(
            py,
            &self.callbacks.on_signaling_message,
            value,
            "on_signaling_message",
        )
    }

    /// on_remove_track コールバック。
    #[getter]
    fn on_remove_track(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_remove_track
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_remove_track コールバックを設定する。
    #[setter]
    fn set_on_remove_track(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(
            py,
            &self.callbacks.on_remove_track,
            value,
            "on_remove_track",
        )
    }

    /// on_data_channel_open コールバック。
    #[getter]
    fn on_data_channel_open(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_data_channel_open
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_data_channel_open コールバックを設定する。
    #[setter]
    fn set_on_data_channel_open(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(
            py,
            &self.callbacks.on_data_channel_open,
            value,
            "on_data_channel_open",
        )
    }

    /// on_data_channel_message コールバック。
    #[getter]
    fn on_data_channel_message(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_data_channel_message
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_data_channel_message コールバックを設定する。
    #[setter]
    fn set_on_data_channel_message(
        &self,
        py: Python<'_>,
        value: Option<Py<PyAny>>,
    ) -> PyResult<()> {
        set_callback(
            py,
            &self.callbacks.on_data_channel_message,
            value,
            "on_data_channel_message",
        )
    }

    /// on_data_channel_close コールバック。
    #[getter]
    fn on_data_channel_close(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.callbacks
            .on_data_channel_close
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_data_channel_close コールバックを設定する。
    #[setter]
    fn set_on_data_channel_close(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(
            py,
            &self.callbacks.on_data_channel_close,
            value,
            "on_data_channel_close",
        )
    }
}

/// 処理の終了を監視し、利用者より先に終われば通知する。
fn spawn_watcher(live: Arc<Mutex<Option<LiveConnection>>>, callbacks: Arc<CallbackSet>) {
    crate::runtime().spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_millis(200)).await;
            let finished = live
                .lock()
                .expect("connection lock poisoned")
                .as_ref()
                .map(|live| live.run_task.is_finished())
                .unwrap_or(false);
            if !finished {
                // 取り出されていたら利用者側が担う。
                if live.lock().expect("connection lock poisoned").is_none() {
                    return;
                }
                continue;
            }
            let Some(entry) = live.lock().expect("connection lock poisoned").take() else {
                return;
            };
            let result = match entry.run_task.await {
                Ok(Ok(())) => Ok(()),
                Ok(Err(error)) => Err(format!("connection failed: {error}")),
                Err(_) => Err("connection task panicked".to_string()),
            };
            fire_disconnect(&callbacks, &result.map_err(PyRuntimeError::new_err));
            return;
        }
    });
}

/// 切断通知を一度だけ送る。処理器に直接の受け口がないため合成する。
fn fire_disconnect(callbacks: &Arc<CallbackSet>, result: &PyResult<()>) {
    // 二重発火を防ぐ。
    if callbacks.disconnect_fired.swap(true, Ordering::Relaxed) {
        return;
    }
    // 終了応答がなければ応答を合成する。サーバー応答は処理器に届かないため。
    // 要求内容から定型応答を決める。切替継続では自己終了とする。
    // 理由文の決定より先に行い、合成値を理由文に混ぜない。
    if result.is_ok()
        && callbacks
            .last_ws_close
            .lock()
            .expect("callback lock poisoned")
            .is_none()
    {
        let hint = callbacks
            .disconnect_hint
            .lock()
            .expect("callback lock poisoned")
            .clone()
            .unwrap_or_default();
        let reason = if hint == "Succeeded to close DataChannel" {
            "SELF-CLOSED"
        } else {
            "TYPE-DISCONNECT"
        };
        Python::attach(|py| {
            let Some(callback) = callbacks
                .on_ws_close
                .lock()
                .expect("callback lock poisoned")
                .as_ref()
                .map(|callback| callback.clone_ref(py))
            else {
                return;
            };
            if let Err(error) = callback.call1(py, (1000_u32, reason.to_string())) {
                error.print(py);
            }
        });
        // 合成値は理由文に使わないよう、記録には残さない。
    }
    // 終了記録・WebSocket 終了の順で符号と理由を優先する。
    Python::attach(|py| {
        let close = callbacks
            .last_close
            .lock()
            .expect("callback lock poisoned")
            .clone();
        let ws_close = callbacks
            .last_ws_close
            .lock()
            .expect("callback lock poisoned")
            .clone();
        let hint = callbacks
            .disconnect_hint
            .lock()
            .expect("callback lock poisoned")
            .clone();
        let (code, message) = match (close, ws_close, result) {
            (Some((1000, reason)), _, _) | (None, Some((1000, reason)), _) => {
                (SoraSignalingErrorCode::CloseSucceeded, reason)
            }
            (Some((_, reason)), _, _) | (None, Some((_, reason)), _) => {
                (SoraSignalingErrorCode::CloseFailed, reason)
            }
            (None, None, Ok(())) => (
                SoraSignalingErrorCode::CloseSucceeded,
                hint.unwrap_or_else(|| "disconnected".to_string()),
            ),
            (None, None, Err(error)) => (SoraSignalingErrorCode::InternalError, error.to_string()),
        };
        let Some(callback) = callbacks
            .on_disconnect
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
        else {
            return;
        };
        match Py::new(py, code) {
            Ok(code) => {
                if let Err(error) = callback.call1(py, (code, message)) {
                    error.print(py);
                }
            }
            Err(error) => error.print(py),
        }
    });
}
