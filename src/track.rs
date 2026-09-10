//! 受信トラックの Python 公開型。
//!
//! 既存 `sora_sdk` の `SoraTrackInterface` / `SoraMediaTrack` に対応する。

use std::sync::{Arc, Mutex};

use ::sora_sdk::SoraConnectionContext;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use shiguredo_webrtc::{FrameTransformer, MediaStreamTrack, RtpReceiver};

use crate::transformer::{SoraVideoFrameTransformer, VideoTransformRelay};

/// 受信トラック。
#[pyclass(module = "sora_sdk")]
pub(crate) struct SoraMediaTrack {
    /// 保持する WebRTC トラック。参照カウントでスレッドセーフのため Mutex で包む。
    track: std::sync::Mutex<MediaStreamTrack>,
    /// 受信器。encoded 変換の設定に使う。受信通知由来でのみ入る。
    receiver: Mutex<Option<RtpReceiver>>,
    /// 設定済み変換器。破棄順序のため保持する。
    transformer: Mutex<Option<FrameTransformer>>,
    /// factory 所有のコンテキスト。Sink 破棄まで factory を生かす。
    context: Arc<SoraConnectionContext>,
}

impl SoraMediaTrack {
    /// WebRTC トラックから作る。
    pub(crate) fn new(
        track: MediaStreamTrack,
        receiver: Option<RtpReceiver>,
        context: Arc<SoraConnectionContext>,
    ) -> Self {
        Self {
            track: std::sync::Mutex::new(track),
            receiver: Mutex::new(receiver),
            transformer: Mutex::new(None),
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

    /// 受信側の encoded 変換を設定する。映像のみ対応する。
    fn set_frame_transformer(&self, py: Python<'_>, transformer: Bound<'_, PyAny>) -> PyResult<()> {
        // 音声変換器の受け付けは組み立て器に経路がないため誤りにする。
        let video: Py<SoraVideoFrameTransformer> = transformer
            .extract()
            .map_err(|_| PyValueError::new_err("only SoraVideoFrameTransformer is supported"))?;
        let shared = video.borrow(py).shared();
        let transformer =
            FrameTransformer::new_with_handler(Box::new(VideoTransformRelay::new(shared)));
        let mut receiver = self.receiver.lock().expect("track lock poisoned");
        let Some(receiver) = receiver.as_mut() else {
            return Err(PyRuntimeError::new_err(
                "track has no receiver for frame transformer",
            ));
        };
        receiver.set_frame_transformer(&transformer);
        *self.transformer.lock().expect("track lock poisoned") = Some(transformer);
        Ok(())
    }
}
