//! libwebrtc 記録制御の Python 公開関数。
//!
//! 既存 `sora_sdk` の `enable_libwebrtc_log` / `rtc_log` に対応する。

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use shiguredo_webrtc::log::{initialize_logging, LoggingConfig, Severity};

use crate::enums::SoraLoggingSeverity;

/// libwebrtc の記録深刻度を設定する。初回だけ有効。
#[pyfunction]
pub(crate) fn enable_libwebrtc_log(severity: Bound<'_, PyAny>) -> PyResult<()> {
    let level = parse_severity(&severity)?;
    let mut config = LoggingConfig::new();
    config.set_min_severity(level);
    initialize_logging(config);
    Ok(())
}

/// libwebrtc の記録に任意文言を出す。
#[pyfunction]
pub(crate) fn rtc_log(severity: Bound<'_, PyAny>, message: String) -> PyResult<()> {
    let level = parse_severity(&severity)?;
    shiguredo_webrtc::log::print(level, "sora_sdk", 0, &message);
    Ok(())
}

/// 深刻度を受け取る。整数か列挙のどちらでもよい。
fn parse_severity(value: &Bound<'_, PyAny>) -> PyResult<Severity> {
    // 整数と整数列挙 (int() 変換できるもの) を受ける。
    let raw = value
        .extract::<i64>()
        .or_else(|_| {
            value
                .getattr("value")
                .and_then(|member| member.extract::<i64>())
        })
        .map_err(|_| {
            PyValueError::new_err("severity must be a SoraLoggingSeverity or an int 0-4")
        })?;
    SoraLoggingSeverity::from_int(raw)
        .map(|level| level.to_webrtc())
        .ok_or_else(|| {
            PyValueError::new_err(format!("invalid logging severity {raw}, expected 0-4"))
        })
}
