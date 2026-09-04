//! sora-rust-sdk を PyO3 経由で Python から利用するためのプロトタイプモジュール。
//!
//! 現行の Sora C++ SDK + nanobind 構成とは独立した最小実装であり、
//! ビルドと接続の成立確認だけを目的とする。

use std::future::Future;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;
use sora_sdk::{Role, SoraConnection, SoraConnectionContext};

mod audio_sink;
mod connection;
mod fake_audio_device;
mod frames;
mod logging_check;
mod loopback;
mod track;
mod video_sink;

use loopback::{validate_base_args, DiscardingEventHandler};

/// Sora に接続し、指定秒数後に切断する。
///
/// recvonly を既定ロールとし、送信トラックは付けない。
/// 接続・切断の成否は戻り値と例外で判定できる。
#[pyfunction]
#[pyo3(signature = (signaling_urls, channel_id, role = "recvonly", metadata = None, duration_secs = 5.0))]
fn connect(
    py: Python<'_>,
    signaling_urls: Vec<String>,
    channel_id: String,
    role: &str,
    metadata: Option<String>,
    duration_secs: f64,
) -> PyResult<()> {
    // 引数の検証は GIL 保持のまま行い、 blocking な接続処理だけ GIL を外す。
    let args = validate_base_args(signaling_urls, channel_id, metadata, duration_secs)?;
    let role = Role::parse(role).map_err(|_| {
        PyValueError::new_err(format!(
            "invalid role \"{role}\", expected sendonly, recvonly or sendrecv"
        ))
    })?;
    py.detach(|| {
        block_on(run_once(
            args.signaling_urls,
            args.channel_id,
            role,
            args.metadata,
            args.duration_secs,
        ))
    })
}

/// 1 回分の接続と切断を実行する。
async fn run_once(
    signaling_urls: Vec<String>,
    channel_id: String,
    role: Role,
    metadata: Option<sora_sdk::JsonString>,
    duration_secs: f64,
) -> PyResult<()> {
    let context = SoraConnectionContext::new().map_err(|e| {
        PyRuntimeError::new_err(format!("failed to create connection context: {e}"))
    })?;
    let mut builder = SoraConnection::builder(
        context,
        signaling_urls,
        channel_id,
        role,
        DiscardingEventHandler,
    );
    if let Some(metadata) = metadata {
        builder = builder.metadata(metadata);
    }
    let (connection, handle) = builder
        .build()
        .map_err(|e| PyRuntimeError::new_err(format!("failed to build connection: {e}")))?;
    // 指定秒数後に別タスクから切断し、run() を終了させる。
    let disconnector = handle.clone();
    tokio::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_secs_f64(duration_secs)).await;
        let _ = disconnector.disconnect().await;
    });
    connection
        .run()
        .await
        .map_err(|e| PyRuntimeError::new_err(format!("connection failed: {e}")))
}

/// 音声ループバックを実行し、受信計数を辞書で返す。
#[pyfunction]
#[pyo3(signature = (signaling_urls, channel_id, metadata = None, duration_secs = 10.0, microphone = false))]
fn loopback_audio_frames(
    py: Python<'_>,
    signaling_urls: Vec<String>,
    channel_id: String,
    metadata: Option<String>,
    duration_secs: f64,
    microphone: bool,
) -> PyResult<Py<PyAny>> {
    let args = validate_base_args(signaling_urls, channel_id, metadata, duration_secs)?;
    let flow = py.detach(|| block_on(loopback::loopback_audio(args, microphone)))?;
    Python::attach(|py| {
        let result = PyDict::new(py);
        result.set_item("frames", flow.frames)?;
        result.set_item("bytes", flow.bytes)?;
        result.set_item("sample_rate", flow.sample_rate)?;
        result.set_item("channels", flow.channels)?;
        result.set_item("unknown_tracks", flow.unknown_tracks)?;
        Ok(result.into())
    })
}

/// 映像ループバックを実行し、受信計数と変換結果を辞書で返す。
#[pyfunction]
#[pyo3(signature = (signaling_urls, channel_id, metadata = None, duration_secs = 15.0))]
fn loopback_video_frames(
    py: Python<'_>,
    signaling_urls: Vec<String>,
    channel_id: String,
    metadata: Option<String>,
    duration_secs: f64,
) -> PyResult<Py<PyAny>> {
    let args = validate_base_args(signaling_urls, channel_id, metadata, duration_secs)?;
    let flow = py.detach(|| block_on(loopback::loopback_video(args)))?;
    Python::attach(|py| {
        let result = PyDict::new(py);
        result.set_item("received_frames", flow.received_frames)?;
        result.set_item("transformed_frames", flow.transformed_frames)?;
        result.set_item("unknown_tracks", flow.unknown_tracks)?;
        result.set_item("width", flow.width)?;
        result.set_item("height", flow.height)?;
        result.set_item("argb_frame", flow.argb_frame)?;
        Ok(result.into())
    })
}

/// current-thread ランタイムで非同期処理をブロッキング実行する。
fn block_on<F, T>(future: F) -> PyResult<T>
where
    F: Future<Output = PyResult<T>> + Send,
    T: Send,
{
    // sora_sdk の利用例と同じ current-thread ランタイムで駆動する。
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|e| PyRuntimeError::new_err(format!("failed to build async runtime: {e}")))?;
    runtime.block_on(future)
}

/// libwebrtc ログ制御の到達確認を実行し、結果を辞書で返す。
#[pyfunction]
fn logging_self_check(py: Python<'_>) -> PyResult<Py<PyAny>> {
    let (initialized, captured) = py.detach(logging_check::logging_self_check)?;
    Python::attach(|py| {
        let result = PyDict::new(py);
        result.set_item("initialized", initialized)?;
        result.set_item("captured", captured)?;
        Ok(result.into())
    })
}

/// モジュール共有の非同期ランタイム。
///
/// 接続の run タスクを駆動する。コールバックは GIL 取得で Python を呼ぶため、
/// ランタイムスレッド自体は Python に触れない。
pub(crate) fn runtime() -> &'static tokio::runtime::Runtime {
    static RUNTIME: std::sync::OnceLock<tokio::runtime::Runtime> = std::sync::OnceLock::new();
    RUNTIME.get_or_init(|| {
        tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .expect("failed to build async runtime")
    })
}

/// プロトタイプモジュール本体。
#[pymodule(gil_used = false)]
fn sora_rust_sdk(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // モジュールの版。依存する sora_sdk クレートの版は Cargo.lock に記録する。
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(connect, m)?)?;
    m.add_function(wrap_pyfunction!(loopback_audio_frames, m)?)?;
    m.add_function(wrap_pyfunction!(loopback_video_frames, m)?)?;
    m.add_function(wrap_pyfunction!(logging_self_check, m)?)?;
    m.add_class::<connection::Sora>()?;
    m.add_class::<connection::SoraConnection>()?;
    m.add_class::<track::SoraMediaTrack>()?;
    m.add_class::<audio_sink::SoraAudioSink>()?;
    m.add_class::<audio_sink::SoraAudioStreamSink>()?;
    m.add_class::<video_sink::SoraVideoSink>()?;
    m.add_class::<frames::SoraAudioFrame>()?;
    m.add_class::<frames::SoraVideoFrame>()?;
    Ok(())
}
