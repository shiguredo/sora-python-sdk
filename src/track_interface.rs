//! トラック基底の Python 公開型。
//!
//! 既存 `sora_sdk` の `SoraTrackInterface` に対応する。
//! 型注釈の受け口として用意し、継承関係の再現は対象外とする。

use pyo3::prelude::*;

/// トラック基底。型注釈の受け口。
#[pyclass(module = "sora_sdk")]
pub(crate) struct SoraTrackInterface;

#[pymethods]
impl SoraTrackInterface {
    /// 基底を作る。直接の利用は想定しない。
    #[new]
    fn new() -> Self {
        Self
    }
}
