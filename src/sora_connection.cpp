#include "sora_connection.h"

#include <chrono>
#include <stdexcept>

// WebRTC
#include <rtc_base/crypto_random.h>

// Sora C++ SDK
#include <sora/rtc_stats.h>

// Boost
#include <boost/asio/signal_set.hpp>

// nonobind
#include <nanobind/nanobind.h>

#include "gil.h"
#include "sora_call.h"

namespace nb = nanobind;

SoraConnection::SoraConnection(CountedPublisher* publisher,
                               boost::asio::io_context* ioc,
                               std::shared_ptr<SoraSignalingObserver> observer)
    : publisher_(publisher),
      ioc_(ioc),
      observer_(observer),
      audio_source_(nullptr),
      video_source_(nullptr) {
  publisher_->AddSubscriber(this);
}

SoraConnection::~SoraConnection() {
  Disconnect();
  Disposed();
  if (publisher_) {
    publisher_->RemoveSubscriber(this);
  }
  Disposed();
}

void SoraConnection::Disposed() {
  DisposePublisher::Disposed();
  if (video_source_) {
    video_source_->RemoveSubscriber(this);
    video_source_ = nullptr;
  }
  if (audio_source_) {
    audio_source_->RemoveSubscriber(this);
    audio_source_ = nullptr;
  }
}

void SoraConnection::PublisherDisposed() {}

void SoraConnection::Init(sora::SoraSignalingConfig& config) {
  // TODO(tnoho): 複数回の呼び出しは禁止なので、ちゃんと throw する
  config.io_context = ioc_;
  conn_ = sora::SoraSignaling::Create(config);
}

void SoraConnection::Connect() {
  if (conn_ == nullptr) {
    throw std::runtime_error(
        "Already disconnected. Please create another Sora instance to "
        "establish a new connection.");
  }

  conn_->Connect();
}

void SoraConnection::Disconnect() {
  if (conn_) {
    Disposed();
    conn_->Disconnect();
    // OnDisconnect が来るまで待つ
    {
      GILLock lock;
      on_disconnect_cv_.wait(lock,
                             [this]() -> bool { return on_disconnected_; });
    }
    // Connection から生成したものは、ここで消す
    audio_sender_ = nullptr;
    video_sender_ = nullptr;
    conn_ = nullptr;
  }
}

void SoraConnection::SetAudioTrack(nb::ref<SoraTrackInterface> audio_source) {
  // TODO(tnoho): audio_sender_ がないと意味がないので、エラーを返すようにするべき
  if (audio_sender_) {
    audio_sender_->SetTrack(audio_source->GetTrack().get());
  }
  if (audio_source_) {
    audio_source_->RemoveSubscriber(this);
    audio_source_ = nullptr;
  }
  audio_source->AddSubscriber(this);
  audio_source_ = audio_source;
}

void SoraConnection::SetVideoTrack(nb::ref<SoraTrackInterface> video_source) {
  // TODO(tnoho): video_sender_ がないと意味がないので、エラーを返すようにするべき
  if (video_sender_) {
    video_sender_->SetTrack(video_source->GetTrack().get());
  }
  if (video_source_) {
    video_source_->RemoveSubscriber(this);
    video_source_ = nullptr;
  }
  video_source->AddSubscriber(this);
  video_source_ = video_source;
}

void SoraConnection::SetAudioSenderFrameTransformer(
    SoraAudioFrameTransformer* audio_sender_frame_transformer) {
  // TODO(tnoho): audio_sender_ がないと意味がないので、エラーを返すようにするべき
  auto interface =
      audio_sender_frame_transformer->GetFrameTransformerInterface();
  if (audio_sender_) {
    audio_sender_->SetFrameTransformer(interface);
  }
  audio_sender_frame_transformer_ = interface;
}

void SoraConnection::SetVideoSenderFrameTransformer(
    SoraVideoFrameTransformer* video_sender_frame_transformer) {
  // TODO(tnoho): video_sender_ がないと意味がないので、エラーを返すようにするべき
  auto interface =
      video_sender_frame_transformer->GetFrameTransformerInterface();
  if (video_sender_) {
    video_sender_->SetFrameTransformer(interface);
  }
  video_sender_frame_transformer_ = interface;
}

