#include <exception>

#include "sora.h"

Sora::Sora(bool use_hardware_encoder) {
  rtc::LogMessage::LogToDebug((rtc::LoggingSeverity)rtc::LS_INFO);
  rtc::LogMessage::LogTimestamps();
  rtc::LogMessage::LogThreads();
  factory_.reset(new SoraFactory(use_hardware_encoder));
}

Sora::~Sora() {
  Disposed();
}

std::shared_ptr<SoraConnection> Sora::CreateConnection(
    const std::string& signaling_url,
    const std::string& role,
    const std::string& channel_id,
    std::optional<std::string> client_id,
    std::optional<std::string> bundle_id,
    const nb::handle& metadata,
    const nb::handle& signaling_notify_metadata,
    SoraTrackInterface* audio_source,
    SoraTrackInterface* video_source,
    bool audio,
    bool video,
    std::optional<std::string> audio_codec_type,
    std::optional<std::string> video_codec_type,
    std::optional<int> video_bit_rate,
    std::optional<int> audio_bit_rate,
    std::optional<bool> simulcast,
    std::optional<bool> spotlight,
    std::optional<int> spotlight_number,
    std::optional<std::string> simulcast_rid,
    std::optional<std::string> spotlight_focus_rid,
    std::optional<std::string> spotlight_unfocus_rid,
    const nb::handle& data_channels,
    std::optional<bool> data_channel_signaling,
    std::optional<bool> ignore_disconnect_websocket,
    std::optional<int> data_channel_signaling_timeout,
    std::optional<int> disconnect_wait_timeout,
    std::optional<int> websocket_close_timeout,
    std::optional<int> websocket_connection_timeout) {
  std::shared_ptr<SoraConnection> conn = std::make_shared<SoraConnection>(this);
  sora::SoraSignalingConfig config;
  config.pc_factory = factory_->GetPeerConnectionFactory();
  config.observer = conn;
  config.signaling_urls.push_back(signaling_url);
  config.role = role;
  config.channel_id = channel_id;
  if (client_id) {
    config.client_id = *client_id;
  }
  if (bundle_id) {
    config.bundle_id = *bundle_id;
  }
  config.multistream = true;
  config.video = video;
  config.audio = audio;
  if (video_codec_type) {
    config.video_codec_type = *video_codec_type;
  }
  if (audio_codec_type) {
    config.audio_codec_type = *audio_codec_type;
  }
  if (video_bit_rate) {
    config.video_bit_rate = *video_bit_rate;
  }
  if (audio_bit_rate) {
    config.audio_bit_rate = *audio_bit_rate;
  }
  config.metadata =
      ConvertJsonValue(metadata, "Invalid JSON value in metadata");
  config.signaling_notify_metadata =
      ConvertJsonValue(signaling_notify_metadata,
                       "Invalid JSON value in signaling_notify_metadata");
  if (simulcast) {
    config.simulcast = *simulcast;
  }
  if (spotlight) {
    config.spotlight = *spotlight;
  }
  if (spotlight_number) {
    config.spotlight_number = *spotlight_number;
  }
  if (simulcast_rid) {
    config.simulcast_rid = *simulcast_rid;
  }
  if (spotlight_focus_rid) {
    config.spotlight_focus_rid = *spotlight_focus_rid;
  }
  if (spotlight_unfocus_rid) {
    config.spotlight_unfocus_rid = *spotlight_unfocus_rid;
  }
  config.data_channels = ConvertDataChannels(data_channels);
  if (data_channel_signaling) {
    config.data_channel_signaling.emplace(*data_channel_signaling);
  }
  if (ignore_disconnect_websocket) {
    config.ignore_disconnect_websocket.emplace(*ignore_disconnect_websocket);
  }
  if (data_channel_signaling_timeout) {
    config.data_channel_signaling_timeout = *data_channel_signaling_timeout;
  }
  if (disconnect_wait_timeout) {
    config.disconnect_wait_timeout = *disconnect_wait_timeout;
  }
  if (websocket_close_timeout) {
    config.websocket_close_timeout = *websocket_close_timeout;
  }
  if (websocket_connection_timeout) {
    config.websocket_connection_timeout = *websocket_connection_timeout;
  }
  config.network_manager =
      factory_->GetConnectionContext()->default_network_manager();
  config.socket_factory =
      factory_->GetConnectionContext()->default_socket_factory();
  conn->Init(config);
  if (audio_source) {
    conn->SetAudioTrack(audio_source);
  }
  if (video_source) {
    conn->SetVideoTrack(video_source);
  }
  return conn;
}

