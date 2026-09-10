//! 映像符号化器情報の Python 公開型。
//!
//! 既存 `sora_sdk` の符号化器 preference / capability に対応する。
//! 実装指定の解決は既定構成の範囲で行い、
//! 対応外の実装指定は内蔵実装に読み替える。

use ::sora_sdk::{
    CodecDirection, InternalVideoCodecCapability, SoraConnectionContextConfig,
    VideoCodecCapability, VideoCodecImplementation, VideoCodecPreference,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::enums::{SoraVideoCodecImplementation, SoraVideoCodecType};

/// 符号化器の実装名に対応する公開値を返す。未知は内蔵に読み替える。
fn implementation_to_public(name: &str) -> SoraVideoCodecImplementation {
    match name {
        "openh264" => SoraVideoCodecImplementation::CiscoOpenh264,
        "vpl" => SoraVideoCodecImplementation::IntelVpl,
        "nvcodec" => SoraVideoCodecImplementation::NvidiaVideoCodecSdk,
        "amf" => SoraVideoCodecImplementation::AmdAmf,
        "v4l2" => SoraVideoCodecImplementation::RaspiV4l2m2m,
        _ => SoraVideoCodecImplementation::Internal,
    }
}

/// 公開値に対応する実装を返す。対応外は内蔵に読み替える。
fn public_to_implementation(value: SoraVideoCodecImplementation) -> VideoCodecImplementation {
    // 内蔵実装の取得口だけが無条件に使える。
    // 対応外の指定も内蔵に読み替え、利用可否の判定は capability 側に任せる。
    let _ = value;
    InternalVideoCodecCapability::new().get_implementation()
}

/// 整数か列挙から符号化方式を読む。
fn parse_codec_type(value: &Bound<'_, PyAny>) -> PyResult<SoraVideoCodecType> {
    let raw = value
        .extract::<i64>()
        .or_else(|_| {
            value
                .getattr("value")
                .and_then(|member| member.extract::<i64>())
        })
        .map_err(|_| PyValueError::new_err("codec type must be a SoraVideoCodecType or an int"))?;
    SoraVideoCodecType::from_int(raw)
        .ok_or_else(|| PyValueError::new_err(format!("unsupported video codec type {raw}")))
}

/// 整数か列挙から実装指定を読む。なしはなしとする。
fn parse_implementation(
    value: Option<Bound<'_, PyAny>>,
) -> PyResult<Option<SoraVideoCodecImplementation>> {
    let Some(value) = value else {
        return Ok(None);
    };
    if value.is_none() {
        return Ok(None);
    }
    let raw = value
        .extract::<i64>()
        .or_else(|_| {
            value
                .getattr("value")
                .and_then(|member| member.extract::<i64>())
        })
        .map_err(|_| {
            PyValueError::new_err("implementation must be a SoraVideoCodecImplementation or an int")
        })?;
    SoraVideoCodecImplementation::from_int(raw)
        .map(Some)
        .ok_or_else(|| {
            PyValueError::new_err(format!("unsupported video codec implementation {raw}"))
        })
}

/// preference の符号化器項目。
#[pyclass(module = "sora_sdk", skip_from_py_object)]
#[derive(Debug, Clone)]
pub(crate) struct SoraVideoCodecPreferenceCodec {
    /// 符号化方式。
    codec_type: SoraVideoCodecType,
    /// 符号化側の実装。
    encoder: Option<SoraVideoCodecImplementation>,
    /// 復号側の実装。
    decoder: Option<SoraVideoCodecImplementation>,
}

#[pymethods]
impl SoraVideoCodecPreferenceCodec {
    /// 項目を作る。
    #[new]
    #[pyo3(signature = (r#type = None, encoder = None, decoder = None, parameters = None))]
    fn new(
        r#type: Option<Bound<'_, PyAny>>,
        encoder: Option<Bound<'_, PyAny>>,
        decoder: Option<Bound<'_, PyAny>>,
        parameters: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        // parameters は受け付けるが使わない。既存 API との互換用。
        let _ = parameters;
        // 既定は VP8 とする。既存の無引数生成に対応する。
        let codec_type = r#type
            .as_ref()
            .map(parse_codec_type)
            .transpose()?
            .unwrap_or(SoraVideoCodecType::Vp8);
        Ok(Self {
            codec_type,
            encoder: parse_implementation(encoder)?,
            decoder: parse_implementation(decoder)?,
        })
    }

    /// 符号化方式。
    #[getter]
    fn r#type(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        to_enum(py, "SoraVideoCodecType", codec_type_name(self.codec_type))
    }

    /// 符号化方式を設定する。
    #[setter]
    fn set_type(&mut self, value: Bound<'_, PyAny>) -> PyResult<()> {
        self.codec_type = parse_codec_type(&value)?;
        Ok(())
    }

    /// 符号化側の実装。
    #[getter]
    fn encoder(&self, py: Python<'_>) -> PyResult<Option<Py<PyAny>>> {
        self.encoder
            .map(|value| {
                to_enum(
                    py,
                    "SoraVideoCodecImplementation",
                    implementation_name(value),
                )
            })
            .transpose()
    }

    /// 符号化側の実装を設定する。
    #[setter]
    fn set_encoder(&mut self, value: Option<Bound<'_, PyAny>>) -> PyResult<()> {
        self.encoder = parse_implementation(value)?;
        Ok(())
    }

    /// 復号側の実装。
    #[getter]
    fn decoder(&self, py: Python<'_>) -> PyResult<Option<Py<PyAny>>> {
        self.decoder
            .map(|value| {
                to_enum(
                    py,
                    "SoraVideoCodecImplementation",
                    implementation_name(value),
                )
            })
            .transpose()
    }

    /// 復号側の実装を設定する。
    #[setter]
    fn set_decoder(&mut self, value: Option<Bound<'_, PyAny>>) -> PyResult<()> {
        self.decoder = parse_implementation(value)?;
        Ok(())
    }

    /// 付随項目。常に空の辞書を返す。既存 API との互換用。
    #[getter]
    fn parameters(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        Ok(PyDict::new(py).into_any().unbind())
    }

    /// 付随項目を設定する。受け付けるが使わない。
    #[setter]
    fn set_parameters(&mut self, _value: Bound<'_, PyAny>) -> PyResult<()> {
        Ok(())
    }
}

