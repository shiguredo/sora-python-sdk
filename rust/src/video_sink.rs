//! 映像 Sink と映像フレームの Python 公開型。
//!
//! 既存 `sora_sdk` の `SoraVideoSink` / `SoraVideoFrame` に対応する。

use std::sync::{Arc, Mutex};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use shiguredo_webrtc::{
    convert_from_i420, LibyuvFourcc, VideoSink, VideoSinkHandler, VideoSinkWants, VideoTrack,
};
use sora_sdk::SoraConnectionContext;

use crate::audio_sink::set_callback;
use crate::frames::SoraVideoFrame;
use crate::track::SoraMediaTrack;

/// 映像 Sink 共有状態。
struct SinkState {
    /// on_frame コールバック。
    on_frame: Mutex<Option<Py<PyAny>>>,
}

/// フレームを中継するハンドラ。
struct RelayingVideoHandler {
    /// 共有状態。
    state: Arc<SinkState>,
}

impl VideoSinkHandler for RelayingVideoHandler {
    fn on_frame(&mut self, frame: shiguredo_webrtc::VideoFrameRef<'_>) {
        // デコーダースレッド上で呼ばれる。ARGB 変換して Python に渡す。
        let width = frame.width();
        let height = frame.height();
        if width <= 0 || height <= 0 {
            return;
        }
        let mut buffer = frame.buffer();
        let Some(i420) = buffer.to_i420() else {
            return;
        };
        let mut argb = vec![0u8; width as usize * height as usize * 4];
        let converted = convert_from_i420(
            i420.y_data(),
            i420.stride_y(),
            i420.u_data(),
            i420.stride_u(),
            i420.v_data(),
            i420.stride_v(),
            &mut argb,
            width * 4,
            width,
            height,
            LibyuvFourcc::Argb,
        );
        if !converted {
            return;
        }
        // ARGB から RGB を抜き出す。
        let rgb: Vec<u8> = argb
            .as_chunks::<4>()
            .0
            .iter()
            .flat_map(|pixel| [pixel[0], pixel[1], pixel[2]])
            .collect();
        Python::attach(|py| {
            let Some(callback) = self
                .state
                .on_frame
                .lock()
                .expect("callback lock poisoned")
                .as_ref()
                .map(|callback| callback.clone_ref(py))
            else {
                return;
            };
            let video_frame = SoraVideoFrame::new(rgb, width as usize, height as usize);
            match Py::new(py, video_frame) {
                Ok(video_frame) => {
                    if let Err(error) = callback.call1(py, (video_frame,)) {
                        error.print(py);
                    }
                }
                Err(error) => error.print(py),
            }
        });
    }
}

/// 映像 Sink。
#[pyclass(module = "sora_rust_sdk")]
pub(crate) struct SoraVideoSink {
    /// 登録済み Sink (登録解除まで保持する)。
    sink: Mutex<Option<VideoSink>>,
    /// 所有維持するトラック。
    _track: VideoTrack,
    /// factory 所有のコンテキスト。破棄順序のため保持する。
    _context: Arc<SoraConnectionContext>,
    /// 共有状態。
    state: Arc<SinkState>,
}

#[pymethods]
impl SoraVideoSink {
    /// Sink を作りトラックに付ける。
    #[new]
    fn new(track: &SoraMediaTrack) -> PyResult<Self> {
        let kind = track.kind()?;
        if kind != "video" {
            return Err(PyValueError::new_err(format!(
                "SoraVideoSink requires a video track, got {kind}"
            )));
        }
        let state = Arc::new(SinkState {
            on_frame: Mutex::new(None),
        });
        let sink = VideoSink::new_with_handler(Box::new(RelayingVideoHandler {
            state: state.clone(),
        }));
        let context = track.connection_context();
        let video = track.with_webrtc_track(|track| track.cast_to_video_track());
        video.add_or_update_sink(&sink, &VideoSinkWants::new());
        Ok(Self {
            sink: Mutex::new(Some(sink)),
            _track: video,
            _context: context,
            state,
        })
    }

    /// on_frame コールバック。
    #[getter]
    fn on_frame(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.state
            .on_frame
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_frame コールバックを設定する。
    #[setter]
    fn set_on_frame(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.state.on_frame, value, "on_frame")
    }
}

impl Drop for SoraVideoSink {
    fn drop(&mut self) {
        // トラックから登録解除する。
        if let Some(sink) = self.sink.lock().expect("sink lock poisoned").take() {
            self._track.remove_sink(&sink);
        }
    }
}
