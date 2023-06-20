#include "sora_connection.h"

#include <chrono>
#include <stdexcept>

// Boost
#include <boost/asio/signal_set.hpp>

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

  thread_.reset(new std::thread([this]() {
    auto guard = boost::asio::make_work_guard(*ioc_);
    ioc_->run();
  }));
}

void SoraConnection::Disconnect() {
  if (thread_) {
    // Disconnect の中で OnDisconnect が呼ばれるので GIL をリリースする
    nb::gil_scoped_release release;
    if (conn_->GetPeerConnection() != nullptr) {
      // 切断済みではない場合は切断する
      //
      // TODO(sile): ioc_ が別スレッドで動作している関係上、上のチェックでは完璧ではなくレースコンディションが存在するはず
      // レースコンディションを完全になくすためには C++ SDK 側での対応が必要なものと思われる
      // (e.g., 切断済みの場合に conn_->Disconnect() が呼ばれた場合には単に無視する仕様にする、など）
      conn_->Disconnect();
    }
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
  if (video_sender_) {
    video_sender_->SetTrack(video_source->GetTrack().get());
  }
  if (video_source_) {
    video_source_->RemoveSubscriber(this);
  }
  video_source->AddSubscriber(this);
  video_source_ = video_source;
}

bool SoraConnection::SendDataChannel(const std::string& label,
                                     nb::bytes& data) {
  return conn_->SendDataChannel(label, std::string(data.c_str(), data.size()));
}

void SoraConnection::OnSetOffer(std::string offer) {
  std::string stream_id = rtc::CreateRandomString(16);
  if (audio_source_) {
    webrtc::RTCErrorOr<rtc::scoped_refptr<webrtc::RtpSenderInterface>>
        audio_result = conn_->GetPeerConnection()->AddTrack(
            audio_source_->GetTrack(), {stream_id});
    if (audio_result.ok()) {
      audio_sender_ = audio_result.value();
    }
  }
  if (video_source_) {
    webrtc::RTCErrorOr<rtc::scoped_refptr<webrtc::RtpSenderInterface>>
        video_result = conn_->GetPeerConnection()->AddTrack(
            video_source_->GetTrack(), {stream_id});
    if (video_result.ok()) {
      video_sender_ = video_result.value();
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
    on_message_(label, nb::bytes(data.c_str(), data.size()));
  }
}

void SoraConnection::OnTrack(
    rtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) {
  if (on_track_) {
    // shared_ptr になってないのでリークする
    auto track = std::make_shared<SoraTrackInterface>(
        this, transceiver->receiver()->track());
    AddSubscriber(track.get());
    on_track_(track);
  }
}

void SoraConnection::OnRemoveTrack(
    rtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver) {}

void SoraConnection::OnDataChannel(std::string label) {
  if (on_data_channel_) {
    on_data_channel_(label);
  }
}
