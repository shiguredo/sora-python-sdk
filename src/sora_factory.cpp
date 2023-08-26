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
#ifndef _WIN32
#include "dynamic_h264_decoder.h"
#include "dynamic_h264_encoder.h"
#endif

SoraFactory::SoraFactory(std::optional<bool> use_hardware_encoder,
                         std::optional<std::string> openh264) {
  // Lyra のモデルファイルを読み込むため SORA_LYRA_MODEL_COEFFS_PATH が設定されていない場合は
  // この共有ライブラリ直下に配置されているモデルファイルを利用する
  auto path = boost::dll::this_line_location().parent_path() / "model_coeffs";
#ifdef _WIN32
  _putenv_s("SORA_LYRA_MODEL_COEFFS_PATH", path.string().c_str());
#else
  setenv("SORA_LYRA_MODEL_COEFFS_PATH", path.string().c_str(), 0);
#endif

  sora::SoraClientContextConfig context_config;
  // Audio デバイスは使わない、 use_audio_device を true にしただけでデバイスを掴んでしまうので常に false
  context_config.use_audio_device = false;
  if (use_hardware_encoder) {
    context_config.use_hardware_encoder = *use_hardware_encoder;
  }
  context_config.configure_media_dependencies =
      [use_hardware_encoder = context_config.use_hardware_encoder, openh264](
          const webrtc::PeerConnectionFactoryDependencies& dependencies,
          cricket::MediaEngineDependencies& media_dependencies) {
        // 通常の AudioMixer を使うと use_audio_device が false のとき、音声のループは全て止まってしまうので自前の AudioMixer を使う
        media_dependencies.audio_mixer =
            DummyAudioMixer::Create(media_dependencies.task_queue_factory);
        // アンチエコーやゲインコントロール、ノイズサプレッションが必要になる用途は想定していないため nullptr
        media_dependencies.audio_processing = nullptr;

#ifndef _WIN32
        if (openh264) {
          {
            auto config =
                use_hardware_encoder
                    ? sora::GetDefaultVideoEncoderFactoryConfig()
                    : sora::GetSoftwareOnlyVideoEncoderFactoryConfig();
            config.use_simulcast_adapter = true;
            config.encoders.insert(
                config.encoders.begin(),
                sora::VideoEncoderConfig(
                    webrtc::kVideoCodecH264,
                    [openh264 = openh264](
                        auto format) -> std::unique_ptr<webrtc::VideoEncoder> {
                      return webrtc::DynamicH264Encoder::Create(
                          cricket::VideoCodec(format), *openh264);
                    }));
            media_dependencies.video_encoder_factory =
                absl::make_unique<sora::SoraVideoEncoderFactory>(
                    std::move(config));
          }
          {
            auto config =
                use_hardware_encoder
                    ? sora::GetDefaultVideoDecoderFactoryConfig()
                    : sora::GetSoftwareOnlyVideoDecoderFactoryConfig();
            config.decoders.insert(
                config.decoders.begin(),
                sora::VideoDecoderConfig(
                    webrtc::kVideoCodecH264,
                    [openh264 = openh264](
                        auto format) -> std::unique_ptr<webrtc::VideoDecoder> {
                      return webrtc::DynamicH264Decoder::Create(*openh264);
                    }));
            media_dependencies.video_decoder_factory =
                absl::make_unique<sora::SoraVideoDecoderFactory>(
                    std::move(config));
          }
        }
#endif
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

rtc::NetworkManager* SoraFactory::default_network_manager() {
  return context_->signaling_thread()->BlockingCall([this]() {
    return context_->connection_context()->default_network_manager();
  });
}
rtc::PacketSocketFactory* SoraFactory::default_socket_factory() {
  return context_->signaling_thread()->BlockingCall([this]() {
    return context_->connection_context()->default_socket_factory();
  });
}