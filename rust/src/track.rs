//! 受信トラックの Python 公開型。
//!
//! 既存 `sora_sdk` の `SoraTrackInterface` / `SoraMediaTrack` に対応する。

use std::sync::Arc;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use shiguredo_webrtc::MediaStreamTrack;
use sora_sdk::SoraConnectionContext;

/// 受信トラック。
#[pyclass(module = "sora_rust_sdk")]
pub(crate) struct SoraMediaTrack {
    /// 保持する WebRTC トラック。参照カウントでスレッドセーフのため Mutex で包む。
    track: std::sync::Mutex<MediaStreamTrack>,
    /// factory 所有のコンテキスト。Sink 破棄まで factory を生かす。
    context: Arc<SoraConnectionContext>,
}

impl SoraMediaTrack {
    /// WebRTC トラックから作る。
    pub(crate) fn new(track: MediaStreamTrack, context: Arc<SoraConnectionContext>) -> Self {
        Self {
            track: std::sync::Mutex::new(track),
            context,
        }
    }

    /// factory 所有のコンテキストを複製する。
    pub(crate) fn connection_context(&self) -> Arc<SoraConnectionContext> {
        self.context.clone()
    }

    /// 内部の WebRTC トラックで処理する。
    pub(crate) fn with_webrtc_track<T>(&self, f: impl FnOnce(&MediaStreamTrack) -> T) -> T {
        f(&self.track.lock().expect("track lock poisoned"))
    }
}

#[pymethods]
impl SoraMediaTrack {
    /// トラック種別 (`audio` / `video`)。
    #[getter]
    pub(crate) fn kind(&self) -> PyResult<String> {
        self.with_webrtc_track(|track| track.kind())
            .map_err(|e| PyRuntimeError::new_err(format!("failed to get track kind: {e}")))
    }

    /// トラック ID。
    #[getter]
    fn id(&self) -> PyResult<String> {
        self.with_webrtc_track(|track| track.id())
            .map_err(|e| PyRuntimeError::new_err(format!("failed to get track id: {e}")))
    }

    /// トラックが有効かどうか。
    #[getter]
    fn enabled(&self) -> bool {
        self.with_webrtc_track(|track| track.enabled())
    }

    /// トラックの有効 / 無効を設定する。
    fn set_enabled(&self, enable: bool) -> bool {
        self.with_webrtc_track(|track| track.set_enabled(enable))
    }
}
