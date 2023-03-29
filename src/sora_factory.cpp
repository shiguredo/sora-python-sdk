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
  setenv("SORA_LYRA_MODEL_COEFFS_PATH", path.string().c_str(), 0);

  rtc::InitializeSSL();

  network_thread_ = rtc::Thread::CreateWithSocketServer();
  network_thread_->Start();
  worker_thread_ = rtc::Thread::Create();
  worker_thread_->Start();
  signaling_thread_ = rtc::Thread::Create();
  signaling_thread_->Start();

  webrtc::PeerConnectionFactoryDependencies dependencies;
  dependencies.network_thread = network_thread_.get();
  dependencies.worker_thread = worker_thread_.get();
  dependencies.signaling_thread = signaling_thread_.get();
  dependencies.task_queue_factory = webrtc::CreateDefaultTaskQueueFactory();
  dependencies.call_factory = webrtc::CreateCallFactory();
  dependencies.event_log_factory =
      absl::make_unique<webrtc::RtcEventLogFactory>(
          dependencies.task_queue_factory.get());

  // media_dependencies
  cricket::MediaEngineDependencies media_dependencies;
  media_dependencies.task_queue_factory = dependencies.task_queue_factory.get();
  media_dependencies.adm = worker_thread_->BlockingCall([&] {
    sora::AudioDeviceModuleConfig config;
    config.audio_layer = webrtc::AudioDeviceModule::kDummyAudio;
    config.task_queue_factory = dependencies.task_queue_factory.get();
    return sora::CreateAudioDeviceModule(config);
  });

  media_dependencies.audio_encoder_factory =
      sora::CreateBuiltinAudioEncoderFactory();
  media_dependencies.audio_decoder_factory =
      sora::CreateBuiltinAudioDecoderFactory();

  auto cuda_context = sora::CudaContext::Create();
  {
    auto config = use_hardware_encoder
                      ? sora::GetDefaultVideoEncoderFactoryConfig(cuda_context)
                      : sora::GetSoftwareOnlyVideoEncoderFactoryConfig();
    config.use_simulcast_adapter = true;
    media_dependencies.video_encoder_factory =
        absl::make_unique<sora::SoraVideoEncoderFactory>(std::move(config));
  }
  {
    auto config = use_hardware_encoder
                      ? sora::GetDefaultVideoDecoderFactoryConfig(cuda_context)
                      : sora::GetSoftwareOnlyVideoDecoderFactoryConfig();
    media_dependencies.video_decoder_factory =
        absl::make_unique<sora::SoraVideoDecoderFactory>(std::move(config));
  }

  media_dependencies.audio_mixer =
      DummyAudioMixer::Create(dependencies.task_queue_factory.get());
  media_dependencies.audio_processing = nullptr;

  dependencies.media_engine =
      cricket::CreateMediaEngine(std::move(media_dependencies));

  factory_ = sora::CreateModularPeerConnectionFactoryWithContext(
      std::move(dependencies), connection_context_);

  webrtc::PeerConnectionFactoryInterface::Options factory_options;
  factory_options.disable_encryption = false;
  factory_options.ssl_max_version = rtc::SSL_PROTOCOL_DTLS_12;
  factory_options.crypto_options.srtp.enable_gcm_crypto_suites = true;
  factory_->SetOptions(factory_options);
}

SoraFactory::~SoraFactory() {
  factory_ = nullptr;
  network_thread_->Stop();
  worker_thread_->Stop();
  signaling_thread_->Stop();

  rtc::CleanupSSL();
}

rtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface>
SoraFactory::GetPeerConnectionFactory() {
  return factory_;
};

rtc::scoped_refptr<webrtc::ConnectionContext>
SoraFactory::GetConnectionContext() {
  return connection_context_;
};