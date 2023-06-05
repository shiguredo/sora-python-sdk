#include "sora.h"

Sora::Sora(bool use_hardware_encoder) {
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
    SoraTrackInterface* video_source) {
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
  config.metadata = ConvertJsonValue(metadata);
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

boost::json::value Sora::ConvertJsonValue(nb::handle value) {
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
      json_array.emplace_back(ConvertJsonValue(value));
    return json_array;
  } else if (nb::isinstance<nb::dict>(value)) {
    nb::dict nb_dict = nb::cast<nb::dict>(value);
    boost::json::object json_object;
    for (auto [k, v] : nb_dict)
      json_object.emplace(nb::cast<const char*>(k), ConvertJsonValue(v));
    return json_object;
  }
  throw nb::type_error("Invalid JSON value in metadata");
}