SoraAudioSource* Sora::CreateAudioSource(size_t channels, int sample_rate) {
  auto source =
      rtc::make_ref_counted<SoraAudioSourceInterface>(channels, sample_rate);

  std::string track_id = rtc::CreateRandomString(16);
  auto track = factory_->GetPeerConnectionFactory()->CreateAudioTrack(
      track_id, source.get());
  SoraAudioSource* audio_source =
      new SoraAudioSource(this, source, track, channels, sample_rate);
  return audio_source;
}

SoraVideoSource* Sora::CreateVideoSource() {
  sora::ScalableVideoTrackSourceConfig config;
  auto source = rtc::make_ref_counted<sora::ScalableVideoTrackSource>(config);

  std::string track_id = rtc::CreateRandomString(16);
  auto track = factory_->GetPeerConnectionFactory()->CreateVideoTrack(
      track_id, source.get());

  SoraVideoSource* video_source = new SoraVideoSource(this, source, track);
  return video_source;
}

boost::json::value Sora::ConvertJsonValue(nb::handle value,
                                          const char* error_message) {
  if (value.is_none()) {
    return nullptr;
  } else if (nb::isinstance<bool>(value)) {
    return nb::cast<bool>(value);
  } else if (nb::isinstance<int>(value)) {
    return nb::cast<int>(value);
  } else if (nb::isinstance<float>(value)) {
    return nb::cast<float>(value);
  } else if (nb::isinstance<const char*>(value)) {
    return nb::cast<const char*>(value);
  } else if (nb::isinstance<nb::list>(value)) {
    nb::list nb_list = nb::cast<nb::list>(value);
    boost::json::array json_array;
    for (auto v : nb_list)
      json_array.emplace_back(ConvertJsonValue(v, error_message));
    return json_array;
  } else if (nb::isinstance<nb::dict>(value)) {
    nb::dict nb_dict = nb::cast<nb::dict>(value);
    boost::json::object json_object;
    for (auto [k, v] : nb_dict)
      json_object.emplace(nb::cast<const char*>(k),
                          ConvertJsonValue(v, error_message));
    return json_object;
  }

  throw nb::type_error(error_message);
}

std::vector<sora::SoraSignalingConfig::DataChannel> Sora::ConvertDataChannels(
    const nb::handle value) {
  std::vector<sora::SoraSignalingConfig::DataChannel> data_channels;

  auto data_channels_value =
      ConvertJsonValue(value, "Invalid JSON value in data_channels");
  if (data_channels_value.is_null()) {
    return data_channels;
  }

  try {
    for (auto data_channel_value : data_channels_value.as_array()) {
      data_channels.push_back(
          boost::json::value_to<sora::SoraSignalingConfig::DataChannel>(
              data_channel_value));
    }
  } catch (std::exception&) {
    throw nb::type_error("Invalid data_channels");
  }

  return data_channels;
}

namespace sora {
SoraSignalingConfig::DataChannel tag_invoke(
    const boost::json::value_to_tag<SoraSignalingConfig::DataChannel>&,
    const boost::json::value& value) {
  auto object = value.as_object();

  SoraSignalingConfig::DataChannel data_channel;
  data_channel.label = object["label"].as_string();
  data_channel.direction = object["direction"].as_string();
  if (!object["protocol"].is_null()) {
    data_channel.protocol.emplace(object["protocol"].as_string());
  }
  if (!object["ordered"].is_null()) {
    data_channel.ordered = object["ordered"].as_bool();
  }
  if (!object["compress"].is_null()) {
    data_channel.compress = object["compress"].as_bool();
  }
  if (!object["max_packet_life_time"].is_null()) {
    data_channel.max_packet_life_time =
        boost::json::value_to<int32_t>(object["max_packet_life_time"]);
  }
  if (!object["max_retransmits"].is_null()) {
    data_channel.max_retransmits =
        boost::json::value_to<int32_t>(object["max_retransmits"]);
  }

  return data_channel;
}
}  // namespace sora
