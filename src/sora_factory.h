#ifndef SORA_FACTORY_H_
#define SORA_FACTORY_H_

#include <optional>

// WebRTC
#include <api/peer_connection_interface.h>
#include <pc/connection_context.h>
#include <rtc_base/thread.h>

// Sora
#include <sora/sora_client_context.h>

class SoraFactory {
 public:
  SoraFactory(std::optional<bool> use_hardware_encoder,
              std::optional<std::string> openh264);

  rtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface>
  GetPeerConnectionFactory() const;
  rtc::scoped_refptr<webrtc::ConnectionContext> GetConnectionContext() const;
  rtc::NetworkManager* default_network_manager();
  rtc::PacketSocketFactory* default_socket_factory();

 private:
  std::shared_ptr<sora::SoraClientContext> context_;
};

#endif