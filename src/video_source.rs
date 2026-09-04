//! 映像送信元の Python 公開型。
//!
//! 既存 `sora_sdk` の `SoraVideoSource` に対応する。
//! RGB フレームを受けて I420 変換し、追跡元に投入する。

use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};

use ::sora_sdk::SoraConnectionContext;
use numpy::{PyArray3, PyArrayMethods};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use shiguredo_webrtc::{
    convert_to_i420, AdaptedVideoTrackSource, I420Buffer, LibyuvFourcc, LibyuvRotationMode,
    VideoFrame, VideoTrack,
};

// 1 辺の上限 (画素)。過剰な確保を防ぐ。
const MAX_EDGE: usize = 4096;

/// 映像送信元。
#[pyclass(module = "sora_sdk")]
pub(crate) struct SoraVideoSource {
    /// フレーム投入口。Sync ではないため Mutex で包む。
    source: Mutex<AdaptedVideoTrackSource>,
    /// 保持する WebRTC トラック。複製して接続に載せる。
    track: Mutex<VideoTrack>,
    /// factory 所有のコンテキスト。投入口が factory より先に壊れないように保つ。
    #[expect(dead_code)]
    context: Arc<SoraConnectionContext>,
}

impl SoraVideoSource {
    /// 追跡元とトラックを作る。
    pub(crate) fn new(context: Arc<SoraConnectionContext>) -> Result<Self, String> {
        let source = AdaptedVideoTrackSource::new();
        let track = context
            .create_video_track(&source.cast_to_video_track_source())
            .map_err(|e| format!("failed to create video track: {e}"))?;
        Ok(Self {
            source: Mutex::new(source),
            track: Mutex::new(track),
            context,
        })
    }

    /// 接続に載せる送信トラックを複製する。
    pub(crate) fn sender_track(&self) -> VideoTrack {
        self.track
            .lock()
            .expect("video source lock poisoned")
            .clone()
    }
}

/// 投入時刻をマイクロ秒にそろえる。整数はマイクロ秒、実数は秒として扱う。
fn timestamp_us(timestamp: Option<Bound<'_, PyAny>>) -> PyResult<i64> {
    let Some(timestamp) = timestamp else {
        return Ok(now_us());
    };
    if let Ok(timestamp_us) = timestamp.extract::<i64>() {
        return Ok(timestamp_us);
    }
    timestamp
        .extract::<f64>()
        .map(|timestamp| (timestamp * 1_000_000.0) as i64)
        .map_err(|_| {
            PyValueError::new_err("timestamp must be int (microseconds) or float (seconds)")
        })
}

/// 現在時刻をマイクロ秒で返す。
fn now_us() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_micros() as i64)
        .unwrap_or(0)
}

#[pymethods]
impl SoraVideoSource {
    /// トラック種別。映像送信元は常に `video`。
    #[getter]
    fn kind(&self) -> &'static str {
        "video"
    }

    /// トラック ID。
    #[getter]
    fn id(&self) -> PyResult<String> {
        self.track
            .lock()
            .expect("video source lock poisoned")
            .cast_to_media_stream_track()
            .id()
            .map_err(|e| PyRuntimeError::new_err(format!("failed to get track id: {e}")))
    }

    /// トラックが有効かどうか。
    #[getter]
    fn enabled(&self) -> bool {
        self.track
            .lock()
            .expect("video source lock poisoned")
            .cast_to_media_stream_track()
            .enabled()
    }

    /// トラックの有効 / 無効を設定する。
    fn set_enabled(&self, enable: bool) -> bool {
        self.track
            .lock()
            .expect("video source lock poisoned")
            .cast_to_media_stream_track()
            .set_enabled(enable)
    }

    /// RGB フレームを投入する。形状は (height, width, 3) の uint8 配列。
    #[pyo3(signature = (array, timestamp = None))]
    fn on_captured(
        &self,
        py: Python<'_>,
        array: Bound<'_, PyArray3<u8>>,
        timestamp: Option<Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        let timestamp_us = timestamp_us(timestamp)?;
        let readonly = array.readonly();
        let shape = readonly.as_array().shape().to_vec();
        if shape.len() != 3 || shape[2] != 3 {
            return Err(PyValueError::new_err(format!(
                "array must have shape (height, width, 3), got {shape:?}"
            )));
        }
        let (height, width) = (shape[0], shape[1]);
        if height < 1 || width < 1 {
            return Err(PyValueError::new_err(format!(
                "array must have positive height and width, got ({height}, {width})"
            )));
        }
        if height > MAX_EDGE || width > MAX_EDGE {
            return Err(PyValueError::new_err(format!(
                "array edge must be at most {MAX_EDGE}, got ({height}, {width})"
            )));
        }
        let rgb = readonly
            .as_slice()
            .map_err(|e| PyValueError::new_err(format!("array must be C-contiguous: {e}")))?
            .to_vec();
        py.detach(move || {
            push_frame_with_timestamp(&self.source, &rgb, width, height, timestamp_us)
        })
    }
}

/// 時刻指定で RGB を I420 変換して追跡元に投入する。
fn push_frame_with_timestamp(
    source: &Mutex<AdaptedVideoTrackSource>,
    rgb: &[u8],
    width: usize,
    height: usize,
    timestamp_us: i64,
) -> PyResult<()> {
    let width_i32 = width as i32;
    let height_i32 = height as i32;
    // libyuv の ARGB 形式 (小端順で B, G, R, A) に並べ替える。
    let mut argb = vec![0u8; width * height * 4];
    let (rgb_chunks, _) = rgb.as_chunks::<3>();
    let (argb_chunks, _) = argb.as_chunks_mut::<4>();
    for (pixel, out) in rgb_chunks.iter().zip(argb_chunks.iter_mut()) {
        out[0] = pixel[2];
        out[1] = pixel[1];
        out[2] = pixel[0];
        out[3] = 255;
    }
    let mut buffer = I420Buffer::new(width_i32, height_i32);
    let (stride_y, stride_u, stride_v) = (buffer.stride_y(), buffer.stride_u(), buffer.stride_v());
    let (dst_y, dst_u, dst_v) = buffer.planes_mut();
    let converted = convert_to_i420(
        &argb,
        dst_y,
        stride_y,
        dst_u,
        stride_u,
        dst_v,
        stride_v,
        0,
        0,
        width_i32,
        height_i32,
        width_i32,
        height_i32,
        LibyuvRotationMode::Rotate0,
        LibyuvFourcc::Argb,
    );
    if !converted {
        return Err(PyRuntimeError::new_err(
            "failed to convert RGB frame to I420",
        ));
    }
    let mut builder = VideoFrame::builder(&buffer.cast_to_video_frame_buffer());
    builder.set_timestamp_us(timestamp_us);
    let frame = builder.build();
    source
        .lock()
        .expect("video source lock poisoned")
        .on_frame(&frame);
    Ok(())
}
