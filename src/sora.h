#ifndef SORA_H_
#define SORA_H_

#include <memory>
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
      SoraTrackInterface* video_source);

  SoraAudioSource* CreateAudioSource(size_t channels, int sample_rate);
  SoraVideoSource* CreateVideoSource();

 private:
  boost::json::value CovertJsonValue(nb::handle value);

  std::unique_ptr<SoraFactory> factory_;
};
#endif