#ifndef SORA_TRACK_INTERFACE_H_
#define SORA_TRACK_INTERFACE_H_

// WebRTC
#include <api/media_stream_interface.h>
#include <api/scoped_refptr.h>

#include "dispose_listener.h"

/**
 * webrtc::MediaStreamTrackInterface を格納する SoraTrackInterface です。
 * 
 * webrtc::MediaStreamTrackInterface は rtc::scoped_refptr なので、
 * nanobind で直接のハンドリングが難しいので用意しました。
 */
class SoraTrackInterface : public DisposePublisher, public DisposeSubscriber {
 public:
  SoraTrackInterface(
      DisposePublisher* publisher,
      rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track)
      : publisher_(publisher), track_(track) {}
  virtual ~SoraTrackInterface() {
    if (publisher_) {
      publisher_->RemoveSubscriber(this);
    }
    Disposed();
  }

  /**
   * Python で呼び出すための関数
   * この実装では track_ が nullptr になっているとクラッシュしてしまいますが、
   * その時には publisher_ も失われているため許容することとしました。
   */
  std::string kind() const { return track_->kind(); }
  std::string id() const { return track_->id(); }
  bool enabled() const { return track_->enabled(); }
  bool set_enabled(bool enable) { return track_->set_enabled(enable); }
  webrtc::MediaStreamTrackInterface::TrackState state() {
    return track_->state();
  }

  /**
   * webrtc::MediaStreamTrackInterface の実体を取り出すため Python SDK 内で使う関数です。
   * 
   * @return rtc::scoped_refptr<webrtc::MediaStreamTrackInterface>
   */
  rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> GetTrack() {
    return track_;
  }

  virtual void Disposed() override {
    DisposePublisher::Disposed();
    publisher_ = nullptr;
    track_ = nullptr;
  }
  virtual void PublisherDisposed() override {
    // Track は生成元が破棄された後に再利用することはないので Disposed() を呼ぶ
    Disposed();
  }

 protected:
  DisposePublisher* publisher_;
  rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track_;
};

/**
 * SoraConnection の on_track で渡されるリモートトラックを格納する SoraTrackInterface です。
 * 
 * webrtc::MediaStreamTrackInterface のメンバーにはない stream_id を on_track で渡すために追加しました。
 */
class SoraMediaTrack : public SoraTrackInterface {
 public:
  SoraMediaTrack(DisposePublisher* publisher,
                 rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track,
                 std::string stream_id)
      : SoraTrackInterface(publisher, track), stream_id_(stream_id) {}

  /**
   * この Track の Stream ID を std::string で返します。
   * 
   * Python で呼び出すための関数です。
   * 本来 Track には複数の Stream ID を紐づけることができるのですが、
   * Sora の使用上 Track には Stream ID が 1 つしか紐づかないため Track のメンバーとしました。
   */
  std::string stream_id() const { return stream_id_; }

 private:
  std::string stream_id_;
};
#endif