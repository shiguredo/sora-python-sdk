//! 受信フレームの Python 公開型。
//!
//! 既存 `sora_sdk` の `SoraAudioFrame` / `SoraVideoFrame` に対応する。

use numpy::{PyArrayMethods, ToPyArray};
use pyo3::prelude::*;

/// 音声フレーム。
#[pyclass(module = "sora_rust_sdk")]
pub(crate) struct SoraAudioFrame {
    /// インタリーブ PCM (int16)。
    samples: Vec<i16>,
    /// チャンネルあたりのサンプル数。
    samples_per_channel: usize,
    /// チャンネル数。
    num_channels: usize,
    /// サンプルレート (Hz)。
    sample_rate_hz: i32,
    /// 取り込み時刻 (ミリ秒)。Sink 経路では取得できないため常に空。
    absolute_capture_timestamp_ms: Option<i64>,
}

impl SoraAudioFrame {
    /// PCM から作る。
    pub(crate) fn from_pcm(
        samples: Vec<i16>,
        samples_per_channel: usize,
        num_channels: usize,
        sample_rate_hz: i32,
    ) -> Self {
        Self {
            samples,
            samples_per_channel,
            num_channels,
            sample_rate_hz,
            absolute_capture_timestamp_ms: None,
        }
    }
}

#[pymethods]
impl SoraAudioFrame {
    /// 空フレームを作る。pickle 復元用。
    #[new]
    fn new() -> Self {
        Self {
            samples: Vec::new(),
            samples_per_channel: 0,
            num_channels: 0,
            sample_rate_hz: 0,
            absolute_capture_timestamp_ms: None,
        }
    }

    /// チャネルあたりのサンプル数。
    #[getter]
    fn samples_per_channel(&self) -> usize {
        self.samples_per_channel
    }

    /// チャンネル数。
    #[getter]
    fn num_channels(&self) -> usize {
        self.num_channels
    }

    /// サンプルレート (Hz)。
    #[getter]
    fn sample_rate_hz(&self) -> i32 {
        self.sample_rate_hz
    }

    /// 取り込み時刻 (ミリ秒)。Sink 経路では取得できないため常に空。
    #[getter]
    fn absolute_capture_timestamp_ms(&self) -> Option<i64> {
        self.absolute_capture_timestamp_ms
    }

    /// PCM を int16 の二次元配列で返す。
    fn data<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, numpy::PyArray2<i16>>> {
        if self.num_channels == 0 {
            let array = Vec::<i16>::new().to_pyarray(py);
            return array.reshape([0, 0]);
        }
        let array = self.samples.to_pyarray(py);
        array.reshape([self.samples_per_channel, self.num_channels])
    }

    /// pickle 化用に全データをタプルで返す。
    fn __getstate__(&self) -> (Vec<i16>, usize, usize, i32, Option<i64>) {
        (
            self.samples.clone(),
            self.samples_per_channel,
            self.num_channels,
            self.sample_rate_hz,
            self.absolute_capture_timestamp_ms,
        )
    }

    /// pickle から復元する。
    fn __setstate__(&mut self, state: (Vec<i16>, usize, usize, i32, Option<i64>)) -> PyResult<()> {
        let (samples, samples_per_channel, num_channels, sample_rate_hz, timestamp) = state;
        if num_channels == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "num_channels must not be 0",
            ));
        }
        if samples.len() != samples_per_channel * num_channels {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "samples length {} does not match samples_per_channel {} * num_channels {}",
                samples.len(),
                samples_per_channel,
                num_channels
            )));
        }
        self.samples = samples;
        self.samples_per_channel = samples_per_channel;
        self.num_channels = num_channels;
        self.sample_rate_hz = sample_rate_hz;
        self.absolute_capture_timestamp_ms = timestamp;
        Ok(())
    }
}

/// 映像フレーム。
#[pyclass(module = "sora_rust_sdk")]
pub(crate) struct SoraVideoFrame {
    /// RGB バイト列。
    rgb: Vec<u8>,
    /// 幅。
    width: usize,
    /// 高さ。
    height: usize,
}

impl SoraVideoFrame {
    /// RGB から作る。
    pub(crate) fn new(rgb: Vec<u8>, width: usize, height: usize) -> Self {
        Self { rgb, width, height }
    }
}

#[pymethods]
impl SoraVideoFrame {
    /// RGB を uint8 の三次元配列で返す。
    fn data<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, numpy::PyArray3<u8>>> {
        let array = self.rgb.to_pyarray(py);
        array.reshape([self.height, self.width, 3])
    }
}
