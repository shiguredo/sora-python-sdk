#ifndef SORA_FACTORY_H_
#define SORA_FACTORY_H_

// WebRTC
#include <api/peer_connection_interface.h>
#include <pc/connection_context.h>
#include <rtc_base/thread.h>

// Sora
#include <sora/sora_client_context.h>

class SoraFactory {
 public:
  SoraFactory(bool use_hardware_encoder);

  rtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface>
  GetPeerConnectionFactory() const;
  rtc::scoped_refptr<webrtc::ConnectionContext> GetConnectionContext() const;

 private:
  std::shared_ptr<sora::SoraClientContext> context_;
};

#endif