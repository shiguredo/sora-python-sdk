#ifndef SORA_FACTORY_H_
#define SORA_FACTORY_H_

#include <optional>

// WebRTC
#include <api/peer_connection_interface.h>
#include <pc/connection_context.h>
#include <rtc_base/thread.h>

// Sora
#include <sora/sora_client_context.h>

/**
 * sora::SoraClientContext を呼び出す必要がある処理をまとめたクラスです。
 */
class SoraFactory {
 public:
  SoraFactory(std::optional<std::string> openh264,
              std::optional<sora::VideoCodecPreference> video_codec_preference);

  webrtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface>
  GetPeerConnectionFactory() const;
  webrtc::scoped_refptr<webrtc::ConnectionContext> GetConnectionContext() const;
  webrtc::NetworkManager* default_network_manager();
  webrtc::PacketSocketFactory* default_socket_factory();

 private:
  std::shared_ptr<sora::SoraClientContext> context_;
};

#endif