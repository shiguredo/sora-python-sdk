#include "sora_connection.h"

#include <chrono>
#include <stdexcept>

// WebRTC
#include <rtc_base/crypto_random.h>

// Sora C++ SDK
#include <sora/rtc_stats.h>

// Boost
#include <boost/asio/signal_set.hpp>

// WebRTC
#include <rtc_base/crypto_random.h>

// nonobind
#include <nanobind/nanobind.h>

namespace nb = nanobind;

SoraConnection::SoraConnection(DisposePublisher* publisher)
    : publisher_(publisher) {
  publisher_->AddSubscriber(this);
}

SoraConnection::~SoraConnection() {
  if (publisher_) {
    publisher_->RemoveSubscriber(this);
  }
  Disposed();
}

void SoraConnection::Disposed() {
  DisposePublisher::Disposed();
  Disconnect();
  publisher_ = nullptr;
}

void SoraConnection::PublisherDisposed() {
  Disposed();
}

void SoraConnection::Init(sora::SoraSignalingConfig& config) {
  // TODO(tnoho): 複数回の呼び出しは禁止なので、ちゃんと throw する
  ioc_.reset(new boost::asio::io_context(1));
  config.io_context = ioc_.get();
  conn_ = sora::SoraSignaling::Create(config);
}

void SoraConnection::Connect() {
  if (thread_ != nullptr) {
    throw std::runtime_error("Already connected");
  }
  if (conn_ == nullptr) {
    throw std::runtime_error(
        "Already disconnected. Please create another Sora instance to "
        "establish a new connection.");
  }

  conn_->Connect();

  // ioc_->run(); は別スレッドで呼ばなければ、この関数は切断されるまで返らなくなってしまう
  thread_.reset(new std::thread([this]() {
    auto guard = boost::asio::make_work_guard(*ioc_);
    ioc_->run();
  }));
}

void SoraConnection::Disconnect() {
  if (thread_) {
    // Disconnect の中で OnDisconnect が呼ばれるので GIL をリリースする
    nb::gil_scoped_release release;
    conn_->Disconnect();
    thread_->join();
    thread_ = nullptr;
  }
  // Connection から生成したものは、ここで消す
  audio_sender_ = nullptr;
  video_sender_ = nullptr;
  conn_ = nullptr;

  // ここで nullptr を設定しておかないと、シグナリング URL に不正な値を指定した場合に、
  // 切断後に何故か SIGSEGV が発生する（macOS 以外の OS で発生するかどうかは不明）
  ioc_ = nullptr;
}

void SoraConnection::SetAudioTrack(SoraTrackInterface* audio_source) {
  // TODO(tnoho): audio_sender_ がないと意味がないので、エラーを返すようにするべき
  if (audio_sender_) {
    audio_sender_->SetTrack(audio_source->GetTrack().get());
  }
  if (audio_source_) {
    audio_source_->RemoveSubscriber(this);
  }
  audio_source->AddSubscriber(this);
  audio_source_ = audio_source;
}

void SoraConnection::SetVideoTrack(SoraTrackInterface* video_source) {
  // TODO(tnoho): video_sender_ がないと意味がないので、エラーを返すようにするべき
  if (video_sender_) {
    video_sender_->SetTrack(video_source->GetTrack().get());
  }
  if (video_source_) {
    video_source_->RemoveSubscriber(this);
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
  nb::gil_scoped_release release;
  pc->GetStats(
      sora::RTCStatsCallback::Create(
          [&](const rtc::scoped_refptr<const webrtc::RTCStatsReport>& report) {
            stats.set_value(report->ToJson());
          })
          .get());
  return future.get();
}

void SoraConnection::OnSetOffer(std::string offer) {
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
    on_set_offer_(offer);
  }
}

void SoraConnection::OnDisconnect(sora::SoraSignalingErrorCode ec,
                                  std::string message) {
  ioc_->stop();
  if (on_disconnect_) {
    on_disconnect_(ec, message);
  }
}

void SoraConnection::OnNotify(std::string text) {
  if (on_notify_) {
    on_notify_(text);
  }
}

void SoraConnection::OnPush(std::string text) {
  if (on_push_) {
    on_push_(text);
  }
}

void SoraConnection::OnMessage(std::string label, std::string data) {
  if (on_message_) {
    nb::gil_scoped_acquire acq;
    on_message_(label, nb::bytes(data.c_str(), data.size()));
  }
}

void SoraConnection::OnSwitched(std::string text) {
  if (on_switched_) {
    on_switched_(text);
  }
}

void SoraConnection::OnSignalingMessage(sora::SoraSignalingType type,
                                        sora::SoraSignalingDirection direction,
                                        std::string message) {
  if (on_signaling_message_) {
    on_signaling_message_(type, direction, message);
  }
}

void SoraConnection::OnWsClose(uint16_t code, std::string message) {
  if (on_ws_close_) {
    on_ws_close_(code, message);
  }
}

void SoraConnection::OnTrack(
    rtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) {
  if (on_track_) {
    // shared_ptr になってないとリークする
    auto track = std::make_shared<SoraMediaTrack>(
        this, transceiver->receiver()->track(),
        transceiver->receiver()->stream_ids()[0]);
    AddSubscriber(track.get());
    on_track_(track);
  }
}

void SoraConnection::OnRemoveTrack(
    rtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver) {
  // TODO(tnoho): 要実装
}

void SoraConnection::OnDataChannel(std::string label) {
  if (on_data_channel_) {
    on_data_channel_(label);
  }
}