/// 列挙体を作る。
fn to_enum(py: Python<'_>, type_name: &str, member_name: &str) -> PyResult<Py<PyAny>> {
    let module = py.import("sora_sdk")?;
    Ok(module.getattr(type_name)?.getattr(member_name)?.unbind())
}

/// 符号化方式の要素名を返す。
fn codec_type_name(value: SoraVideoCodecType) -> &'static str {
    match value {
        SoraVideoCodecType::Vp8 => "VP8",
        SoraVideoCodecType::Vp9 => "VP9",
        SoraVideoCodecType::H264 => "H264",
        SoraVideoCodecType::H265 => "H265",
        SoraVideoCodecType::Av1 => "AV1",
    }
}

/// 実装指定の要素名を返す。
fn implementation_name(value: SoraVideoCodecImplementation) -> &'static str {
    match value {
        SoraVideoCodecImplementation::Internal => "INTERNAL",
        SoraVideoCodecImplementation::CiscoOpenh264 => "CISCO_OPENH264",
        SoraVideoCodecImplementation::IntelVpl => "INTEL_VPL",
        SoraVideoCodecImplementation::NvidiaVideoCodecSdk => "NVIDIA_VIDEO_CODEC_SDK",
        SoraVideoCodecImplementation::AmdAmf => "AMD_AMF",
        SoraVideoCodecImplementation::RaspiV4l2m2m => "RASPI_V4L2M2M",
    }
}

/// 映像符号化器の preference。
#[pyclass(module = "sora_sdk", skip_from_py_object)]
#[derive(Debug, Clone, Default)]
pub(crate) struct SoraVideoCodecPreference {
    /// 符号化器項目列。
    codecs: Vec<SoraVideoCodecPreferenceCodec>,
}

