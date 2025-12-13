#include "sora_video_sink.h"

// WebRTC
#include <api/environment/environment_factory.h>
#include <api/task_queue/task_queue_factory.h>
#include <api/video/i420_buffer.h>
#include <third_party/libyuv/include/libyuv.h>

#include "gil.h"
#include "sora_call.h"

SoraVideoFrame::SoraVideoFrame(
    webrtc::scoped_refptr<webrtc::I420BufferInterface> i420_buffer)
    : width_(i420_buffer->width()),
      height_(i420_buffer->height()),
      i420_buffer_(i420_buffer),
      bgr_converted_(false) {
  // I420 バッファの参照を保持するだけで、変換は遅延実行する
}

nb::ndarray<nb::numpy, uint8_t, nb::shape<-1, -1, 3>> SoraVideoFrame::Data() {
  if (!bgr_converted_) {
    /**
     * データを取り出す際に Python 側で自由に FourCC を指定できる形にするのも手ですが、
     * その場合は関数を呼び出すたびに変換が走るので GIL を長く保持してしまいます。
     * また、複数回呼び出された際に毎回変換を行いパフォーマンスが悪化してしまうので、
     * ここで numpy の形式である 24BG に変換することとしました。
     */
    bgr_data_ = std::make_unique<uint8_t[]>(width_ * height_ * 3);
    libyuv::ConvertFromI420(
        i420_buffer_->DataY(), i420_buffer_->StrideY(), i420_buffer_->DataU(),
        i420_buffer_->StrideU(), i420_buffer_->DataV(), i420_buffer_->StrideV(),
        bgr_data_.get(), width_ * 3, width_, height_, libyuv::FOURCC_24BG);
    bgr_converted_ = true;
  }
  size_t shape[3] = {static_cast<size_t>(height_), static_cast<size_t>(width_),
                     3};
  return nb::ndarray<nb::numpy, uint8_t, nb::shape<-1, -1, 3>>(
      bgr_data_.get(), 3, shape, nb::handle());
}

nb::tuple SoraVideoFrame::Planes() {
  int uv_width = width_ / 2;
  int uv_height = height_ / 2;

  // Y プレーン（stride 付き）
  size_t y_shape[2] = {static_cast<size_t>(height_),
                       static_cast<size_t>(width_)};
  int64_t y_strides[2] = {i420_buffer_->StrideY(), 1};
  auto y_plane = nb::ndarray<nb::numpy, uint8_t>(
      const_cast<uint8_t*>(i420_buffer_->DataY()), 2, y_shape, nb::handle(),
      y_strides);

  // U プレーン（stride 付き）
  size_t uv_shape[2] = {static_cast<size_t>(uv_height),
                        static_cast<size_t>(uv_width)};
  int64_t u_strides[2] = {i420_buffer_->StrideU(), 1};
  auto u_plane = nb::ndarray<nb::numpy, uint8_t>(
      const_cast<uint8_t*>(i420_buffer_->DataU()), 2, uv_shape, nb::handle(),
      u_strides);

  // V プレーン（stride 付き）
  int64_t v_strides[2] = {i420_buffer_->StrideV(), 1};
  auto v_plane = nb::ndarray<nb::numpy, uint8_t>(
      const_cast<uint8_t*>(i420_buffer_->DataV()), 2, uv_shape, nb::handle(),
      v_strides);

  return nb::make_tuple(y_plane, u_plane, v_plane);
}

SoraVideoSinkImpl::SoraVideoSinkImpl(nb::ref<SoraTrackInterface> track)
    : SoraVideoSinkImpl(webrtc::CreateEnvironment(), track) {}

SoraVideoSinkImpl::SoraVideoSinkImpl(const webrtc::Environment& env,
                                     nb::ref<SoraTrackInterface> track)
    : track_(track) {
  on_frame_queue_ = env.task_queue_factory().CreateTaskQueue(
      "OnFrameQueue", webrtc::TaskQueueFactory::Priority::NORMAL);

  track_->AddSubscriber(this);
  webrtc::VideoTrackInterface* video_track =
      static_cast<webrtc::VideoTrackInterface*>(track_->GetTrack().get());
  // video_track にこの Sink を追加し OnFrame を呼び出してもらいます。
  video_track->AddOrUpdateSink(this, webrtc::VideoSinkWants());
}

SoraVideoSinkImpl::~SoraVideoSinkImpl() {
  Del();

  // OnFrameQueue スレッドの join 待ちでデッドロックしてしまうので、ここで GIL を解放する
  // 具体的には、以下の順序で実行された時にデッドロックする。
  //
  // 1. このスレッドで、GIL を獲得した状態でデストラクタが呼ばれる
  // 2. OnFrameQueue スレッドで、OnFrameQueue スレッドから OnFrame のタスクが上がってくる → GIL 獲得待ち
  // 3. このスレッドで、TaskQueueBase デストラクタ呼び出しで OnFrameQueue スレッドに終了依頼を出す → OnFrameQueue の終了待ち
  gil_scoped_release release;
  on_frame_queue_.reset();
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
  on_frame_ = nullptr;
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
    gil_scoped_acquire acq;
    if (on_frame_) {
      /**
       * 形式を問わず I420 でフレームデータを取得している。
       * 特殊なコーデックを選択しない限りはデコードされたフレームデータは I420 の形式になっているはずなので問題ないと考えた。
       * webrtc::VideoFrame を継承した特殊なフレームであったとしても ToI420 は実装されているはず。
       */
      webrtc::scoped_refptr<webrtc::I420BufferInterface> i420_data =
          frame.video_frame_buffer()->ToI420();
      call_python(on_frame_, std::make_shared<SoraVideoFrame>(i420_data));
    }
  });
}
