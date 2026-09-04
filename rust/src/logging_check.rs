//! libwebrtc ログ制御の到達確認。
//!
//! `shiguredo_webrtc::log` モジュール (`LoggingConfig` / `Severity` /
//! `LogSink` / `initialize_logging` / `print`) が外部クレートから使えることを
//! 実際に初期化と取得で確認する。

use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc,
};

use pyo3::prelude::*;
use shiguredo_webrtc::log::{
    initialize_logging, print, LogLineRef, LogSink, LogSinkHandler, LoggingConfig, Severity,
};

/// ログ行を数える sink。
struct CountingLogSink {
    /// 照合用目印。
    marker: String,
    /// 目印を含む行数。
    count: Arc<AtomicU64>,
}

impl LogSinkHandler for CountingLogSink {
    fn on_log_message(&mut self, line: LogLineRef<'_>) {
        // ログ出力スレッド上で呼ばれるため計数だけする。
        if line.message().contains(&self.marker) {
            self.count.fetch_add(1, Ordering::Relaxed);
        }
    }
}

/// ログ設定を初期化し、目印メッセージを出力して取得できた行数を返す。
///
/// 戻り値は (初期化できたか、取得行数) である。初期化は初回だけ有効なため、
/// 二重呼び出しでは偽が返る。取得行数は初回呼び出しでのみ意味を持つ。
pub(crate) fn logging_self_check() -> PyResult<(bool, u64)> {
    let marker = "sora-rust-prototype-logging-self-check".to_string();
    let count = Arc::new(AtomicU64::default());
    let mut config = LoggingConfig::new();
    config.set_min_severity(Severity::Verbose);
    config.set_log_to_stderr(false);
    config.add_sink(LogSink::new_with_handler(Box::new(CountingLogSink {
        marker: marker.clone(),
        count: count.clone(),
    })));
    let initialized = initialize_logging(config);
    print(Severity::Error, "sora_rust_sdk", 0, &marker);
    Ok((initialized, count.load(Ordering::Relaxed)))
}
