#include "sora_video_sink.h"

#include <thread>

// WebRTC
#include <api/environment/environment_factory.h>
#include <api/task_queue/task_queue_factory.h>
#include <api/video/i420_buffer.h>
#include <third_party/libyuv/include/libyuv.h>

SoraVideoFrame::SoraVideoFrame(
    rtc::scoped_refptr<webrtc::I420BufferInterface> i420_data)
    : width_(i420_data->width()), height_(i420_data->height()) {
  /**
   * データを取り出す際に Python 側で自由に FourCC を指定できる形にするのも手ですが、
   * その場合は関数を呼び出すたびに変換が走るので GIL を長く保持してしまいます。
   * また、複数回呼び出された際に毎回変換を行いパフォーマンスが悪化してしまうので、
   * ここで numpy の形式である 24BG に変換することとしました。
   */
  argb_data_ = std::unique_ptr<uint8_t>(new uint8_t[width_ * height_ * 3]);
  libyuv::ConvertFromI420(
      i420_data->DataY(), i420_data->StrideY(), i420_data->DataU(),
      i420_data->StrideU(), i420_data->DataV(), i420_data->StrideV(),
      argb_data_.get(), width_ * 3, width_, height_, libyuv::FOURCC_24BG);
}

nb::ndarray<nb::numpy, uint8_t, nb::shape<-1, -1, 3>> SoraVideoFrame::Data() {
  size_t shape[3] = {static_cast<size_t>(height_), static_cast<size_t>(width_),
                     3};
  return nb::ndarray<nb::numpy, uint8_t, nb::shape<-1, -1, 3>>(
      argb_data_.get(), 3, shape, nb::handle());
}

SoraVideoSinkImpl::SoraVideoSinkImpl(SoraTrackInterface* track)
    : SoraVideoSinkImpl(webrtc::CreateEnvironment(), track) {}

SoraVideoSinkImpl::SoraVideoSinkImpl(const webrtc::Environment& env,
                                     SoraTrackInterface* track)
    : track_(track) {
  on_frame_queue_ = env.task_queue_factory().CreateTaskQueue(
      "OnFrameQueue", webrtc::TaskQueueFactory::Priority::NORMAL);

  track_->AddSubscriber(this);
  webrtc::VideoTrackInterface* video_track =
      static_cast<webrtc::VideoTrackInterface*>(track_->GetTrack().get());
  // video_track にこの Sink を追加し OnFrame を呼び出してもらいます。
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
    // video_track からこの Sink を削除します。
    video_track->RemoveSink(this);
  }
  track_ = nullptr;
}

void SoraVideoSinkImpl::PublisherDisposed() {
  Disposed();
}

void SoraVideoSinkImpl::OnFrame(const webrtc::VideoFrame& frame) {
  if (frame.width() == 0 || frame.height() == 0)
    return;
  // ここで GIL を獲得しようとするとデッドロックが発生する。
  // 具体的には以下のようになる。
  //
  // IO スレッド - on_track で GIL 獲得し、オブジェクト削除のために video_track->RemoveSink() を Signaling スレッドへの Proxy 経由で呼び出し、Signaling スレッドの処理完了待ち
  // Signaling スレッド - rtc::VideoBroadcaster::RemoveSink() でオブジェクトロック獲得待ち
  // VideoStream スレッド - rtc::VideoBroadcaster::OnFrame() でオブジェクトロック獲得し、on_frame 内で GIL 獲得待ち
  //
  // つまり VideoStream スレッドが rtc::VideoBroadcaster のオブジェクトロック獲得 → GIL 獲得という順序なのに対し、
  // IO スレッドと Signaling スレッドが GIL 獲得 → rtc::VideoBroadcaster のオブジェクトロック獲得という順序でロックをしているため
  // デッドロックが発生している。
  //
  // これを解決するため、ここの OnFrame ではフレームをキューに詰めるだけにして、
  // ワーカースレッドで改めて GIL を獲得してから on_frame_ を呼び出すようにした。
  on_frame_queue_->PostTask([this, frame]() {
    nb::gil_scoped_acquire acq;
    if (on_frame_) {
      /**
       * 形式を問わず I420 でフレームデータを取得している。
       * 特殊なコーデックを選択しない限りはデコードされたフレームデータは I420 の形式になっているはずなので問題ないと考えた。
       * webrtc::VideoFrame を継承した特殊なフレームであったとしても ToI420 は実装されているはず。
       */
      rtc::scoped_refptr<webrtc::I420BufferInterface> i420_data =
          frame.video_frame_buffer()->ToI420();
      on_frame_(std::make_shared<SoraVideoFrame>(i420_data));
    }
  });
}