bool SoraConnection::SendDataChannel(const std::string& label,
                                     nb::bytes& data) {
  return conn_->SendDataChannel(label, std::string(data.c_str(), data.size()));
}

std::string SoraConnection::GetStats() {
  auto pc = conn_->GetPeerConnection();
  if (pc == nullptr) {
    return "[]";
  }
  std::promise<std::string> stats;
  std::future<std::string> future = stats.get_future();
  gil_scoped_release release;
  pc->GetStats(
      sora::RTCStatsCallback::Create(
          [&](const rtc::scoped_refptr<const webrtc::RTCStatsReport>& report) {
            stats.set_value(report->ToJson());
          })
          .get());
  return future.get();
}

void SoraConnection::OnSetOffer(std::string offer) {
  gil_scoped_acquire acq;
  std::string stream_id = rtc::CreateRandomString(16);
  if (audio_source_) {
    webrtc::RTCErrorOr<rtc::scoped_refptr<webrtc::RtpSenderInterface>>
        audio_result = conn_->GetPeerConnection()->AddTrack(
            audio_source_->GetTrack(), {stream_id});
    if (audio_result.ok()) {
      // javascript でいう replaceTrack を実装するために webrtc::RtpSenderInterface の参照をとっておく
      audio_sender_ = audio_result.value();
      if (audio_sender_frame_transformer_) {
        audio_sender_->SetFrameTransformer(audio_sender_frame_transformer_);
      }
    }
  }
  if (video_source_) {
    webrtc::RTCErrorOr<rtc::scoped_refptr<webrtc::RtpSenderInterface>>
        video_result = conn_->GetPeerConnection()->AddTrack(
            video_source_->GetTrack(), {stream_id});
    if (video_result.ok()) {
      video_sender_ = video_result.value();
      if (video_sender_frame_transformer_) {
        video_sender_->SetFrameTransformer(video_sender_frame_transformer_);
      }
    }
  }
  if (on_set_offer_) {
    call_python(on_set_offer_, offer);
  }
}

void SoraConnection::OnDisconnect(sora::SoraSignalingErrorCode ec,
                                  std::string message) {
  gil_scoped_acquire acq;
  if (on_disconnect_) {
    call_python(on_disconnect_, ec, message);
  }
  on_disconnected_ = true;
  on_disconnect_cv_.notify_all();
}

void SoraConnection::OnNotify(std::string text) {
  gil_scoped_acquire acq;
  if (on_notify_) {
    call_python(on_notify_, text);
  }
}

void SoraConnection::OnPush(std::string text) {
  if (on_push_) {
    call_python(on_push_, text);
  }
}

void SoraConnection::OnMessage(std::string label, std::string data) {
  gil_scoped_acquire acq;
  if (on_message_) {
    call_python(on_message_, label, nb::bytes(data.c_str(), data.size()));
  }
}

void SoraConnection::OnRpc(std::string data) {
  gil_scoped_acquire acq;
  if (on_rpc_) {
    call_python(on_rpc_, nb::bytes(data.c_str(), data.size()));
  }
}

void SoraConnection::OnSwitched(std::string text) {
  gil_scoped_acquire acq;
  if (on_switched_) {
    call_python(on_switched_, text);
  }
}

void SoraConnection::OnSignalingMessage(sora::SoraSignalingType type,
                                        sora::SoraSignalingDirection direction,
                                        std::string message) {
  gil_scoped_acquire acq;
  if (on_signaling_message_) {
    call_python(on_signaling_message_, type, direction, message);
  }
}

void SoraConnection::OnWsClose(uint16_t code, std::string message) {
  gil_scoped_acquire acq;
  if (on_ws_close_) {
    call_python(on_ws_close_, code, message);
  }
}

void SoraConnection::OnTrack(
    rtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) {
  gil_scoped_acquire acq;
  if (on_track_) {
    auto receiver = transceiver->receiver();
    nb::ref<SoraMediaTrack> track = new SoraMediaTrack(this, receiver);
    call_python(on_track_, track);
  }
}

void SoraConnection::OnRemoveTrack(
    rtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver) {
  gil_scoped_acquire acq;
  // TODO(tnoho): 要実装
}

void SoraConnection::OnDataChannel(std::string label) {
  gil_scoped_acquire acq;
  if (on_data_channel_) {
    call_python(on_data_channel_, label);
  }
}
