#include "sora_video_sink.h"

// WebRTC
#include <api/video/i420_buffer.h>
#include <third_party/libyuv/include/libyuv.h>

SoraVideoFrame::SoraVideoFrame(
    rtc::scoped_refptr<webrtc::I420BufferInterface> i420_data)
    : width_(i420_data->width()), height_(i420_data->height()) {
  argb_data_ = std::unique_ptr<uint8_t>(new uint8_t[width_ * height_ * 3]);
  libyuv::ConvertFromI420(
      i420_data->DataY(), i420_data->StrideY(), i420_data->DataU(),
      i420_data->StrideU(), i420_data->DataV(), i420_data->StrideV(),
      argb_data_.get(), width_ * 3, width_, height_, libyuv::FOURCC_24BG);
}

nb::ndarray<nb::numpy, uint8_t, nb::shape<nb::any, nb::any, 3>>
SoraVideoFrame::Data() {
  size_t shape[3] = {static_cast<size_t>(height_), static_cast<size_t>(width_),
                     3};
  return nb::ndarray<nb::numpy, uint8_t, nb::shape<nb::any, nb::any, 3>>(
      argb_data_.get(), 3, shape);
}

SoraVideoSinkImpl::SoraVideoSinkImpl(SoraTrackInterface* track)
    : track_(track) {
  track_->AddSubscriber(this);
  webrtc::VideoTrackInterface* video_track =
      static_cast<webrtc::VideoTrackInterface*>(track_->GetTrack().get());
  video_track->AddOrUpdateSink(this, rtc::VideoSinkWants());
}

SoraVideoSinkImpl::~SoraVideoSinkImpl() {
  Del();
}

void SoraVideoSinkImpl::Del() {
  if (track_) {
    track_->RemoveSubscriber(this);
  }
  Disposed();
}

void SoraVideoSinkImpl::Disposed() {
  if (track_ && track_->GetTrack()) {
    webrtc::VideoTrackInterface* video_track =
        static_cast<webrtc::VideoTrackInterface*>(track_->GetTrack().get());
    video_track->RemoveSink(this);
  }
  track_ = nullptr;
}

void SoraVideoSinkImpl::PubliserDisposed() {
  Disposed();
}

void SoraVideoSinkImpl::OnFrame(const webrtc::VideoFrame& frame) {
  if (frame.width() == 0 || frame.height() == 0)
    return;
  if (on_frame_) {
    rtc::scoped_refptr<webrtc::I420BufferInterface> i420_data =
        frame.video_frame_buffer()->ToI420();
    on_frame_(std::make_shared<SoraVideoFrame>(i420_data));
  }
}
