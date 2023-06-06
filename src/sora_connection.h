#ifndef SORA_CONNECTION_H_
#define SORA_CONNECTION_H_

#include <memory>
#include <thread>

// nonobind
#include <nanobind/nanobind.h>
#include <nanobind/stl/shared_ptr.h>

// Boost
#include <boost/asio/io_context.hpp>

// WebRTC
#include <api/media_stream_interface.h>
#include <api/rtp_sender_interface.h>

// Sora
#include <sora/sora_signaling.h>

#include "dispose_listener.h"
#include "sora_track_interface.h"

namespace nb = nanobind;

class SoraConnection : public sora::SoraSignalingObserver,
                       public DisposePublisher,
                       public DisposeSubscriber {
 public:
  SoraConnection(DisposePublisher* publisher);
  ~SoraConnection();

  void Disposed() override;
  void PubliserDisposed() override;

  void Init(sora::SoraSignalingConfig& config);
  void Connect();
  void Disconnect();
  void SetAudioTrack(SoraTrackInterface* audio_source);
  void SetVideoTrack(SoraTrackInterface* video_source);
  bool SendDataChannel(const std::string& label, nb::bytes& data);

  // sora::SoraSignalingObserver
  void OnSetOffer(std::string offer) override;
  void OnDisconnect(sora::SoraSignalingErrorCode ec,
                    std::string message) override;
  void OnNotify(std::string text) override;
  void OnPush(std::string text) override;
  void OnMessage(std::string label, std::string data) override;
  void OnTrack(
      rtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) override;
  void OnRemoveTrack(
      rtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver) override;
  void OnDataChannel(std::string label) override;

  std::function<void(std::string)> on_set_offer_;
  std::function<void(sora::SoraSignalingErrorCode, std::string)> on_disconnect_;
  std::function<void(std::string)> on_notify_;
  std::function<void(std::string)> on_push_;
  std::function<void(std::string, nb::bytes)> on_message_;
  std::function<void(std::shared_ptr<SoraTrackInterface>)> on_track_;
  std::function<void(std::string)> on_data_channel_;

 private:
  DisposePublisher* publisher_;
  std::unique_ptr<boost::asio::io_context> ioc_;
  std::shared_ptr<sora::SoraSignaling> conn_;
  std::unique_ptr<std::thread> thread_;
  SoraTrackInterface* audio_source_;
  SoraTrackInterface* video_source_;
  rtc::scoped_refptr<webrtc::RtpSenderInterface> audio_sender_;
  rtc::scoped_refptr<webrtc::RtpSenderInterface> video_sender_;
};

#endif
