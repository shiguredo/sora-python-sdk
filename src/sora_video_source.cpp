#include "sora_video_source.h"

// WebRTC
#include <api/video/i420_buffer.h>
#include <rtc_base/time_utils.h>
#include <third_party/libyuv/include/libyuv.h>

SoraVideoSource::SoraVideoSource(
    DisposePublisher* publisher,
    rtc::scoped_refptr<sora::ScalableVideoTrackSource> source,
    rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track)
    : SoraTrackInterface(publisher, track), source_(source), finished_(false) {
  publisher_->AddSubscriber(this);
  thread_.reset(new std::thread([this]() {
    while (SendFrameProcess()) {
    }
  }));
}

void SoraVideoSource::Disposed() {
  std::unique_lock<std::mutex> lock(queue_mtx_);
  if (!finished_) {
    finished_ = true;
    lock.unlock();
    queue_cond_.notify_all();
    nb::gil_scoped_release release;
    thread_->join();
    thread_ = nullptr;
  }
  SoraTrackInterface::Disposed();
}

void SoraVideoSource::PublisherDisposed() {
  Disposed();
}

void SoraVideoSource::OnCaptured(
    nb::ndarray<uint8_t, nb::shape<-1, -1, 3>, nb::c_contig, nb::device::cpu>
        ndarray) {
  OnCaptured(ndarray, rtc::TimeMicros());
}

void SoraVideoSource::OnCaptured(
    nb::ndarray<uint8_t, nb::shape<-1, -1, 3>, nb::c_contig, nb::device::cpu>
        ndarray,
    double timestamp) {
  OnCaptured(ndarray, (int64_t)(timestamp * 1000000));
}

void SoraVideoSource::OnCaptured(
    nb::ndarray<uint8_t, nb::shape<-1, -1, 3>, nb::c_contig, nb::device::cpu>
        ndarray,
    int64_t timestamp_us) {
  int width = ndarray.shape(1);
  int height = ndarray.shape(0);
  std::unique_ptr<uint8_t> data(new uint8_t[width * height * 3]);
  memcpy(data.get(), ndarray.data(), width * height * 3);

  {
    std::lock_guard<std::mutex> lock(queue_mtx_);
    if (finished_) {
      return;
    }
    queue_.push(
        std::make_unique<Frame>(std::move(data), width, height, timestamp_us));
  }
  queue_cond_.notify_all();
}

bool SoraVideoSource::SendFrameProcess() {
  std::unique_ptr<Frame> frame;
  {
    std::unique_lock<std::mutex> lock(queue_mtx_);
    if (queue_.empty()) {
      queue_cond_.wait(lock, [&] { return !queue_.empty() || finished_; });
    }
    if (finished_) {
      return false;
    }
    frame = std::move(queue_.front());
    queue_.pop();
  }
  if (frame) {
    SendFrame(frame->data.get(), frame->width, frame->height,
              frame->timestamp_us);
  }
  return true;
}

bool SoraVideoSource::SendFrame(const uint8_t* argb_data,
                                const int width,
                                const int height,
                                const int64_t timestamp_us) {
  rtc::scoped_refptr<webrtc::I420Buffer> i420_buffer(
      webrtc::I420Buffer::Create(width, height));
  i420_buffer->InitializeData();
  int ret = libyuv::ConvertToI420(
      argb_data, width * height * 3, i420_buffer.get()->MutableDataY(),
      i420_buffer.get()->StrideY(), i420_buffer.get()->MutableDataU(),
      i420_buffer.get()->StrideU(), i420_buffer.get()->MutableDataV(),
      i420_buffer.get()->StrideV(), 0, 0, width, height, width, height,
      libyuv::kRotate0, libyuv::FOURCC_24BG);
  if (ret != 0) {
    return false;
  }

  webrtc::VideoFrame video_frame =
      webrtc::VideoFrame::Builder()
          .set_video_frame_buffer(i420_buffer)
          .set_timestamp_us(timestamp_us)
          .set_timestamp_rtp(
              (uint32_t)(kMsToRtpTimestamp * timestamp_us / 1000))
          .set_rotation(webrtc::kVideoRotation_0)
          .build();
  source_->OnCapturedFrame(video_frame);
  return true;
}