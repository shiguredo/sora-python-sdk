#include "sora_factory.h"

// Boost
#include <boost/dll/runtime_symbol_info.hpp>

// WebRTC
#include <api/create_peerconnection_factory.h>
#include <api/rtc_event_log/rtc_event_log_factory.h>
#include <api/task_queue/default_task_queue_factory.h>
#include <media/engine/webrtc_media_engine.h>
#include <rtc_base/ssl_adapter.h>

// Sora
#include <sora/audio_device_module.h>
#include <sora/sora_audio_decoder_factory.h>
#include <sora/sora_audio_encoder_factory.h>
#include <sora/sora_peer_connection_factory.h>
#include <sora/sora_video_decoder_factory.h>
#include <sora/sora_video_encoder_factory.h>

#include "dummy_audio_mixer.h"

SoraFactory::SoraFactory(bool use_hardware_encoder) {
  // Lyra のモデルファイルを読み込むため SORA_LYRA_MODEL_COEFFS_PATH が設定されていない場合は
  // この共有ライブラリ直下に配置されているモデルファイルを利用する
  auto path = boost::dll::this_line_location().parent_path() / "model_coeffs";
#ifdef _WIN32
  _putenv_s("SORA_LYRA_MODEL_COEFFS_PATH", path.string().c_str());
#else
  setenv("SORA_LYRA_MODEL_COEFFS_PATH", path.string().c_str(), 0);
#endif

  sora::SoraClientContextConfig context_config;
  context_config.use_audio_device = false;
  context_config.use_hardware_encoder = use_hardware_encoder;
  context_config.configure_media_dependencies =
      [](const webrtc::PeerConnectionFactoryDependencies& dependencies,
         cricket::MediaEngineDependencies& media_dependencies) {
        media_dependencies.audio_mixer =
            DummyAudioMixer::Create(media_dependencies.task_queue_factory);
      };
  context_ = sora::SoraClientContext::Create(context_config);
}

rtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface>
SoraFactory::GetPeerConnectionFactory() const {
  return context_->peer_connection_factory();
};

rtc::scoped_refptr<webrtc::ConnectionContext>
SoraFactory::GetConnectionContext() const {
  return context_->connection_context();
};