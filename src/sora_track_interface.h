#ifndef SORA_TRACK_INTERFACE_H_
#define SORA_TRACK_INTERFACE_H_

// WebRTC
#include <api/media_stream_interface.h>
#include <api/scoped_refptr.h>

#include "dispose_listener.h"

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

  std::string kind() const { return track_->kind(); }
  std::string id() const { return track_->id(); }
  bool enabled() const { return track_->enabled(); }
  bool set_enabled(bool enable) { return track_->set_enabled(enable); }
  webrtc::MediaStreamTrackInterface::TrackState state() {
    return track_->state();
  }
  rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> GetTrack() {
    return track_;
  }

  virtual void Disposed() override {
    DisposePublisher::Disposed();
    publisher_ = nullptr;
    track_ = nullptr;
  }
  virtual void PublisherDisposed() override { Disposed(); }

 protected:
  DisposePublisher* publisher_;
  rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track_;
};

#endif