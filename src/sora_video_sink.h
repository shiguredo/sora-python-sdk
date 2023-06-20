#ifndef SORA_VIDEO_SINK_H_
#define SORA_VIDEO_SINK_H_

#include <memory>

// nonobind
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/shared_ptr.h>

// WebRTC
#include <api/media_stream_interface.h>
#include <api/scoped_refptr.h>
#include <api/video/video_frame.h>
#include <api/video/video_sink_interface.h>

#include "sora_track_interface.h"

namespace nb = nanobind;

class SoraVideoFrame {
 public:
  SoraVideoFrame(rtc::scoped_refptr<webrtc::I420BufferInterface> i420_data);

  nb::ndarray<nb::numpy, uint8_t, nb::shape<nb::any, nb::any, 3>> Data();

 private:
  const int width_;
  const int height_;
  std::unique_ptr<uint8_t> argb_data_;
};

class SoraVideoSinkImpl : public rtc::VideoSinkInterface<webrtc::VideoFrame>,
                          public DisposeSubscriber {
 public:
  SoraVideoSinkImpl(SoraTrackInterface* track);
  ~SoraVideoSinkImpl();

  void Del();
  void Disposed();

  // rtc::VideoSinkInterface
  void OnFrame(const webrtc::VideoFrame& frame) override;

  // DisposeSubscriber
  void PublisherDisposed() override;

  // このコールバックは shared_ptr にしないとリークする
  std::function<void(std::shared_ptr<SoraVideoFrame>)> on_frame_;

 private:
  SoraTrackInterface* track_;
};

#endif