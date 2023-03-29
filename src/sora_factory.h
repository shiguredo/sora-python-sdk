#ifndef SORA_FACTORY_H_
#define SORA_FACTORY_H_

// WebRTC
#include <api/peer_connection_interface.h>
#include <pc/connection_context.h>
#include <rtc_base/thread.h>

class SoraFactory {
 public:
  SoraFactory(bool use_hardware_encoder);
  ~SoraFactory();

  rtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface>
  GetPeerConnectionFactory();
  rtc::scoped_refptr<webrtc::ConnectionContext> GetConnectionContext();

 private:
  std::unique_ptr<rtc::Thread> network_thread_;
  std::unique_ptr<rtc::Thread> worker_thread_;
  std::unique_ptr<rtc::Thread> signaling_thread_;
  rtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface> factory_;
  rtc::scoped_refptr<webrtc::ConnectionContext> connection_context_;
};
#endif