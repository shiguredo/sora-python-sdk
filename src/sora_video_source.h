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

/**
 * Sora に映像データを送る受け口である SoraVideoSource です。
 * 
 * VideoSource にフレームデータを渡すことで、 Sora に映像を送ることができます。
 * 送信時通信状況によってはフレームのリサイズやドロップが行われます。
 * VideoSource は MediaStreamTrack として振る舞うため、
 * VideoSource と同一の Sora インスタンスから生成された複数の Connection で共用できます。
 */
class SoraVideoSource : public SoraTrackInterface {
 public:
  SoraVideoSource(DisposePublisher* publisher,
                  rtc::scoped_refptr<sora::ScalableVideoTrackSource> source,
                  rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track);

  void Disposed() override;
  void PublisherDisposed() override;
  /**
   * Sora に映像データとして送るフレームを渡します。
   * 
   * この関数が呼び出された時点のタイムスタンプでフレームを送信します。
   * 映像になるように一定のタイミングで呼び出さない場合、受信側でコマ送りになります。
   * 
   * @param ndarray NumPy の配列 numpy.ndarray で H x W x BGR になっているフレームデータ
   */
  void OnCaptured(
      nb::ndarray<uint8_t, nb::shape<-1, -1, 3>, nb::c_contig, nb::device::cpu>
          ndarray);
  /**
   * Sora に映像データとして送るフレームを渡します。
   * 
   * timestamp 引数で渡されたタイムスタンプでフレームを送信します。
   * フレームのタイムスタンプを指定できるようにするため用意したオーバーロードです。
   * timestamp が映像になるように一定の時間差がない場合、受信側で正しく表示されない場合があります。
   * 表示側で音声データの timestamp と同期を取るため遅延が発生する場合があります。
   * 
   * @param ndarray NumPy の配列 numpy.ndarray で H x W x BGR になっているフレームデータ
   * @param timestamp Python の time.time() で取得できるエポック秒で表されるフレームのタイムスタンプ
   */
  void OnCaptured(
      nb::ndarray<uint8_t, nb::shape<-1, -1, 3>, nb::c_contig, nb::device::cpu>
          ndarray,
      double timestamp);
  /**
   * Sora に映像データとして送るフレームを渡します。
   * 
   * timestamp_us 引数で渡されたマイクロ秒精度の整数で表されるタイムスタンプでフレームを送信します。
   * libWebRTC のタイムスタンプはマイクロ秒精度のため用意したオーバーロードです。
   * timestamp が映像になるように一定の時間差がない場合、受信側で正しく表示されない場合があります。
   * 表示側で音声データの timestamp と同期を取るため遅延が発生する場合があります。
   * 
   * @param ndarray NumPy の配列 numpy.ndarray で H x W x BGR になっているフレームデータ
   * @param timestamp_us マイクロ秒単位の整数で表されるフレームのタイムスタンプ
   */
  void OnCaptured(
      nb::ndarray<uint8_t, nb::shape<-1, -1, 3>, nb::c_contig, nb::device::cpu>
          ndarray,
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

  rtc::scoped_refptr<sora::ScalableVideoTrackSource> source_;
  std::unique_ptr<std::thread> thread_;
  std::condition_variable_any queue_cond_;
  std::queue<std::unique_ptr<Frame>> queue_;
  bool finished_;
};

#endif