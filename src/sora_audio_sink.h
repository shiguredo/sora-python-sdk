#ifndef SORA_AUDIO_SINK_H_
#define SORA_AUDIO_SINK_H_

#include <condition_variable>
#include <mutex>

// nonobind
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>

// WebRTC
#include <api/audio/audio_frame.h>
#include <api/media_stream_interface.h>
#include <api/scoped_refptr.h>
#include <modules/audio_coding/acm2/acm_resampler.h>
#include <rtc_base/buffer.h>

#include "sora_track_interface.h"

namespace nb = nanobind;

/**
 * Sora からの音声を受け取る SoraAudioSinkImpl です。
 * 
 * Connection の OnTrack コールバックから渡されるリモート Track から音声を取り出すことができます。
 * Track からの音声はコンストラクタで設定したサンプリングレートとチャネル数に変換し、
 * SoraAudioSinkImpl 内のバッファに溜め込まれるため、任意のタイミングで音声を取り出すことができます。
 * 実装上の留意点：Track の参照保持のための Impl のない SoraAudioSink を __init__.py に定義しています。
 * SoraAudioSinkImpl を直接 Python から呼び出すことは想定していません。
 */
class SoraAudioSinkImpl : public webrtc::AudioTrackSinkInterface,
                          public DisposeSubscriber {
 public:
  /**
   * @param track 音声を取り出す OnTrack コールバックから渡されるリモート Track
   * @param output_sample_rate 音声の出力サンプリングレート
   * @param output_channels 音声の出力チャネル数
   */
  SoraAudioSinkImpl(nb::ref<SoraTrackInterface> track,
                    int output_sample_rate,
                    size_t output_channels);
  ~SoraAudioSinkImpl();

  void Del();
  void Disposed();
  void PublisherDisposed() override;
  // webrtc::AudioTrackSinkInterface
  void OnData(const void* audio_data,
              int bits_per_sample,
              int sample_rate,
              size_t number_of_channels,
              size_t number_of_frames,
              std::optional<int64_t> absolute_capture_timestamp_ms) override;

  /**
   * 実装上の留意点：コールバックと Read 関数の共存はパフォーマンスや使い方の面で難しいことが判明したので、
   * on_data_, on_format_ ともに廃止予定です。
  */
  std::function<void(nb::ndarray<nb::numpy, int16_t, nb::shape<-1, -1>>)>
      on_data_;
  std::function<void(int, size_t)> on_format_;

  /**
   * 受信済みのデータをバッファから読み出す
   * 
   * @param frames 受け取るチャンネルごとのサンプル数。0 を指定した場合には、受信済みのすべてのサンプルを返す
   * @param timeout 溜まっているサンプル数が frames で指定した数を満たさない場合の待ち時間。秒単位の float で指定する
   * @return Tuple でインデックス 0 には成否が、成功した場合のみインデックス 1 には NumPy の配列 numpy.ndarray で チャンネルごとのサンプル数 x チャンネル数 になっている音声データ
   */
  nb::tuple Read(size_t frames, float timeout);

 private:
  void AppendData(const int16_t* audio_data,
                  int sample_rate,
                  size_t number_of_channels,
                  size_t number_of_frames);

  nb::ref<SoraTrackInterface> track_;
  const int output_sample_rate_;
  const size_t output_channels_;
  std::unique_ptr<webrtc::AudioFrame> audio_frame_;
  webrtc::acm2::ACMResampler resampler_;
  std::mutex buffer_mtx_;
  std::condition_variable buffer_cond_;
  rtc::BufferT<int16_t> buffer_;
  int sample_rate_;
  size_t number_of_channels_;
};

#endif