#[pymethods]
impl SoraVideoCodecPreference {
    /// preference を作る。
    #[new]
    #[pyo3(signature = (codecs = None))]
    fn new(codecs: Option<Vec<Py<SoraVideoCodecPreferenceCodec>>>) -> PyResult<Self> {
        // 参照共有ではなく複写で保持する。
        Ok(Self {
            codecs: Python::attach(|py| {
                codecs
                    .unwrap_or_default()
                    .iter()
                    .map(|codec| codec.borrow(py).clone())
                    .collect()
            }),
        })
    }

    /// 符号化器項目列。
    #[getter]
    fn codecs(&self, py: Python<'_>) -> PyResult<Vec<Py<SoraVideoCodecPreferenceCodec>>> {
        self.codecs
            .iter()
            .map(|codec| Py::new(py, codec.clone()))
            .collect()
    }

    /// 符号化器項目列を設定する。
    #[setter]
    fn set_codecs(
        &mut self,
        py: Python<'_>,
        value: Vec<Py<SoraVideoCodecPreferenceCodec>>,
    ) -> PyResult<()> {
        self.codecs = value.iter().map(|codec| codec.borrow(py).clone()).collect();
        Ok(())
    }

    /// 辞書化する。
    fn to_json(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let items = self
            .codecs
            .iter()
            .map(|codec| {
                let dict = PyDict::new(py);
                dict.set_item("type", codec.codec_type as i32)?;
                dict.set_item("encoder", codec.encoder.map(|value| value as i32))?;
                dict.set_item("decoder", codec.decoder.map(|value| value as i32))?;
                Ok(dict.into_any().unbind())
            })
            .collect::<PyResult<Vec<Py<PyAny>>>>()?;
        Ok(items.into_pyobject(py)?.into_any().unbind())
    }

    /// 方式の位置を探す。なければなしとする。
    fn find(&self, codec_type: Bound<'_, PyAny>) -> PyResult<Option<usize>> {
        let codec_type = parse_codec_type(&codec_type)?;
        Ok(self
            .codecs
            .iter()
            .position(|codec| codec.codec_type == codec_type))
    }

    /// 方式の位置を返す。なければ追加する。
    fn get_or_add(&mut self, codec_type: Bound<'_, PyAny>) -> PyResult<usize> {
        let codec_type = parse_codec_type(&codec_type)?;
        if let Some(index) = self
            .codecs
            .iter()
            .position(|codec| codec.codec_type == codec_type)
        {
            return Ok(index);
        }
        self.codecs.push(SoraVideoCodecPreferenceCodec {
            codec_type,
            encoder: None,
            decoder: None,
        });
        Ok(self.codecs.len() - 1)
    }

    /// 実装指定を含むか調べる。
    fn has_implementation(&self, implementation: Bound<'_, PyAny>) -> PyResult<bool> {
        let Some(implementation) = parse_implementation(Some(implementation))? else {
            return Ok(false);
        };
        Ok(self.codecs.iter().any(|codec| {
            codec.encoder == Some(implementation) || codec.decoder == Some(implementation)
        }))
    }

    /// 他の preference を取り込む。
    fn merge(&mut self, py: Python<'_>, other: Py<SoraVideoCodecPreference>) -> PyResult<()> {
        let other = other.borrow(py).codecs.clone();
        for codec in other {
            if !self
                .codecs
                .iter()
                .any(|mine| mine.codec_type == codec.codec_type)
            {
                self.codecs.push(codec);
            }
        }
        Ok(())
    }
}

impl SoraVideoCodecPreference {
    /// 組み立て器用の preference に変える。
    pub(crate) fn to_sdk_preference(&self) -> VideoCodecPreference {
        use ::sora_sdk::PreferenceCodec;
        let mut codecs = Vec::new();
        for codec in &self.codecs {
            let codec_type = codec.codec_type.to_webrtc();
            if let Some(encoder) = codec.encoder {
                codecs.push(PreferenceCodec::new(
                    CodecDirection::Encoder,
                    codec_type,
                    public_to_implementation(encoder),
                ));
            }
            if let Some(decoder) = codec.decoder {
                codecs.push(PreferenceCodec::new(
                    CodecDirection::Decoder,
                    codec_type,
                    public_to_implementation(decoder),
                ));
            }
        }
        VideoCodecPreference::new(codecs)
    }
}

