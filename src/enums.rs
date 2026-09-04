//! 既存 `sora_sdk` の列挙公開型。
//!
//! 通知種別や符号化器指定など、接続設定とコールバックで使う整数列挙を持つ。

use pyo3::prelude::*;

/// 記録の経路。既存 `SoraSignalingType` に対応する。
#[pyclass(module = "sora_sdk", eq, eq_int, skip_from_py_object)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SoraSignalingType {
    /// WebSocket 経路。
    #[pyo3(name = "WEBSOCKET")]
    Websocket = 0,
    /// DataChannel 経路。
    #[pyo3(name = "DATACHANNEL")]
    Datachannel = 1,
}

#[pymethods]
impl SoraSignalingType {
    /// 整数値。既存 IntEnum の value に対応する。
    #[getter]
    fn value(&self) -> i32 {
        *self as i32
    }
}

/// 記録の方向。既存 `SoraSignalingDirection` に対応する。
#[pyclass(module = "sora_sdk", eq, eq_int, skip_from_py_object)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SoraSignalingDirection {
    /// 送信。
    #[pyo3(name = "SENT")]
    Sent = 0,
    /// 受信。
    #[pyo3(name = "RECEIVED")]
    Received = 1,
}

#[pymethods]
impl SoraSignalingDirection {
    /// 整数値。既存 IntEnum の value に対応する。
    #[getter]
    fn value(&self) -> i32 {
        *self as i32
    }
}

/// トラックの生死。既存 `SoraTrackState` に対応する。
///
/// 取得口が公開バインディングにないため、現在は参照用のみ。
#[pyclass(module = "sora_sdk", eq, eq_int, skip_from_py_object)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SoraTrackState {
    /// 生存。
    #[pyo3(name = "LIVE")]
    Live = 0,
    /// 終了。
    #[pyo3(name = "ENDED")]
    Ended = 1,
}

#[pymethods]
impl SoraTrackState {
    /// 整数値。既存 IntEnum の value に対応する。
    #[getter]
    fn value(&self) -> i32 {
        *self as i32
    }
}

/// 記録の深刻度。既存 `SoraLoggingSeverity` に対応する。
#[pyclass(module = "sora_sdk", eq, eq_int, skip_from_py_object)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SoraLoggingSeverity {
    /// 詳細。
    #[pyo3(name = "VERBOSE")]
    Verbose = 0,
    /// 情報。
    #[pyo3(name = "INFO")]
    Info = 1,
    /// 警告。
    #[pyo3(name = "WARNING")]
    Warning = 2,
    /// 誤り。
    #[pyo3(name = "ERROR")]
    Error = 3,
    /// 無効。
    #[pyo3(name = "NONE")]
    None_ = 4,
}

#[pymethods]
impl SoraLoggingSeverity {
    /// 整数値。既存 IntEnum の value に対応する。
    #[getter]
    fn value(&self) -> i32 {
        *self as i32
    }
}

impl SoraLoggingSeverity {
    /// libwebrtc の深刻度に変える。
    pub(crate) fn to_webrtc(self) -> shiguredo_webrtc::log::Severity {
        match self {
            Self::Verbose => shiguredo_webrtc::log::Severity::Verbose,
            Self::Info => shiguredo_webrtc::log::Severity::Info,
            Self::Warning => shiguredo_webrtc::log::Severity::Warning,
            Self::Error => shiguredo_webrtc::log::Severity::Error,
            // 無効は最も高い深刻度で黙らせる。
            Self::None_ => shiguredo_webrtc::log::Severity::None,
        }
    }

    /// 整数から作る。
    pub(crate) fn from_int(value: i64) -> Option<Self> {
        match value {
            0 => Some(Self::Verbose),
            1 => Some(Self::Info),
            2 => Some(Self::Warning),
            3 => Some(Self::Error),
            4 => Some(Self::None_),
            _ => None,
        }
    }
}

/// 劣化 preference。既存 `SoraDegradationPreference` に対応する。
///
/// 組み立て器に受け口がないため、現在は参照用のみ。
#[pyclass(module = "sora_sdk", eq, eq_int, skip_from_py_object)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SoraDegradationPreference {
    /// 無効。
    #[pyo3(name = "DISABLED")]
    Disabled = 0,
    /// 均衡。
    #[pyo3(name = "BALANCED")]
    Balanced = 3,
    /// 枠率維持。
    #[pyo3(name = "MAINTAIN_FRAMERATE")]
    MaintainFramerate = 1,
    /// 解像度維持。
    #[pyo3(name = "MAINTAIN_RESOLUTION")]
    MaintainResolution = 2,
}

#[pymethods]
impl SoraDegradationPreference {
    /// 整数値。既存 IntEnum の value に対応する。
    #[getter]
    fn value(&self) -> i32 {
        *self as i32
    }
}

