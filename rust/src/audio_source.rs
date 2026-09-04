//! 音声送信元の Python 公開型。
//!
//! 既存 `sora_sdk` の `SoraAudioSource` に対応する。
//! 投入された PCM は偽デバイスの送信キューに積み、
//! 10ms 周期の取り込み要求で送信する。

use std::sync::{Arc, Mutex};

use numpy::{PyArray2, PyArrayMethods};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use shiguredo_webrtc::{AudioTrack, AudioTrackSource};
use sora_sdk::SoraConnectionContext;

use crate::fake_audio_device::AudioPumpState;

// 1 回の投入で受け付ける上限 (秒数)。過剰な確保を防ぐ。
const MAX_PUSH_SECS: usize = 10;

/// 音声送信元。
#[pyclass(module = "sora_rust_sdk")]
pub(crate) struct SoraAudioSource {
    /// 送信トラックの生成元。接続ごとのトラック生成に使う。
    /// AudioTrackSource 自体は Sync ではないため Mutex で包む。
    source: Mutex<AudioTrackSource>,
    /// 属性参照用のトラック。
    track: Mutex<AudioTrack>,
    /// factory 所有のコンテキスト。トラック生成まで factory を生かす。
    context: Arc<SoraConnectionContext>,
    /// 送信ポンプの共有状態。
    pump: Arc<AudioPumpState>,
    /// チャンネル数。
    channels: usize,
    /// サンプルレート (Hz)。
    sample_rate: u32,
}

impl SoraAudioSource {
    /// 検証済みの形式で作る。
    pub(crate) fn new(
        context: Arc<SoraConnectionContext>,
        pump: Arc<AudioPumpState>,
        channels: usize,
        sample_rate: u32,
    ) -> Result<Self, String> {
        let source = context
            .create_audio_source()
            .map_err(|e| format!("failed to create audio source: {e}"))?;
        let track = context
            .create_audio_track(&source)
            .map_err(|e| format!("failed to create audio track: {e}"))?;
        pump.set_capture(channels, sample_rate);
        Ok(Self {
            source: Mutex::new(source),
            track: Mutex::new(track),
            context,
            pump,
            channels,
            sample_rate,
        })
    }

    /// 接続に載せる送信トラックを作る。
    pub(crate) fn new_sender_track(&self) -> Result<AudioTrack, String> {
        let source = self.source.lock().expect("audio source lock poisoned");
        self.context
            .create_audio_track(&source)
            .map_err(|e| format!("failed to create sender audio track: {e}"))
    }
}

#[pymethods]
impl SoraAudioSource {
    /// トラック種別。音声送信元は常に `audio`。
    #[getter]
    fn kind(&self) -> &'static str {
        "audio"
    }

    /// トラック ID。
    #[getter]
    fn id(&self) -> PyResult<String> {
        self.track
            .lock()
            .expect("audio source lock poisoned")
            .cast_to_media_stream_track()
            .id()
            .map_err(|e| PyRuntimeError::new_err(format!("failed to get track id: {e}")))
    }

    /// トラックが有効かどうか。
    #[getter]
    fn enabled(&self) -> bool {
        self.track
            .lock()
            .expect("audio source lock poisoned")
            .cast_to_media_stream_track()
            .enabled()
    }

    /// トラックの有効 / 無効を設定する。
    fn set_enabled(&self, enable: bool) -> bool {
        self.track
            .lock()
            .expect("audio source lock poisoned")
            .cast_to_media_stream_track()
            .set_enabled(enable)
    }

    /// PCM を投入する。形状は (samples_per_channel, channels) の int16 配列。
    #[pyo3(signature = (array, timestamp = None))]
    fn on_data(&self, array: Bound<'_, PyArray2<i16>>, timestamp: Option<f64>) -> PyResult<()> {
        // 時刻は連続投入の前提で無視する。キューが途切れた箇所は無音で埋まる。
        let _ = timestamp;
        let readonly = array.readonly();
        let shape = readonly.as_array().shape().to_vec();
        if shape.len() != 2 {
            return Err(PyValueError::new_err(format!(
                "array must be 2-dimensional (samples_per_channel, channels), got {} dimensions",
                shape.len()
            )));
        }
        if shape[1] != self.channels {
            return Err(PyValueError::new_err(format!(
                "array channels must be {}, got {}",
                self.channels, shape[1]
            )));
        }
        if shape[0] < 1 {
            return Err(PyValueError::new_err(format!(
                "array must contain at least 1 sample per channel, got {}",
                shape[0]
            )));
        }
        if shape[0] > self.sample_rate as usize * MAX_PUSH_SECS {
            return Err(PyValueError::new_err(format!(
                "array holds too many samples per channel, got {}",
                shape[0]
            )));
        }
        let samples = readonly
            .as_slice()
            .map_err(|e| PyValueError::new_err(format!("array must be C-contiguous: {e}")))?;
        self.pump
            .push_send(samples, self.channels, self.sample_rate);
        Ok(())
    }
}
