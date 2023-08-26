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

/**
 * Sora からのフレームを格納する SoraVideoFrame です。
 * 
 * on_frame_ コールバックで直接フレームデータの ndarray を返してしまうとメモリーリークしてしまうため、
 * フレームデータを Python で適切にハンドリングできるようにするために用意しました。
 */
class SoraVideoFrame {
 public:
  SoraVideoFrame(rtc::scoped_refptr<webrtc::I420BufferInterface> i420_data);

  /**
   * SoraVideoFrame 内のフレームデータへの numpy.ndarray での参照を渡します。
   * 
   * @return NumPy の配列 numpy.ndarray で H x W x BGR になっているフレームデータ
   */
  nb::ndarray<nb::numpy, uint8_t, nb::shape<nb::any, nb::any, 3>> Data();

 private:
  // width や height は ndarray に情報として含まれるため、これらを別で返す関数は不要
  const int width_;
  const int height_;
  std::unique_ptr<uint8_t> argb_data_;
};

/**
 * Sora からの映像を受け取る SoraVideoSinkImpl です。
 * 
 * Connection の OnTrack コールバックから渡されるリモート Track から映像を取り出すことができます。
 * 実装上の留意点：Track の参照保持のための Impl のない SoraVideoSink を __init__.py に定義しています。
 * SoraVideoSinkImpl を直接 Python から呼び出すことは想定していません。
 */
class SoraVideoSinkImpl : public rtc::VideoSinkInterface<webrtc::VideoFrame>,
                          public DisposeSubscriber {
 public:
  /**
   * @param track 映像を取り出す OnTrack コールバックから渡されるリモート Track
   */
  SoraVideoSinkImpl(SoraTrackInterface* track);
  ~SoraVideoSinkImpl();

  void Del();
  void Disposed();

  /**
   * VideoTrack からフレームデータが来るたびに呼び出される関数です。
   * 
   * 継承している rtc::VideoSinkInterface で定義されています。
   * 
   * @param frame VideoTrack から渡されるフレームデータ
   */
  void OnFrame(const webrtc::VideoFrame& frame) override;

  // DisposeSubscriber
  void PublisherDisposed() override;

  /**
   * フレームデータが来るたびに呼び出されるコールバック変数です。
   * 
   * フレームが受信される度に呼び出されます。
   * このコールバック関数内では重い処理は行わないでください。サンプルを参考に queue を利用するなどの対応を推奨します。
   * また、この関数はメインスレッドから呼び出されないため、関数内で cv2.imshow を実行しても macOS の場合は表示されません。
   * 実装上の留意点：このコールバックで渡す引数は shared_ptr にしておかないとリークします。
   */
  std::function<void(std::shared_ptr<SoraVideoFrame>)> on_frame_;

 private:
  SoraTrackInterface* track_;
};

#endif