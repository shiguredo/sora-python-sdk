//! 音声区間検出の Python 公開型。
//!
//! 既存 `sora_sdk` の `SoraVAD` に対応する。
//! 公開バインディングに神経網 VAD の受け口がないため、
//! 実力比に基づく簡易判定で確率を返す。利用上の差分として明記する。

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::frames::SoraAudioFrame;

// 無音とみなす実力比の境目。16bit PCM の最大振幅に対する比。
const SILENCE_RATIO: f32 = 0.02;
// 確実に発話とみなす実力比の境目。
const SPEECH_RATIO: f32 = 0.20;

/// 音声区間検出器。
#[pyclass(module = "sora_sdk")]
pub(crate) struct SoraVAD;

#[pymethods]
impl SoraVAD {
    /// 検出器を作る。
    #[new]
    fn new() -> Self {
        Self
    }

    /// 音声である確率を返す。実力比の直線補間で求める。
    fn analyze(&self, frame: Py<SoraAudioFrame>) -> PyResult<f32> {
        Python::attach(|py| {
            let frame = frame.borrow(py);
            let samples = frame.samples_ref();
            if samples.is_empty() {
                return Err(PyValueError::new_err(
                    "empty audio frame cannot be analyzed",
                ));
            }
            // 実効値を最大振幅で割って 0 から 1 にそろえる。
            let mean_square = samples
                .iter()
                .map(|sample| f32::from(*sample).powi(2))
                .sum::<f32>()
                / samples.len() as f32;
            let ratio = mean_square.sqrt() / f32::from(i16::MAX);
            // 境目の間は直線でつなぐ。
            let probability = (ratio - SILENCE_RATIO) / (SPEECH_RATIO - SILENCE_RATIO);
            Ok(probability.clamp(0.0, 1.0))
        })
    }
}