/// 映像符号化方式。既存 `SoraVideoCodecType` に対応する。
#[pyclass(module = "sora_sdk", eq, eq_int, skip_from_py_object)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SoraVideoCodecType {
    /// VP8。
    #[pyo3(name = "VP8")]
    Vp8 = 1,
    /// VP9。
    #[pyo3(name = "VP9")]
    Vp9 = 2,
    /// H264。
    #[pyo3(name = "H264")]
    H264 = 4,
    /// H265。
    #[pyo3(name = "H265")]
    H265 = 5,
    /// AV1。
    #[pyo3(name = "AV1")]
    Av1 = 3,
}

#[pymethods]
impl SoraVideoCodecType {
    /// 整数値。既存 IntEnum の value に対応する。
    #[getter]
    fn value(&self) -> i32 {
        *self as i32
    }
}

impl SoraVideoCodecType {
    /// 整数から作る。
    pub(crate) fn from_int(value: i64) -> Option<Self> {
        match value {
            1 => Some(Self::Vp8),
            2 => Some(Self::Vp9),
            4 => Some(Self::H264),
            5 => Some(Self::H265),
            3 => Some(Self::Av1),
            _ => None,
        }
    }

    /// バインディングの符号化方式に変える。
    pub(crate) fn to_webrtc(self) -> shiguredo_webrtc::VideoCodecType {
        match self {
            Self::Vp8 => shiguredo_webrtc::VideoCodecType::Vp8,
            Self::Vp9 => shiguredo_webrtc::VideoCodecType::Vp9,
            Self::H264 => shiguredo_webrtc::VideoCodecType::H264,
            Self::H265 => shiguredo_webrtc::VideoCodecType::H265,
            Self::Av1 => shiguredo_webrtc::VideoCodecType::Av1,
        }
    }
}

/// 映像符号化器の実装。既存 `SoraVideoCodecImplementation` に対応する。
#[pyclass(module = "sora_sdk", eq, eq_int, skip_from_py_object)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SoraVideoCodecImplementation {
    /// 内蔵。
    #[pyo3(name = "INTERNAL")]
    Internal = 0,
    /// Cisco OpenH264。
    #[pyo3(name = "CISCO_OPENH264")]
    CiscoOpenh264 = 1,
    /// Intel VPL。
    #[pyo3(name = "INTEL_VPL")]
    IntelVpl = 2,
    /// NVIDIA Video Codec SDK。
    #[pyo3(name = "NVIDIA_VIDEO_CODEC_SDK")]
    NvidiaVideoCodecSdk = 3,
    /// AMD AMF。
    #[pyo3(name = "AMD_AMF")]
    AmdAmf = 4,
    /// Raspberry Pi V4L2M2M。
    #[pyo3(name = "RASPI_V4L2M2M")]
    RaspiV4l2m2m = 5,
}

#[pymethods]
impl SoraVideoCodecImplementation {
    /// 整数値。既存 IntEnum の value に対応する。
    #[getter]
    fn value(&self) -> i32 {
        *self as i32
    }
}

impl SoraVideoCodecImplementation {
    /// 整数から作る。
    pub(crate) fn from_int(value: i64) -> Option<Self> {
        match value {
            0 => Some(Self::Internal),
            1 => Some(Self::CiscoOpenh264),
            2 => Some(Self::IntelVpl),
            3 => Some(Self::NvidiaVideoCodecSdk),
            4 => Some(Self::AmdAmf),
            5 => Some(Self::RaspiV4l2m2m),
            _ => None,
        }
    }
}

/// 変換フレームの方向。既存 `SoraTransformableFrameDirection` に対応する。
#[pyclass(module = "sora_sdk", eq, eq_int, skip_from_py_object)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SoraTransformableFrameDirection {
    /// 不明。
    #[pyo3(name = "UNKNOWN")]
    Unknown = 0,
    /// 受信。
    #[pyo3(name = "RECEIVER")]
    Receiver = 1,
    /// 送信。
    #[pyo3(name = "SENDER")]
    Sender = 2,
}

#[pymethods]
impl SoraTransformableFrameDirection {
    /// 整数値。既存 IntEnum の value に対応する。
    #[getter]
    fn value(&self) -> i32 {
        *self as i32
    }
}

/// 変換音声フレームの種別。既存 `SoraTransformableAudioFrameType` に対応する。
#[pyclass(module = "sora_sdk", eq, eq_int, skip_from_py_object)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SoraTransformableAudioFrameType {
    /// 無音。
    #[pyo3(name = "EMPTY")]
    Empty = 0,
    /// 発話。
    #[pyo3(name = "SPEECH")]
    Speech = 1,
    /// 快適雑音。
    #[pyo3(name = "CN")]
    Cn = 2,
}

#[pymethods]
impl SoraTransformableAudioFrameType {
    /// 整数値。既存 IntEnum の value に対応する。
    #[getter]
    fn value(&self) -> i32 {
        *self as i32
    }
}
