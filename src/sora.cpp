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
    const std::string& client_id,
    const nb::handle& metadata,
    SoraTrackInterface* audio_source,
    SoraTrackInterface* video_source,
    const nb::handle& data_channels,
    std::optional<bool> data_channel_signaling,
    std::optional<bool> ignore_disconnect_websocket) {
  std::shared_ptr<SoraConnection> conn = std::make_shared<SoraConnection>(this);
  sora::SoraSignalingConfig config;
  config.pc_factory = factory_->GetPeerConnectionFactory();
  config.observer = conn;
  config.signaling_urls.push_back(signaling_url);
  config.role = role;
  config.channel_id = channel_id;
  config.client_id = client_id;
  config.video = true;
  config.audio = true;
  config.video_codec_type = "VP8";
  config.audio_codec_type = "OPUS";
  config.metadata =
      ConvertJsonValue(metadata, "Invalid JSON value in metadata");
  config.data_channels = ConvertDataChannels(data_channels);
  if (data_channel_signaling) {
    config.data_channel_signaling.emplace(*data_channel_signaling);
  }
  if (ignore_disconnect_websocket) {
    config.ignore_disconnect_websocket.emplace(*ignore_disconnect_websocket);
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

  if (!data_channels_value.is_array()) {
    throw nb::type_error("Invalid data_channels");
  }

  for (auto data_channel_value : data_channels_value.as_array()) {
    if (!data_channel_value.is_object()) {
      throw nb::type_error("Invalid data_channels");
    }

    auto object = data_channel_value.as_object();
    sora::SoraSignalingConfig::DataChannel data_channel;

    if (!object["label"].is_string()) {
      throw nb::type_error("Invalid data_channels");
    }
    data_channel.label = object["label"].as_string();

    if (!object["direction"].is_string()) {
      throw nb::type_error("Invalid data_channels");
    }
    data_channel.direction = object["direction"].as_string();

    if (!object["protocol"].is_null()) {
      if (!object["protocol"].is_string()) {
        throw nb::type_error("Invalid data_channels");
      }
      data_channel.protocol.emplace(object["protocol"].as_string());
    }

    if (!object["ordered"].is_null()) {
      if (!object["ordered"].is_bool()) {
        throw nb::type_error("Invalid data_channels");
      }
      data_channel.ordered = object["ordered"].as_bool();
    }

    if (!object["compress"].is_null()) {
      if (!object["compress"].is_bool()) {
        throw nb::type_error("Invalid data_channels");
      }
      data_channel.compress = object["compress"].as_bool();
    }

    if (!object["max_packet_life_time"].is_null()) {
      if (!object["max_packet_life_time"].is_number()) {
        throw nb::type_error("Invalid data_channels");
      }
      data_channel.max_packet_life_time =
          boost::json::value_to<int32_t>(object["max_packet_life_time"]);
    }

    if (!object["max_retransmits"].is_null()) {
      if (!object["max_retransmits"].is_number()) {
        throw nb::type_error("Invalid data_channels");
      }
      data_channel.max_retransmits =
          boost::json::value_to<int32_t>(object["max_retransmits"]);
    }
    data_channels.push_back(data_channel);
  }

  return data_channels;
}
