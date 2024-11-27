#include <exception>

#include "sora.h"

// WebRTC
#include <rtc_base/crypto_random.h>

Sora::Sora(std::optional<bool> use_hardware_encoder,
           std::optional<std::string> openh264) {
  factory_.reset(new SoraFactory(use_hardware_encoder, openh264));
}

Sora::~Sora() {
  Disposed();
}

std::shared_ptr<SoraConnection> Sora::CreateConnection(
    const nb::handle& signaling_urls,
    const std::string& role,
    const std::string& channel_id,
    std::optional<std::string> client_id,
    std::optional<std::string> bundle_id,
    const nb::handle& metadata,
    const nb::handle& signaling_notify_metadata,
    SoraTrackInterface* audio_source,
    SoraTrackInterface* video_source,
    SoraAudioFrameTransformer* audio_frame_transformer,
    SoraVideoFrameTransformer* video_frame_transformer,
    std::optional<bool> audio,
    std::optional<bool> video,
    std::optional<std::string> audio_codec_type,
    std::optional<std::string> video_codec_type,
    std::optional<int> video_bit_rate,
    std::optional<int> audio_bit_rate,
    const nb::handle& video_vp9_params,
    const nb::handle& video_av1_params,
    const nb::handle& video_h264_params,
    const nb::handle& audio_opus_params,
    std::optional<bool> simulcast,
    std::optional<bool> spotlight,
    std::optional<int> spotlight_number,
    std::optional<std::string> simulcast_rid,
    std::optional<std::string> spotlight_focus_rid,
    std::optional<std::string> spotlight_unfocus_rid,
    const nb::handle& forwarding_filter,
    const nb::handle& forwarding_filters,
    const nb::handle& data_channels,
    std::optional<bool> data_channel_signaling,
    std::optional<bool> ignore_disconnect_websocket,
    std::optional<int> data_channel_signaling_timeout,
    std::optional<int> disconnect_wait_timeout,
    std::optional<int> websocket_close_timeout,
    std::optional<int> websocket_connection_timeout,
    std::optional<std::string> audio_streaming_language_code,
    std::optional<bool> insecure,
    std::optional<nb::bytes> client_cert,
    std::optional<nb::bytes> client_key,
    std::optional<nb::bytes> ca_cert,
    std::optional<std::string> proxy_url,
    std::optional<std::string> proxy_username,
    std::optional<std::string> proxy_password,
    std::optional<std::string> proxy_agent) {
  std::shared_ptr<SoraConnection> conn = std::make_shared<SoraConnection>(this);
  sora::SoraSignalingConfig config;
  config.pc_factory = factory_->GetPeerConnectionFactory();
  config.observer = conn;
  config.signaling_urls = ConvertSignalingUrls(signaling_urls);
  config.role = role;
  config.channel_id = channel_id;
  if (client_id) {
    config.client_id = *client_id;
  }
  if (bundle_id) {
    config.bundle_id = *bundle_id;
  }
  config.multistream = true;
  if (video) {
    config.video = *video;
  }
  if (audio) {
    config.audio = *audio;
  }
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
  if (video_vp9_params) {
    config.video_vp9_params = ConvertJsonValue(
        video_vp9_params, "Invalid JSON value in video_vp9_params");
  }
  if (video_av1_params) {
    config.video_av1_params = ConvertJsonValue(
        video_av1_params, "Invalid JSON value in video_av1_params");
  }
  if (video_h264_params) {
    config.video_h264_params = ConvertJsonValue(
        video_h264_params, "Invalid JSON value in video_h264_params");
  }
  if (audio_opus_params) {
    config.audio_opus_params = ConvertJsonValue(
        audio_opus_params, "Invalid JSON value in audio_opus_params");
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
  config.forwarding_filter = ConvertForwardingFilter(forwarding_filter);
  config.forwarding_filters = ConvertForwardingFilters(forwarding_filters);
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
  if (audio_streaming_language_code) {
    config.audio_streaming_language_code = *audio_streaming_language_code;
  }
  if (insecure) {
    config.insecure = *insecure;
  }
  if (client_cert) {
    config.client_cert = client_cert->c_str();
  }
  if (client_key) {
    config.client_key = client_key->c_str();
  }
  if (ca_cert) {
    config.ca_cert = ca_cert->c_str();
  }
  if (proxy_url) {
    config.proxy_url = *proxy_url;
  }
  if (proxy_username) {
    config.proxy_username = *proxy_username;
  }
  if (proxy_password) {
    config.proxy_password = *proxy_password;
  }
  if (proxy_agent) {
    config.proxy_agent = *proxy_agent;
  }
  config.network_manager = factory_->default_network_manager();
  config.socket_factory = factory_->default_socket_factory();

  config.sora_client = "Sora Python SDK";
  try {
    nb::module_ importlib_metadata = nb::module_::import_("importlib.metadata");
    auto version = importlib_metadata.attr("version")("sora_sdk");
    if (nb::isinstance<const char*>(version)) {
      config.sora_client += " ";
      config.sora_client += nb::cast<const char*>(version);
    }
  } catch (std::exception&) {
    // バージョン情報の取得に失敗した場合にはエラーにはせずに単に無視する
    // なお、基本的にここに来ることはないはずだけど、念の為にハンドリングしている
  }

  conn->Init(config);
  if (audio_source) {
    conn->SetAudioTrack(audio_source);
  }
  if (video_source) {
    conn->SetVideoTrack(video_source);
  }
  if (audio_frame_transformer) {
    conn->SetAudioSenderFrameTransformer(audio_frame_transformer);
  }
  if (video_frame_transformer) {
    conn->SetVideoSenderFrameTransformer(video_frame_transformer);
  }

  weak_connections_.erase(
      std::remove_if(
          weak_connections_.begin(), weak_connections_.end(),
          [](std::weak_ptr<SoraConnection> w) { return w.expired(); }),
      weak_connections_.end());
  weak_connections_.push_back(conn);

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
  auto track =
      factory_->GetPeerConnectionFactory()->CreateVideoTrack(source, track_id);

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

std::optional<std::vector<sora::SoraSignalingConfig::ForwardingFilter>>
Sora::ConvertForwardingFilters(const nb::handle value) {
  auto forwarding_filters_value =
      ConvertJsonValue(value, "Invalid JSON value in forwarding_filters");
  if (forwarding_filters_value.is_null()) {
    return std::nullopt;
  }

  std::vector<sora::SoraSignalingConfig::ForwardingFilter> forwarding_filters;

  for (auto forwarding_filter_value : forwarding_filters_value.as_array()) {
    sora::SoraSignalingConfig::ForwardingFilter filter;
    try {
      auto object = forwarding_filter_value.as_object();
      if (!object["action"].is_null()) {
        filter.action = std::string(object["action"].as_string());
      }
      for (auto or_rule : object["rules"].as_array()) {
        std::vector<sora::SoraSignalingConfig::ForwardingFilter::Rule> rules;
        for (auto and_rule_value : or_rule.as_array()) {
          auto and_rule = and_rule_value.as_object();
          sora::SoraSignalingConfig::ForwardingFilter::Rule rule;
          rule.field = and_rule["field"].as_string();
          rule.op = and_rule["operator"].as_string();
          for (auto value : and_rule["values"].as_array()) {
            rule.values.push_back(value.as_string().c_str());
          }
          rules.push_back(rule);
        }
        filter.rules.push_back(rules);
      }
      if (!object["version"].is_null()) {
        filter.version = std::string(object["version"].as_string());
      }
      if (!object["metadata"].is_null()) {
        filter.metadata = object["metadata"];
      }
      if (!object["name"].is_null()) {
        filter.name = std::string(object["name"].as_string());
      }
      if (!object["priority"].is_null()) {
        filter.priority = boost::json::value_to<int>(object["priority"]);
      }
    } catch (std::exception&) {
      throw nb::type_error("Invalid forwarding_filter");
    }
    forwarding_filters.push_back(filter);
  }

  return forwarding_filters;
}

std::optional<sora::SoraSignalingConfig::ForwardingFilter>
Sora::ConvertForwardingFilter(const nb::handle value) {
  auto forwarding_filter_value =
      ConvertJsonValue(value, "Invalid JSON value in forwarding_filter");
  if (forwarding_filter_value.is_null()) {
    return std::nullopt;
  }

  sora::SoraSignalingConfig::ForwardingFilter filter;

  try {
    auto object = forwarding_filter_value.as_object();
    if (!object["action"].is_null()) {
      filter.action = std::string(object["action"].as_string());
    }
    for (auto or_rule : object["rules"].as_array()) {
      std::vector<sora::SoraSignalingConfig::ForwardingFilter::Rule> rules;
      for (auto and_rule_value : or_rule.as_array()) {
        auto and_rule = and_rule_value.as_object();
        sora::SoraSignalingConfig::ForwardingFilter::Rule rule;
        rule.field = and_rule["field"].as_string();
        rule.op = and_rule["operator"].as_string();
        for (auto value : and_rule["values"].as_array()) {
          rule.values.push_back(value.as_string().c_str());
        }
        rules.push_back(rule);
      }
      filter.rules.push_back(rules);
    }
    if (!object["version"].is_null()) {
      filter.version = std::string(object["version"].as_string());
    }
    if (!object["metadata"].is_null()) {
      filter.metadata = object["metadata"];
    }
    if (!object["name"].is_null()) {
      filter.name = std::string(object["name"].as_string());
    }
    if (!object["priority"].is_null()) {
      filter.priority = boost::json::value_to<int>(object["priority"]);
    }
  } catch (std::exception&) {
    throw nb::type_error("Invalid forwarding_filter");
  }

  return filter;
}

std::vector<std::string> Sora::ConvertSignalingUrls(const nb::handle value) {
  auto signaling_urls_value =
      ConvertJsonValue(value, "Invalid JSON value in signaling_urls");
  if (!signaling_urls_value.is_array()) {
    throw nb::type_error("`signaling_urls` should be a list of strings");
  }

  std::vector<std::string> signaling_urls;
  for (auto signaling_url_value : signaling_urls_value.as_array()) {
    if (!signaling_url_value.is_string()) {
      throw nb::type_error("`signaling_urls` should be a list of strings");
    }
    signaling_urls.push_back(
        boost::json::value_to<std::string>(signaling_url_value));
  }

  if (signaling_urls.empty()) {
    throw nb::type_error("`signaling_urls` should not be empty");
  }
  return signaling_urls;
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
  if (!object["header"].is_null()) {
    const auto& ar = object["header"].as_array();
    data_channel.header.emplace(ar.begin(), ar.end());
  }

  return data_channel;
}
}  // namespace sora
