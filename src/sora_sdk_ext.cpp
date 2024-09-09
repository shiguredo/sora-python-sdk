// nonobind
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/function.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/shared_ptr.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

#include "sora.h"
#include "sora_audio_sink.h"
#include "sora_audio_source.h"
#include "sora_audio_stream_sink.h"
#include "sora_connection.h"
#include "sora_log.h"
#include "sora_track_interface.h"
#include "sora_vad.h"
#include "sora_video_sink.h"
#include "sora_video_source.h"

namespace nb = nanobind;
using namespace nb::literals;

/**
 * クラスにコールバック関数のメンバー変数がある場合は全て以下のように、
 * Py_VISIT を呼び出すことによりガベージコレクタにその存在を伝える関数を作る。
 * やっておかないと終了時にリークエラーが発生する。
 */
int audio_sink_tp_traverse(PyObject* self, visitproc visit, void* arg) {
  // インスタンスを取得する
  SoraAudioSinkImpl* audio_sink = nb::inst_ptr<SoraAudioSinkImpl>(self);

  // コールバックがある場合
  if (audio_sink->on_format_) {
    // コールバック変数の参照を取得して
    nb::object on_format =
        nb::cast(audio_sink->on_format_, nb::rv_policy::none);
    // ガベージコレクタに伝える
    Py_VISIT(on_format.ptr());
  }

  // 上に同じ
  if (audio_sink->on_data_) {
    nb::object on_data = nb::cast(audio_sink->on_data_, nb::rv_policy::none);
    Py_VISIT(on_data.ptr());
  }

  return 0;
}

/**
 * PyType_Slot の Py_tp_traverse に先に作った関数を設定する。
 * 定義した PyType_Slot は NB_MODULE 内の対応するクラスに対して紐づける。
 */
PyType_Slot audio_sink_slots[] = {
    {Py_tp_traverse, (void*)audio_sink_tp_traverse},
    {0, nullptr}};

int audio_stream_sink_tp_traverse(PyObject* self, visitproc visit, void* arg) {
  SoraAudioStreamSinkImpl* audio_sink =
      nb::inst_ptr<SoraAudioStreamSinkImpl>(self);

  if (audio_sink->on_frame_) {
    nb::object on_frame = nb::cast(audio_sink->on_frame_, nb::rv_policy::none);
    Py_VISIT(on_frame.ptr());
  }

  return 0;
}

PyType_Slot audio_stream_sink_slots[] = {
    {Py_tp_traverse, (void*)audio_stream_sink_tp_traverse},
    {0, nullptr}};

int video_sink_tp_traverse(PyObject* self, visitproc visit, void* arg) {
  SoraVideoSinkImpl* video_sink = nb::inst_ptr<SoraVideoSinkImpl>(self);

  if (video_sink->on_frame_) {
    nb::object on_frame = nb::cast(video_sink->on_frame_, nb::rv_policy::none);
    Py_VISIT(on_frame.ptr());
  }

  return 0;
}

PyType_Slot video_sink_slots[] = {
    {Py_tp_traverse, (void*)video_sink_tp_traverse},
    {0, nullptr}};

int connection_tp_traverse(PyObject* self, visitproc visit, void* arg) {
  SoraConnection* conn = nb::inst_ptr<SoraConnection>(self);

  if (conn->on_set_offer_) {
    nb::object on_set_offer =
        nb::cast(conn->on_set_offer_, nb::rv_policy::none);
    Py_VISIT(on_set_offer.ptr());
  }

  if (conn->on_disconnect_) {
    nb::object on_disconnect =
        nb::cast(conn->on_disconnect_, nb::rv_policy::none);
    Py_VISIT(on_disconnect.ptr());
  }

  if (conn->on_notify_) {
    nb::object on_notify = nb::cast(conn->on_notify_, nb::rv_policy::none);
    Py_VISIT(on_notify.ptr());
  }

  if (conn->on_push_) {
    nb::object on_push = nb::cast(conn->on_push_, nb::rv_policy::none);
    Py_VISIT(on_push.ptr());
  }

  if (conn->on_message_) {
    nb::object on_message = nb::cast(conn->on_message_, nb::rv_policy::none);
    Py_VISIT(on_message.ptr());
  }

  if (conn->on_switched_) {
    nb::object on_switched = nb::cast(conn->on_switched_, nb::rv_policy::none);
    Py_VISIT(on_switched.ptr());
  }

  if (conn->on_track_) {
    nb::object on_track = nb::cast(conn->on_track_, nb::rv_policy::none);
    Py_VISIT(on_track.ptr());
  }

  if (conn->on_data_channel_) {
    nb::object on_data_channel =
        nb::cast(conn->on_data_channel_, nb::rv_policy::none);
    Py_VISIT(on_data_channel.ptr());
  }

  return 0;
}

