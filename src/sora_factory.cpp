#include "sora_factory.h"

// Boost
#include <boost/dll/runtime_symbol_info.hpp>

// WebRTC
#include <api/create_peerconnection_factory.h>
#include <api/environment/environment_factory.h>
#include <api/rtc_event_log/rtc_event_log_factory.h>
#include <api/task_queue/default_task_queue_factory.h>
#include <media/engine/webrtc_media_engine.h>
#include <rtc_base/ssl_adapter.h>

// Sora
#include <sora/audio_device_module.h>
#include <sora/sora_peer_connection_factory.h>
#include <sora/sora_video_decoder_factory.h>
#include <sora/sora_video_encoder_factory.h>

#include "dummy_audio_mixer.h"
#ifndef _WIN32
#include "dynamic_h264_decoder.h"
#include "dynamic_h264_encoder.h"
#endif

#include <exception>
#include <iostream>

#include <exception>
#include <iostream>

SoraFactory::SoraFactory(
    std::optional<std::string> openh264,
    std::optional<sora::VideoCodecPreference> video_codec_preference) {
  sora::SoraClientContextConfig context_config;
  context_config.video_codec_factory_config.capability_config.openh264_path =
      openh264;
  if (sora::CudaContext::CanCreate()) {
    context_config.video_codec_factory_config.capability_config.cuda_context =
        sora::CudaContext::Create();
  }
  if (sora::AMFContext::CanCreate()) {
    context_config.video_codec_factory_config.capability_config.amf_context =
        sora::AMFContext::Create();
  }

  // Audio デバイスは使わない、 use_audio_device を true にしただけでデバイスを掴んでしまうので常に false
  context_config.use_audio_device = false;
  context_config.configure_dependencies =
      [openh264](webrtc::PeerConnectionFactoryDependencies& dependencies) {
        // 通常の AudioMixer を使うと use_audio_device が false のとき、音声のループは全て止まってしまうので自前の AudioMixer を使う
        dependencies.audio_mixer =
            DummyAudioMixer::Create(dependencies.task_queue_factory.get());
        // アンチエコーやゲインコントロール、ノイズサプレッションが必要になる用途は想定していないため nullptr
        dependencies.audio_processing = nullptr;
      };
  context_ = sora::SoraClientContext::Create(context_config);
  if (context_ == nullptr) {
    throw std::exception();
  }
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