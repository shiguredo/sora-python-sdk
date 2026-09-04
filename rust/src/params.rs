//! 接続設定の辞書変換。
//!
//! 既存 `sora_sdk` が辞書で受ける送信設定を、
//! 組み立て器の型付き項目に変える。

use std::time::Duration;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use sora_sdk::{
    Audio, AudioOpusParams, ConnectDataChannel, ForwardingFilter, ForwardingFilterRule, JsonString,
    ProxyInfo, Video, VideoAV1Params, VideoH264Params, VideoH265Params, VideoVP9Params,
};

/// 辞書から文字列項目を読む。
fn get_str(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<String>> {
    dict.get_item(key)?
        .map(|value| {
            value
                .extract::<String>()
                .map_err(|_| PyValueError::new_err(format!("{key} must be a string")))
        })
        .transpose()
}

/// 辞書から真偽値項目を読む。
fn get_bool(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<bool>> {
    dict.get_item(key)?
        .map(|value| {
            value
                .extract::<bool>()
                .map_err(|_| PyValueError::new_err(format!("{key} must be a bool")))
        })
        .transpose()
}

/// 辞書から非負整数項目を読む。
fn get_u32(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<u32>> {
    dict.get_item(key)?
        .map(|value| {
            let raw = value
                .extract::<i64>()
                .map_err(|_| PyValueError::new_err(format!("{key} must be an int")))?;
            u32::try_from(raw)
                .map_err(|_| PyValueError::new_err(format!("{key} must be at least 0, got {raw}")))
        })
        .transpose()
}

/// 辞書から整数項目を読む。
fn get_i32(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<i32>> {
    dict.get_item(key)?
        .map(|value| {
            let raw = value
                .extract::<i64>()
                .map_err(|_| PyValueError::new_err(format!("{key} must be an int")))?;
            i32::try_from(raw)
                .map_err(|_| PyValueError::new_err(format!("{key} is out of range, got {raw}")))
        })
        .transpose()
}

/// 辞書から辞書項目を読む。
fn get_dict<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Option<Bound<'py, PyDict>>> {
    dict.get_item(key)?
        .map(|value| {
            value
                .cast_into::<PyDict>()
                .map_err(|_| PyValueError::new_err(format!("{key} must be a dict")))
        })
        .transpose()
}

/// Python 値を JSON 文字列に変える。
fn to_json_string(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<JsonString> {
    let json = py.import("json")?;
    let text = json.call_method1("dumps", (value,))?.extract::<String>()?;
    text.parse()
        .map_err(|e| PyValueError::new_err(format!("invalid JSON value: {e}")))
}

/// Opus 項目を辞書から作る。
fn parse_opus_params(dict: &Bound<'_, PyDict>) -> PyResult<AudioOpusParams> {
    Ok(AudioOpusParams {
        channels: get_u32(dict, "channels")?,
        maxplaybackrate: get_u32(dict, "maxplaybackrate")?,
        minptime: get_u32(dict, "minptime")?,
        ptime: get_u32(dict, "ptime")?,
        stereo: get_bool(dict, "stereo")?,
        sprop_stereo: get_bool(dict, "sprop_stereo")?,
        useinbandfec: get_bool(dict, "useinbandfec")?,
        usedtx: get_bool(dict, "usedtx")?,
    })
}

/// 音声設定を作る。詳細指定がなければ可否だけを使う。
pub(crate) fn parse_audio(
    audio: Option<bool>,
    codec_type: Option<String>,
    bit_rate: Option<i64>,
    opus_params: Option<Bound<'_, PyDict>>,
    has_sender: bool,
) -> PyResult<Option<Audio>> {
    if codec_type.is_none() && bit_rate.is_none() && opus_params.is_none() {
        // 送信元があるのに可否指定がない場合は有効として扱う。
        return Ok(match (audio, has_sender) {
            (Some(enabled), _) => Some(Audio::new_bool(enabled)),
            (None, true) => Some(Audio::new_bool(true)),
            (None, false) => None,
        });
    }
    let codec = codec_type.unwrap_or_else(|| "OPUS".to_string());
    if !codec.eq_ignore_ascii_case("OPUS") {
        return Err(PyValueError::new_err(format!(
            "unsupported audio_codec_type \"{codec}\", expected \"OPUS\""
        )));
    }
    let bit_rate = bit_rate
        .map(|raw| {
            u32::try_from(raw).map_err(|_| {
                PyValueError::new_err(format!("audio_bit_rate must be at least 0, got {raw}"))
            })
        })
        .transpose()?;
    let params = opus_params
        .map(|dict| parse_opus_params(&dict))
        .transpose()?;
    Ok(Some(Audio::new_opus(bit_rate, params)))
}

/// VP9 項目を辞書から作る。
fn parse_vp9_params(dict: &Bound<'_, PyDict>) -> PyResult<VideoVP9Params> {
    Ok(VideoVP9Params {
        profile_id: get_u32(dict, "profile_id")?,
    })
}

/// H264 項目を辞書から作る。
fn parse_h264_params(dict: &Bound<'_, PyDict>) -> PyResult<VideoH264Params> {
    Ok(VideoH264Params {
        profile_level_id: get_str(dict, "profile_level_id")?,
        b_frame: get_bool(dict, "b_frame")?,
    })
}

/// H265 項目を辞書から作る。
fn parse_h265_params(dict: &Bound<'_, PyDict>) -> PyResult<VideoH265Params> {
    Ok(VideoH265Params {
        level_id: get_str(dict, "level_id")?,
        profile_id: get_u32(dict, "profile_id")?,
        tier_flag: get_u32(dict, "tier_flag")?,
        tx_mode: get_str(dict, "tx_mode")?,
        b_frame: get_bool(dict, "b_frame")?,
    })
}

/// AV1 項目を辞書から作る。
fn parse_av1_params(dict: &Bound<'_, PyDict>) -> PyResult<VideoAV1Params> {
    Ok(VideoAV1Params {
        profile: get_u32(dict, "profile")?,
        level_idx: get_u32(dict, "level_idx")?,
        tier: get_u32(dict, "tier")?,
    })
}

/// 映像設定を作る。詳細指定がなければ可否だけを使う。
#[expect(clippy::too_many_arguments)]
pub(crate) fn parse_video(
    video: Option<bool>,
    codec_type: Option<String>,
    bit_rate: Option<i64>,
    vp9_params: Option<Bound<'_, PyDict>>,
    av1_params: Option<Bound<'_, PyDict>>,
    h264_params: Option<Bound<'_, PyDict>>,
    h265_params: Option<Bound<'_, PyDict>>,
    has_sender: bool,
) -> PyResult<Option<Video>> {
    let detailed = codec_type.is_some()
        || bit_rate.is_some()
        || vp9_params.is_some()
        || av1_params.is_some()
        || h264_params.is_some()
        || h265_params.is_some();
    if !detailed {
        // 送信元があるのに可否指定がない場合は有効として扱う。
        return Ok(match (video, has_sender) {
            (Some(enabled), _) => Some(Video::new_bool(enabled)),
            (None, true) => Some(Video::new_bool(true)),
            (None, false) => None,
        });
    }
    let codec = codec_type.unwrap_or_default();
    let bit_rate = bit_rate
        .map(|raw| {
            u32::try_from(raw).map_err(|_| {
                PyValueError::new_err(format!("video_bit_rate must be at least 0, got {raw}"))
            })
        })
        .transpose()?;
    match codec.to_ascii_uppercase().as_str() {
        "VP8" => Ok(Some(Video::new_vp8(bit_rate))),
        "VP9" => {
            let params = vp9_params.map(|dict| parse_vp9_params(&dict)).transpose()?;
            Ok(Some(Video::new_vp9(bit_rate, params)))
        }
        "H264" => {
            let params = h264_params
                .map(|dict| parse_h264_params(&dict))
                .transpose()?;
            Ok(Some(Video::new_h264(bit_rate, params)))
        }
        "H265" => {
            let params = h265_params
                .map(|dict| parse_h265_params(&dict))
                .transpose()?;
            Ok(Some(Video::new_h265(bit_rate, params)))
        }
        "AV1" => {
            let params = av1_params.map(|dict| parse_av1_params(&dict)).transpose()?;
            Ok(Some(Video::new_av1(bit_rate, params)))
        }
        _ => Err(PyValueError::new_err(format!(
            "unsupported video_codec_type \"{codec}\", expected one of VP8, VP9, H264, H265, AV1"
        ))),
    }
}

/// メッセージ送受信路の設定を辞書から作る。
fn parse_data_channel(dict: &Bound<'_, PyDict>) -> PyResult<ConnectDataChannel> {
    let Some(label) = get_str(dict, "label")? else {
        return Err(PyValueError::new_err(
            "data channel entry requires \"label\"",
        ));
    };
    let Some(direction) = get_str(dict, "direction")? else {
        return Err(PyValueError::new_err(
            "data channel entry requires \"direction\"",
        ));
    };
    let header = dict
        .get_item("header")?
        .map(|value| {
            let py = value.py();
            let items = value
                .cast_into::<PyList>()
                .map_err(|_| PyValueError::new_err("data channel \"header\" must be a list"))?;
            items
                .iter()
                .map(|item| to_json_string(py, &item))
                .collect::<PyResult<Vec<JsonString>>>()
        })
        .transpose()?;
    Ok(ConnectDataChannel {
        label,
        direction,
        ordered: get_bool(dict, "ordered")?,
        max_packet_life_time: get_i32(dict, "max_packet_life_time")?,
        max_retransmits: get_i32(dict, "max_retransmits")?,
        protocol: get_str(dict, "protocol")?,
        compress: get_bool(dict, "compress")?,
        header,
    })
}

/// メッセージ送受信路の設定列を作る。
pub(crate) fn parse_data_channels(
    value: Option<Bound<'_, PyAny>>,
) -> PyResult<Option<Vec<ConnectDataChannel>>> {
    let Some(value) = value else {
        return Ok(None);
    };
    let items = value
        .cast_into::<PyList>()
        .map_err(|_| PyValueError::new_err("data_channels must be a list of dicts"))?;
    items
        .iter()
        .map(|item| {
            let dict = item
                .cast_into::<PyDict>()
                .map_err(|_| PyValueError::new_err("data_channels must be a list of dicts"))?;
            parse_data_channel(&dict)
        })
        .collect::<PyResult<Vec<ConnectDataChannel>>>()
        .map(Some)
}

/// 転送選別器の規則を辞書から作る。
fn parse_filter_rule(dict: &Bound<'_, PyDict>) -> PyResult<ForwardingFilterRule> {
    let Some(field) = get_str(dict, "field")? else {
        return Err(PyValueError::new_err(
            "forwarding filter rule requires \"field\"",
        ));
    };
    let Some(operator) = get_str(dict, "operator")? else {
        return Err(PyValueError::new_err(
            "forwarding filter rule requires \"operator\"",
        ));
    };
    let values = dict
        .get_item("values")?
        .map(|value| {
            let items = value.cast_into::<PyList>().map_err(|_| {
                PyValueError::new_err("forwarding filter rule \"values\" must be a list")
            })?;
            items
                .iter()
                .map(|item| {
                    item.extract::<String>().map_err(|_| {
                        PyValueError::new_err(
                            "forwarding filter rule \"values\" must be a list of strings",
                        )
                    })
                })
                .collect::<PyResult<Vec<String>>>()
        })
        .transpose()?
        .unwrap_or_default();
    Ok(ForwardingFilterRule {
        field,
        operator,
        values,
    })
}

/// 転送選別器を作る。
fn parse_forwarding_filter(py: Python<'_>, dict: &Bound<'_, PyDict>) -> PyResult<ForwardingFilter> {
    let rules = dict
        .get_item("rules")?
        .map(|value| {
            let outer = value.cast_into::<PyList>().map_err(|_| {
                PyValueError::new_err("forwarding filter \"rules\" must be a list of lists")
            })?;
            outer
                .iter()
                .map(|group| {
                    let inner = group.cast_into::<PyList>().map_err(|_| {
                        PyValueError::new_err("forwarding filter \"rules\" must be a list of lists")
                    })?;
                    inner
                        .iter()
                        .map(|item| {
                            let rule = item.cast_into::<PyDict>().map_err(|_| {
                                PyValueError::new_err("forwarding filter rules must be dicts")
                            })?;
                            parse_filter_rule(&rule)
                        })
                        .collect::<PyResult<Vec<ForwardingFilterRule>>>()
                })
                .collect::<PyResult<Vec<Vec<ForwardingFilterRule>>>>()
        })
        .transpose()?
        .unwrap_or_default();
    let metadata = get_dict(dict, "metadata")?
        .map(|value| to_json_string(py, value.as_any()))
        .transpose()?;
    Ok(ForwardingFilter {
        name: get_str(dict, "name")?,
        priority: get_i32(dict, "priority")?,
        action: get_str(dict, "action")?,
        rules,
        version: get_str(dict, "version")?,
        metadata,
    })
}

/// 転送選別器の列を作る。単体指定は 1 件の列にまとめる。
pub(crate) fn parse_forwarding_filters(
    py: Python<'_>,
    single: Option<Bound<'_, PyDict>>,
    multiple: Option<Bound<'_, PyAny>>,
) -> PyResult<Option<Vec<ForwardingFilter>>> {
    let mut filters = Vec::new();
    if let Some(dict) = single {
        filters.push(parse_forwarding_filter(py, &dict)?);
    }
    if let Some(value) = multiple {
        let items = value
            .cast_into::<PyList>()
            .map_err(|_| PyValueError::new_err("forwarding_filters must be a list of dicts"))?;
        for item in items.iter() {
            let dict = item
                .cast_into::<PyDict>()
                .map_err(|_| PyValueError::new_err("forwarding_filters must be a list of dicts"))?;
            filters.push(parse_forwarding_filter(py, &dict)?);
        }
    }
    if filters.is_empty() {
        return Ok(None);
    }
    Ok(Some(filters))
}

/// 秒数指定を期間に変える。
pub(crate) fn parse_timeout_secs(value: Option<i64>, key: &str) -> PyResult<Option<Duration>> {
    value
        .map(|raw| {
            u64::try_from(raw)
                .map(Duration::from_secs)
                .map_err(|_| PyValueError::new_err(format!("{key} must be at least 0, got {raw}")))
        })
        .transpose()
}

/// 証明書バイト列を文字列に変える。
pub(crate) fn parse_cert_pem(value: Option<Vec<u8>>, key: &str) -> PyResult<Option<String>> {
    value
        .map(|raw| {
            String::from_utf8(raw)
                .map_err(|_| PyValueError::new_err(format!("{key} must be UTF-8 PEM bytes")))
        })
        .transpose()
}

/// 接続仲介の設定を作る。URL 指定がなければなしとする。
pub(crate) fn parse_proxy(
    url: Option<String>,
    username: Option<String>,
    password: Option<String>,
    agent: Option<String>,
) -> Option<ProxyInfo> {
    url.map(|url| ProxyInfo {
        url,
        username,
        password,
        user_agent: agent,
    })
}

/// 通知付随情報を辞書から作る。
pub(crate) fn parse_notify_metadata(
    py: Python<'_>,
    value: Option<Bound<'_, PyDict>>,
) -> PyResult<Option<JsonString>> {
    value
        .map(|dict| to_json_string(py, dict.as_any()))
        .transpose()
}