PyType_Slot connection_slots[] = {
    {Py_tp_traverse, (void*)connection_tp_traverse},
    {0, nullptr}};

/**
 * Python で利用するすべてのクラスと定数は以下のように定義しなければならない
 */
NB_MODULE(sora_sdk_ext, m) {
  nb::enum_<sora::SoraSignalingErrorCode>(m, "SoraSignalingErrorCode",
                                          nb::is_arithmetic())
      .value("CLOSE_SUCCEEDED", sora::SoraSignalingErrorCode::CLOSE_SUCCEEDED)
      .value("CLOSE_FAILED", sora::SoraSignalingErrorCode::CLOSE_FAILED)
      .value("INTERNAL_ERROR", sora::SoraSignalingErrorCode::INTERNAL_ERROR)
      .value("INVALID_PARAMETER",
             sora::SoraSignalingErrorCode::INVALID_PARAMETER)
      .value("WEBSOCKET_HANDSHAKE_FAILED",
             sora::SoraSignalingErrorCode::WEBSOCKET_HANDSHAKE_FAILED)
      .value("WEBSOCKET_ONCLOSE",
             sora::SoraSignalingErrorCode::WEBSOCKET_ONCLOSE)
      .value("WEBSOCKET_ONERROR",
             sora::SoraSignalingErrorCode::WEBSOCKET_ONERROR)
      .value("PEER_CONNECTION_STATE_FAILED",
             sora::SoraSignalingErrorCode::PEER_CONNECTION_STATE_FAILED)
      .value("ICE_FAILED", sora::SoraSignalingErrorCode::ICE_FAILED);

  nb::enum_<webrtc::MediaStreamTrackInterface::TrackState>(m, "SoraTrackState",
                                                           nb::is_arithmetic())
      .value("LIVE", webrtc::MediaStreamTrackInterface::TrackState::kLive)
      .value("ENDED", webrtc::MediaStreamTrackInterface::TrackState::kEnded);

  nb::enum_<rtc::LoggingSeverity>(m, "SoraLoggingSeverity", nb::is_arithmetic())
      .value("VERBOSE", rtc::LoggingSeverity::LS_VERBOSE)
      .value("INFO", rtc::LoggingSeverity::LS_INFO)
      .value("WARNING", rtc::LoggingSeverity::LS_WARNING)
      .value("ERROR", rtc::LoggingSeverity::LS_ERROR)
      .value("NONE", rtc::LoggingSeverity::LS_NONE);

  m.def("enable_libwebrtc_log", &EnableLibwebrtcLog);

  nb::class_<SoraTrackInterface>(m, "SoraTrackInterface")
      .def_prop_ro("kind", &SoraTrackInterface::kind)
      .def_prop_ro("id", &SoraTrackInterface::id)
      .def_prop_ro("enabled", &SoraTrackInterface::enabled)
      .def_prop_ro("state", &SoraTrackInterface::state)
      .def("set_enabled", &SoraTrackInterface::set_enabled, "enable"_a);

  nb::class_<SoraMediaTrack, SoraTrackInterface>(m, "SoraMediaTrack")
      .def_prop_ro("stream_id", &SoraMediaTrack::stream_id);

  nb::class_<SoraAudioSource, SoraTrackInterface>(m, "SoraAudioSource")
      .def("on_data",
           nb::overload_cast<const int16_t*, size_t, double>(
               &SoraAudioSource::OnData),
           "data"_a, "samples_per_channel"_a, "timestamp"_a)
      .def("on_data",
           nb::overload_cast<const int16_t*, size_t>(&SoraAudioSource::OnData),
           "data"_a, "samples_per_channel"_a)
      .def("on_data",
           nb::overload_cast<nb::ndarray<int16_t, nb::shape<-1, -1>,
                                         nb::c_contig, nb::device::cpu>,
                             double>(&SoraAudioSource::OnData),
           "ndarray"_a, "timestamp"_a)
      .def("on_data",
           nb::overload_cast<nb::ndarray<int16_t, nb::shape<-1, -1>,
                                         nb::c_contig, nb::device::cpu>>(
               &SoraAudioSource::OnData),
           "ndarray"_a);

  nb::class_<SoraVideoSource, SoraTrackInterface>(m, "SoraVideoSource")
      .def("on_captured",
           nb::overload_cast<nb::ndarray<uint8_t, nb::shape<-1, -1, 3>,
                                         nb::c_contig, nb::device::cpu>>(
               &SoraVideoSource::OnCaptured),
           "ndarray"_a)
      .def("on_captured",
           nb::overload_cast<nb::ndarray<uint8_t, nb::shape<-1, -1, 3>,
                                         nb::c_contig, nb::device::cpu>,
                             double>(&SoraVideoSource::OnCaptured),
           "ndarray"_a, "timestamp"_a)
      .def("on_captured",
           nb::overload_cast<nb::ndarray<uint8_t, nb::shape<-1, -1, 3>,
                                         nb::c_contig, nb::device::cpu>,
                             int64_t>(&SoraVideoSource::OnCaptured),
           "ndarray"_a, "timestamp_us"_a);

  nb::class_<SoraAudioSinkImpl>(m, "SoraAudioSinkImpl",
                                nb::type_slots(audio_sink_slots))
      .def(nb::init<SoraTrackInterface*, int, size_t>(), "track"_a,
           "output_frequency"_a = -1, "output_channels"_a = 0)
      .def("__del__", &SoraAudioSinkImpl::Del)
      .def("read", &SoraAudioSinkImpl::Read, "frames"_a = 0, "timeout"_a = 1,
           nb::rv_policy::move)
      .def_rw("on_data", &SoraAudioSinkImpl::on_data_)
      .def_rw("on_format", &SoraAudioSinkImpl::on_format_);

  nb::class_<SoraAudioFrame>(m, "SoraAudioFrame")
      .def("__getstate__",
           [](const SoraAudioFrame& frame) {
             // picke 化する際に呼び出されるので、すべてのデータを tuple に格納します。
             return std::make_tuple(
                 frame.VectorData(), frame.samples_per_channel(),
                 frame.num_channels(), frame.sample_rate_hz(),
                 frame.absolute_capture_timestamp_ms());
           })
      .def("__setstate__",
           [](SoraAudioFrame& frame,
              const std::tuple<std::vector<uint16_t>, size_t, size_t, int,
                               std::optional<int64_t>>& state) {
             // picke から戻す際に呼び出されるので、 tuple から SoraAudioFrame に戻します。
             new (&frame) SoraAudioFrame(std::get<0>(state), std::get<1>(state),
                                         std::get<2>(state), std::get<3>(state),
                                         std::get<4>(state));
           })
      .def_prop_ro("samples_per_channel", &SoraAudioFrame::samples_per_channel)
      .def_prop_ro("num_channels", &SoraAudioFrame::num_channels)
      .def_prop_ro("sample_rate_hz", &SoraAudioFrame::sample_rate_hz)
      .def_prop_ro("absolute_capture_timestamp_ms",
                   &SoraAudioFrame::absolute_capture_timestamp_ms)
      .def("data", &SoraAudioFrame::Data, nb::rv_policy::reference);

  nb::class_<SoraAudioStreamSinkImpl>(m, "SoraAudioStreamSinkImpl",
                                      nb::type_slots(audio_stream_sink_slots))
      .def(nb::init<SoraTrackInterface*, int, size_t>(), "track"_a,
           "output_frequency"_a = -1, "output_channels"_a = 0)
      .def("__del__", &SoraAudioStreamSinkImpl::Del)
      .def_rw("on_frame", &SoraAudioStreamSinkImpl::on_frame_);

  nb::class_<SoraVAD>(m, "SoraVAD")
      .def(nb::init<>())
      .def("analyze", &SoraVAD::Analyze, "frame"_a);

  nb::class_<SoraVideoFrame>(m, "SoraVideoFrame")
      .def("data", &SoraVideoFrame::Data, nb::rv_policy::reference);

  nb::class_<SoraVideoSinkImpl>(m, "SoraVideoSinkImpl",
                                nb::type_slots(video_sink_slots))
      .def(nb::init<SoraTrackInterface*>())
      .def("__del__", &SoraVideoSinkImpl::Del)
      .def_rw("on_frame", &SoraVideoSinkImpl::on_frame_);

  nb::class_<SoraConnection>(m, "SoraConnection",
                             nb::type_slots(connection_slots))
      .def("connect", &SoraConnection::Connect)
      .def("disconnect", &SoraConnection::Disconnect)
      .def("send_data_channel", &SoraConnection::SendDataChannel, "label"_a,
           "data"_a)
      .def("get_stats", &SoraConnection::GetStats)
      .def_rw("on_set_offer", &SoraConnection::on_set_offer_)
      .def_rw("on_disconnect", &SoraConnection::on_disconnect_)
      .def_rw("on_signaling", &SoraConnection::on_signaling_)
      .def_rw("on_notify", &SoraConnection::on_notify_)
      .def_rw("on_push", &SoraConnection::on_push_)
      .def_rw("on_message", &SoraConnection::on_message_)
      .def_rw("on_switched", &SoraConnection::on_switched_)
      .def_rw("on_track", &SoraConnection::on_track_)
      .def_rw("on_data_channel", &SoraConnection::on_data_channel_);

  nb::class_<Sora>(m, "Sora")
      .def(nb::init<std::optional<bool>, std::optional<std::string>>(),
           "use_hardware_encoder"_a = nb::none(), "openh264"_a = nb::none())
      .def("create_connection", &Sora::CreateConnection, "signaling_urls"_a,
           "role"_a, "channel_id"_a, "client_id"_a = nb::none(),
           "bundle_id"_a = nb::none(), "metadata"_a = nb::none(),
           "signaling_notify_metadata"_a = nb::none(),
           "audio_source"_a = nb::none(), "video_source"_a = nb::none(),
           "audio"_a = nb::none(), "video"_a = nb::none(),
           "audio_codec_type"_a = nb::none(), "video_codec_type"_a = nb::none(),
           "video_bit_rate"_a = nb::none(), "audio_bit_rate"_a = nb::none(),
           "video_vp9_params"_a = nb::none(), "video_av1_params"_a = nb::none(),
           "video_h264_params"_a = nb::none(), "simulcast"_a = nb::none(),
           "spotlight"_a = nb::none(), "spotlight_number"_a = nb::none(),
           "simulcast_rid"_a = nb::none(), "spotlight_focus_rid"_a = nb::none(),
           "spotlight_unfocus_rid"_a = nb::none(),
           "forwarding_filter"_a = nb::none(), "data_channels"_a = nb::none(),
           "data_channel_signaling"_a = nb::none(),
           "ignore_disconnect_websocket"_a = nb::none(),
           "data_channel_signaling_timeout"_a = nb::none(),
           "disconnect_wait_timeout"_a = nb::none(),
           "websocket_close_timeout"_a = nb::none(),
           "websocket_connection_timeout"_a = nb::none(),
           "audio_streaming_language_code"_a = nb::none(),
           "insecure"_a = nb::none(), "client_cert"_a = nb::none(),
           "client_key"_a = nb::none(), "proxy_url"_a = nb::none(),
           "proxy_username"_a = nb::none(), "proxy_password"_a = nb::none(),
           "proxy_agent"_a = nb::none(),
           nb::sig("def create_connection("
                   "self, "
                   "signaling_urls: list[str], "
                   "role: str, "
                   "channel_id: str, "
                   "client_id: Optional[str] = None, "
                   "bundle_id: Optional[str] = None, "
                   "metadata: Optional[dict] = None, "
                   "signaling_notify_metadata: Optional[dict] = None, "
                   "audio_source: Optional[SoraTrackInterface] = None, "
                   "video_source: Optional[SoraTrackInterface] = None, "
                   "audio: Optional[bool] = None, "
                   "video: Optional[bool] = None, "
                   "audio_codec_type: Optional[str] = None, "
                   "video_codec_type: Optional[str] = None, "
                   "video_bit_rate: Optional[int] = None, "
                   "audio_bit_rate: Optional[int] = None, "
                   "video_vp9_params: Optional[dict] = None, "
                   "video_av1_params: Optional[dict] = None, "
                   "video_h264_params: Optional[dict] = None, "
                   "simulcast: Optional[bool] = None, "
                   "spotlight: Optional[bool] = None, "
                   "spotlight_number: Optional[int] = None, "
                   "simulcast_rid: Optional[str] = None, "
                   "spotlight_focus_rid: Optional[str] = None, "
                   "spotlight_unfocus_rid: Optional[str] = None, "
                   "forwarding_filter: Optional[dict] = None, "
                   "data_channels: Optional[list[dict]] = None, "
                   "data_channel_signaling: Optional[bool] = None, "
                   "ignore_disconnect_websocket: Optional[bool] = None, "
                   "data_channel_signaling_timeout: Optional[int] = None, "
                   "disconnect_wait_timeout: Optional[int] = None, "
                   "websocket_close_timeout: Optional[int] = None, "
                   "websocket_connection_timeout: Optional[int] = None, "
                   "audio_streaming_language_code: Optional[str] = None, "
                   "insecure: Optional[bool] = None, "
                   "client_cert: Optional[str] = None, "
                   "client_key: Optional[str] = None, "
                   "proxy_url: Optional[str] = None, "
                   "proxy_username: Optional[str] = None, "
                   "proxy_password: Optional[str] = None, "
                   "proxy_agent: Optional[str] = None"
                   ") -> SoraConnection"))
      .def("create_audio_source", &Sora::CreateAudioSource, "channels"_a,
           "sample_rate"_a)
      .def("create_video_source", &Sora::CreateVideoSource);
}
