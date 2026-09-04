//! sora-rust-sdk を PyO3 経由で Python から利用するためのプロトタイプモジュール。
//!
//! 現行の Sora C++ SDK + nanobind 構成とは独立した最小実装であり、
//! ビルドと接続の成立確認だけを目的とする。

use std::time::Duration;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use sora_sdk::{Role, SoraConnection, SoraConnectionContext, SoraConnectionEventHandler};

// 入力値の上限。Python 側からの不正な入力で過剰な確保や長時間実行が起きないようにする。
// シグナリング URL の最大件数。
const MAX_SIGNALING_URLS: usize = 16;
// シグナリング URL 1 件の最大文字数。
const MAX_SIGNALING_URL_LEN: usize = 2048;
// チャネル ID の最大文字数。
const MAX_CHANNEL_ID_LEN: usize = 1024;
// メタデータ JSON 文字列の最大文字数。
const MAX_METADATA_LEN: usize = 16384;
// 接続維持時間の最大秒数。
const MAX_DURATION_SECS: f64 = 3600.0;

/// イベントを破棄する空のハンドラ。
///
/// プロトタイプではコールバックを Python に中継しないため、
/// トレイトのデフォルト空実装をそのまま使う。
struct DiscardingEventHandler;

impl SoraConnectionEventHandler for DiscardingEventHandler {}

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
    if signaling_urls.is_empty() {
        return Err(PyValueError::new_err(
            "signaling_urls must contain at least 1 URL, got 0",
        ));
    }
    if signaling_urls.len() > MAX_SIGNALING_URLS {
        return Err(PyValueError::new_err(format!(
            "signaling_urls must contain at most {MAX_SIGNALING_URLS} URLs, got {}",
            signaling_urls.len()
        )));
    }
    for url in &signaling_urls {
        if url.len() > MAX_SIGNALING_URL_LEN {
            return Err(PyValueError::new_err(format!(
                "signaling URL must be at most {MAX_SIGNALING_URL_LEN} characters, got {}",
                url.len()
            )));
        }
    }
    if channel_id.is_empty() {
        return Err(PyValueError::new_err("channel_id must not be empty"));
    }
    if channel_id.len() > MAX_CHANNEL_ID_LEN {
        return Err(PyValueError::new_err(format!(
            "channel_id must be at most {MAX_CHANNEL_ID_LEN} characters, got {}",
            channel_id.len()
        )));
    }
    let role = Role::parse(role).map_err(|_| {
        PyValueError::new_err(format!(
            "invalid role \"{role}\", expected sendonly, recvonly or sendrecv"
        ))
    })?;
    if let Some(metadata) = &metadata {
        if metadata.len() > MAX_METADATA_LEN {
            return Err(PyValueError::new_err(format!(
                "metadata must be at most {MAX_METADATA_LEN} characters, got {}",
                metadata.len()
            )));
        }
    }
    if !duration_secs.is_finite() || duration_secs <= 0.0 || duration_secs > MAX_DURATION_SECS {
        return Err(PyValueError::new_err(format!(
            "duration_secs must be within (0, {MAX_DURATION_SECS}], got {duration_secs}"
        )));
    }

    py.detach(|| run_blocking(signaling_urls, channel_id, role, metadata, duration_secs))
}

/// 接続から切断までをブロッキング実行する。
fn run_blocking(
    signaling_urls: Vec<String>,
    channel_id: String,
    role: Role,
    metadata: Option<String>,
    duration_secs: f64,
) -> PyResult<()> {
    // sora_sdk の利用例と同じ current-thread ランタイムで駆動する。
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|e| PyRuntimeError::new_err(format!("failed to build async runtime: {e}")))?;
    runtime.block_on(run_once(
        signaling_urls,
        channel_id,
        role,
        metadata,
        duration_secs,
    ))
}

/// 1 回分の接続と切断を実行する。
async fn run_once(
    signaling_urls: Vec<String>,
    channel_id: String,
    role: Role,
    metadata: Option<String>,
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
        let metadata = metadata
            .parse()
            .map_err(|e| PyValueError::new_err(format!("invalid metadata JSON: {e}")))?;
        builder = builder.metadata(metadata);
    }
    let (connection, handle) = builder
        .build()
        .map_err(|e| PyRuntimeError::new_err(format!("failed to build connection: {e}")))?;
    // 指定秒数後に別タスクから切断し、run() を終了させる。
    let disconnector = handle.clone();
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_secs_f64(duration_secs)).await;
        let _ = disconnector.disconnect().await;
    });
    connection
        .run()
        .await
        .map_err(|e| PyRuntimeError::new_err(format!("connection failed: {e}")))
}

/// プロトタイプモジュール本体。
#[pymodule(gil_used = false)]
fn sora_rust_sdk(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // モジュールの版。依存する sora_sdk クレートの版は Cargo.lock に記録する。
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(connect, m)?)?;
    Ok(())
}
