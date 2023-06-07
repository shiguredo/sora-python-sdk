#ifndef SORA_H_
#define SORA_H_

#include <memory>
#include <optional>
#include <vector>

#include "dispose_listener.h"
#include "sora_audio_source.h"
#include "sora_connection.h"
#include "sora_factory.h"
#include "sora_track_interface.h"
#include "sora_video_source.h"

class Sora : public DisposePublisher {
 public:
  Sora(bool use_hardware_encoder);
  ~Sora();

  std::shared_ptr<SoraConnection> CreateConnection(
      const std::string& signaling_url,
      const std::string& role,
      const std::string& channel_id,
      const std::string& client_id,
      const nb::handle& metadata,
      SoraTrackInterface* audio_source,
      SoraTrackInterface* video_source,
      bool audio,
      bool video,
      const std::string& audio_codec_type,
      const std::string& video_codec_type,
      const nb::handle& data_channels,
      std::optional<bool> data_channel_signaling,
      std::optional<bool> ignore_disconnect_websocket);

  SoraAudioSource* CreateAudioSource(size_t channels, int sample_rate);
  SoraVideoSource* CreateVideoSource();

 private:
  boost::json::value ConvertJsonValue(nb::handle value,
                                      const char* error_message);
  std::vector<sora::SoraSignalingConfig::DataChannel> ConvertDataChannels(
      const nb::handle value);

  std::unique_ptr<SoraFactory> factory_;
};
#endif
