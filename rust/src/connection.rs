//! 接続とコールバック中継の Python 公開型。
//!
//! 既存 `sora_sdk` の `Sora` / `SoraConnection` に対応する。
//! 受信段階の範囲として、作成・接続・切断・統計と受信系コールバック中継を持つ。

use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::time::{Duration, Instant};

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use shiguredo_webrtc::{RtpReceiver, RtpTransceiver};
use sora_sdk::{
    Role, SignalingDirection, SignalingType, SoraConnectionContext, SoraConnectionEventHandler,
    SoraConnectionHandle,
};

use crate::audio_sink::set_callback;
use crate::loopback::validate_base_args;
use crate::track::SoraMediaTrack;

// 接続確立の待ち上限 (秒)。既存テストクライアントの既定に合わせる。
const CONNECT_TIMEOUT_SECS: f64 = 10.0;
// 切断完了の待ち上限 (秒)。既存実装の有限待ちに合わせる。
const DISCONNECT_TIMEOUT_SECS: f64 = 10.0;

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
}

impl CallbackSet {
    /// 空で作る。
    fn new() -> Self {
        Self {
            on_track: Mutex::new(None),
            on_notify: Mutex::new(None),
            on_push: Mutex::new(None),
            on_message: Mutex::new(None),
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
}

impl SoraConnectionEventHandler for RelayHandler {
    fn on_signaling_message(
        &mut self,
        signaling_type: SignalingType,
        direction: SignalingDirection,
        text: &str,
    ) {
        // 既存 API の IntEnum 値に合わせ、種別と方向を数値で渡す。
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
        let track = transceiver.receiver().track();
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
            match Py::new(py, SoraMediaTrack::new(track, self.context.clone())) {
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
            match Py::new(py, SoraMediaTrack::new(track, self.context.clone())) {
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
        // Rust 側にペイロードがないため空文字を渡す。差分として記録する。
        self.callbacks
            .call(&self.callbacks.on_switched, (String::new(),));
    }

    fn on_websocket_close(&mut self, code: Option<u16>, reason: &str) {
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
    run_task: tokio::task::JoinHandle<sora_sdk::Result<()>>,
    /// 操作用ハンドル。
    handle: SoraConnectionHandle,
}

/// 接続ファクトリ。既存 `Sora` に対応する。
#[pyclass(module = "sora_rust_sdk")]
pub(crate) struct Sora;

#[pymethods]
impl Sora {
    /// ファクトリを作る。
    #[new]
    fn new() -> Self {
        Self
    }

    /// 接続を作る。受信段階では受信に必要な引数だけを受け付ける。
    #[pyo3(signature = (signaling_urls, role, channel_id, metadata = None))]
    fn create_connection(
        &self,
        signaling_urls: Vec<String>,
        role: String,
        channel_id: String,
        metadata: Option<String>,
    ) -> PyResult<SoraConnection> {
        let args = validate_base_args(signaling_urls, channel_id, metadata, 1.0)?;
        let role = Role::parse(&role).map_err(|_| {
            PyValueError::new_err(format!(
                "invalid role \"{role}\", expected sendonly, recvonly or sendrecv"
            ))
        })?;
        Ok(SoraConnection::new(
            args.signaling_urls,
            role,
            args.channel_id,
            args.metadata,
        ))
    }
}

/// 接続。既存 `SoraConnection` に対応する。
#[pyclass(module = "sora_rust_sdk")]
pub(crate) struct SoraConnection {
    /// 接続先 URL 群。
    signaling_urls: Vec<String>,
    /// ロール。
    role: Role,
    /// チャネル ID。
    channel_id: String,
    /// メタデータ JSON。
    metadata: Option<sora_sdk::JsonString>,
    /// コールバック群。
    callbacks: Arc<CallbackSet>,
    /// factory 所有のコンテキスト。Sink 破棄まで factory を生かす。
    context: Mutex<Option<Arc<SoraConnectionContext>>>,
    /// 稼働中の接続。
    live: Mutex<Option<LiveConnection>>,
}

impl SoraConnection {
    /// 接続を作る。
    fn new(
        signaling_urls: Vec<String>,
        role: Role,
        channel_id: String,
        metadata: Option<sora_sdk::JsonString>,
    ) -> Self {
        Self {
            signaling_urls,
            role,
            channel_id,
            metadata,
            callbacks: Arc::new(CallbackSet::new()),
            context: Mutex::new(None),
            live: Mutex::new(None),
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
        // 受信引き抜きの駆動に偽デバイスを使う。既定の Dummy ADM では
        // 再生ループがなく音声が流れないため。
        let context_config = sora_sdk::SoraConnectionContextConfig {
            adm_config: sora_sdk::AdmConfig::UseExternal(
                crate::fake_audio_device::FakeAudioDevice::new().into_device_module(),
            ),
            ..Default::default()
        };
        let context = SoraConnectionContext::new_with_config(context_config).map_err(|e| {
            PyRuntimeError::new_err(format!("failed to create connection context: {e}"))
        })?;
        let mut builder = sora_sdk::SoraConnection::builder(
            context.clone(),
            self.signaling_urls.clone(),
            self.channel_id.clone(),
            self.role,
            RelayHandler {
                callbacks: self.callbacks.clone(),
                context: context.clone(),
            },
        );
        *self.context.lock().expect("connection lock poisoned") = Some(context);
        if let Some(metadata) = self.metadata.clone() {
            builder = builder.metadata(metadata);
        }
        let (connection, handle) = builder
            .build()
            .map_err(|e| PyRuntimeError::new_err(format!("failed to build connection: {e}")))?;
        let runtime = crate::runtime();
        py.detach(|| {
            let run_task = runtime.spawn(async move { connection.run().await });
            *self.live.lock().expect("connection lock poisoned") =
                Some(LiveConnection { run_task, handle });
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

    /// 切断し、終了を最大 10 秒待つ。
    fn disconnect(&self, py: Python<'_>) -> PyResult<()> {
        let live = self.live.lock().expect("connection lock poisoned").take();
        let Some(live) = live else {
            return Err(PyRuntimeError::new_err("not connected"));
        };
        let LiveConnection { run_task, handle } = live;
        let runtime = crate::runtime();
        py.detach(|| {
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
        })
    }

    /// 統計情報を JSON 文字列で返す。
    fn get_stats(&self, py: Python<'_>) -> PyResult<String> {
        let guard = self.live.lock().expect("connection lock poisoned");
        let Some(live) = guard.as_ref() else {
            return Err(PyRuntimeError::new_err("not connected"));
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
