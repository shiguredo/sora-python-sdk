#ifndef SORA_VIDEO_SOURCE_H_
#define SORA_VIDEO_SOURCE_H_

#include <condition_variable>
#include <memory>
#include <mutex>
#include <queue>
#include <thread>

// nonobind
#include <nanobind/ndarray.h>

// WebRTC
#include <api/peer_connection_interface.h>
#include <api/scoped_refptr.h>

// Sora
#include <sora/scalable_track_source.h>

#include "sora_connection.h"
#include "sora_track_interface.h"

namespace nb = nanobind;

class SoraVideoSource : public SoraTrackInterface {
 public:
  SoraVideoSource(DisposePublisher* publisher,
                  rtc::scoped_refptr<sora::ScalableVideoTrackSource> source,
                  rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track);

  void Disposed() override;
  void PublisherDisposed() override;
  void OnCaptured(nb::ndarray<uint8_t,
                              nb::shape<nb::any, nb::any, 3>,
                              nb::c_contig,
                              nb::device::cpu> ndarray);
  void OnCaptured(nb::ndarray<uint8_t,
                              nb::shape<nb::any, nb::any, 3>,
                              nb::c_contig,
                              nb::device::cpu> ndarray,
                  double timestamp);
  void OnCaptured(nb::ndarray<uint8_t,
                              nb::shape<nb::any, nb::any, 3>,
                              nb::c_contig,
                              nb::device::cpu> ndarray,
                  int64_t timestamp_us);

 private:
  struct Frame {
    Frame(std::unique_ptr<uint8_t> d, int w, int h, int64_t t)
        : data(std::move(d)), width(w), height(h), timestamp_us(t) {}

    const std::unique_ptr<uint8_t> data;
    const int32_t width;
    const int32_t height;
    const int64_t timestamp_us;
  };

  bool SendFrameProcess();
  bool SendFrame(const uint8_t* argb_data,
                 const int width,
                 const int height,
                 const int64_t timestamp_us);

  const int kMsToRtpTimestamp = 90;
  rtc::scoped_refptr<sora::ScalableVideoTrackSource> source_;
  std::unique_ptr<std::thread> thread_;
  std::mutex queue_mtx_;
  std::condition_variable queue_cond_;
  std::queue<std::unique_ptr<Frame>> queue_;
  bool finished_;
};

#endif