/// 符号化器情報の付随項目。
#[pyclass(module = "sora_sdk", skip_from_py_object)]
#[derive(Debug, Clone, Default)]
pub(crate) struct SoraVideoCodecCapabilityParameters;

#[pymethods]
impl SoraVideoCodecCapabilityParameters {
    /// 版。
    #[getter]
    fn version(&self) -> Option<String> {
        None
    }

    /// openh264 経路。
    #[getter]
    fn openh264_path(&self) -> Option<String> {
        None
    }

    /// VPL 実装名。
    #[getter]
    fn vpl_impl(&self) -> Option<String> {
        None
    }

    /// VPL 実装値。
    #[getter]
    fn vpl_impl_value(&self) -> Option<i32> {
        None
    }

    /// NVCODEC 図形装置名。
    #[getter]
    fn nvcodec_gpu_device_name(&self) -> Option<String> {
        None
    }

    /// AMF 実行時版。
    #[getter]
    fn amf_runtime_version(&self) -> Option<String> {
        None
    }

    /// AMF 組込版。
    #[getter]
    fn amf_embedded_version(&self) -> Option<String> {
        None
    }
}

/// 符号化器情報の符号化器項目。
#[pyclass(module = "sora_sdk", skip_from_py_object)]
#[derive(Debug, Clone)]
pub(crate) struct SoraVideoCodecCapabilityCodec {
    /// 符号化方式。
    codec_type: SoraVideoCodecType,
    /// 符号化可否。
    encoder: bool,
    /// 復号可否。
    decoder: bool,
}

#[pymethods]
impl SoraVideoCodecCapabilityCodec {
    /// 符号化方式。
    #[getter]
    fn r#type(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        to_enum(py, "SoraVideoCodecType", codec_type_name(self.codec_type))
    }

    /// 符号化可否。
    #[getter]
    fn encoder(&self) -> bool {
        self.encoder
    }

    /// 復号可否。
    #[getter]
    fn decoder(&self) -> bool {
        self.decoder
    }

    /// 付随項目。
    #[getter]
    fn parameters(&self, py: Python<'_>) -> PyResult<Py<SoraVideoCodecCapabilityParameters>> {
        Py::new(py, SoraVideoCodecCapabilityParameters)
    }
}

/// 符号化器情報の機関項目。
#[pyclass(module = "sora_sdk", skip_from_py_object)]
#[derive(Debug, Clone)]
pub(crate) struct SoraVideoCodecCapabilityEngine {
    /// 実装。
    implementation: SoraVideoCodecImplementation,
    /// 符号化器項目列。
    codecs: Vec<SoraVideoCodecCapabilityCodec>,
}

#[pymethods]
impl SoraVideoCodecCapabilityEngine {
    /// 実装。
    #[getter]
    fn name(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        to_enum(
            py,
            "SoraVideoCodecImplementation",
            implementation_name(self.implementation),
        )
    }

    /// 符号化器項目列。
    #[getter]
    fn codecs(&self, py: Python<'_>) -> PyResult<Vec<Py<SoraVideoCodecCapabilityCodec>>> {
        self.codecs
            .iter()
            .map(|codec| Py::new(py, codec.clone()))
            .collect()
    }

    /// 付随項目。
    #[getter]
    fn parameters(&self, py: Python<'_>) -> PyResult<Py<SoraVideoCodecCapabilityParameters>> {
        Py::new(py, SoraVideoCodecCapabilityParameters)
    }
}

/// 映像符号化器情報。
#[pyclass(module = "sora_sdk", skip_from_py_object)]
#[derive(Debug, Clone)]
pub(crate) struct SoraVideoCodecCapability {
    /// 機関項目列。
    engines: Vec<SoraVideoCodecCapabilityEngine>,
}

#[pymethods]
impl SoraVideoCodecCapability {
    /// 機関項目列。
    #[getter]
    fn engines(&self, py: Python<'_>) -> PyResult<Vec<Py<SoraVideoCodecCapabilityEngine>>> {
        self.engines
            .iter()
            .map(|engine| Py::new(py, engine.clone()))
            .collect()
    }

    /// 辞書化する。
    fn to_json(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let engines = self
            .engines
            .iter()
            .map(|engine| {
                let dict = PyDict::new(py);
                dict.set_item("name", engine.implementation as i32)?;
                let codecs = engine
                    .codecs
                    .iter()
                    .map(|codec| {
                        let item = PyDict::new(py);
                        item.set_item("type", codec.codec_type as i32)?;
                        item.set_item("encoder", codec.encoder)?;
                        item.set_item("decoder", codec.decoder)?;
                        Ok(item.into_any().unbind())
                    })
                    .collect::<PyResult<Vec<Py<PyAny>>>>()?;
                dict.set_item("codecs", codecs)?;
                Ok(dict.into_any().unbind())
            })
            .collect::<PyResult<Vec<Py<PyAny>>>>()?;
        let root = PyDict::new(py);
        root.set_item("engines", engines)?;
        Ok(root.into_any().unbind())
    }
}

/// 既定構成の符号化器情報を作る。
fn default_capability() -> SoraVideoCodecCapability {
    use shiguredo_webrtc::VideoCodecType;
    let config = SoraConnectionContextConfig::default();
    let order = [
        VideoCodecType::Vp8,
        VideoCodecType::Vp9,
        VideoCodecType::Av1,
        VideoCodecType::H264,
        VideoCodecType::H265,
    ];
    let public_order = [
        SoraVideoCodecType::Vp8,
        SoraVideoCodecType::Vp9,
        SoraVideoCodecType::Av1,
        SoraVideoCodecType::H264,
        SoraVideoCodecType::H265,
    ];
    let engines = config
        .video_codec_capabilities
        .iter()
        .map(|capability| {
            let codecs = order
                .iter()
                .zip(public_order.iter())
                .map(|(webrtc_type, public_type)| SoraVideoCodecCapabilityCodec {
                    codec_type: *public_type,
                    encoder: capability.is_supported(CodecDirection::Encoder, *webrtc_type),
                    decoder: capability.is_supported(CodecDirection::Decoder, *webrtc_type),
                })
                .collect();
            SoraVideoCodecCapabilityEngine {
                implementation: implementation_to_public(capability.get_implementation().name()),
                codecs,
            }
        })
        .collect();
    SoraVideoCodecCapability { engines }
}

/// 映像符号化器情報を返す。
#[pyfunction]
#[pyo3(signature = (openh264 = None))]
pub(crate) fn get_video_codec_capability(
    py: Python<'_>,
    openh264: Option<String>,
) -> PyResult<Py<SoraVideoCodecCapability>> {
    // openh264 経路は受け付けるが使わない。既存 API との互換用。
    let _ = openh264;
    Py::new(py, default_capability())
}

/// 実装指定から preference を作る。
#[pyfunction]
pub(crate) fn create_video_codec_preference_from_implementation(
    py: Python<'_>,
    capability: Py<SoraVideoCodecCapability>,
    implementation: Bound<'_, PyAny>,
) -> PyResult<Py<SoraVideoCodecPreference>> {
    let implementation = parse_implementation(Some(implementation))?.ok_or_else(|| {
        PyValueError::new_err("implementation must be a SoraVideoCodecImplementation")
    })?;
    let capability = capability.borrow(py).clone();
    let codecs = capability
        .engines
        .iter()
        .find(|engine| engine.implementation == implementation)
        .map(|engine| {
            engine
                .codecs
                .iter()
                .map(|codec| SoraVideoCodecPreferenceCodec {
                    codec_type: codec.codec_type,
                    encoder: codec.encoder.then_some(implementation),
                    decoder: codec.decoder.then_some(implementation),
                })
                .collect()
        })
        .unwrap_or_default();
    Py::new(py, SoraVideoCodecPreference { codecs })
}
