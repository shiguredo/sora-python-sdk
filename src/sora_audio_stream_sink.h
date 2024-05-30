#ifndef SORA_AUDIO_STREAM_SINK_H_
#define SORA_AUDIO_STREAM_SINK_H_

#include <optional>

// nonobind
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>

// WebRTC
#include <api/audio/audio_frame.h>
#include <api/media_stream_interface.h>
#include <api/scoped_refptr.h>
#include <modules/audio_coding/acm2/acm_resampler.h>

#include "sora_track_interface.h"

namespace nb = nanobind;

/**
 * SoraAudioFrame 内で音声データを持つクラスの抽象クラス
 */
class SoraAudioFrameImpl {
 public:
  virtual ~SoraAudioFrameImpl() {}
  virtual const int16_t* RawData() const = 0;
  virtual std::vector<uint16_t> VectorData() const = 0;
  virtual size_t samples_per_channel() const = 0;
  virtual size_t num_channels() const = 0;
  virtual int sample_rate_hz() const = 0;
  virtual std::optional<int64_t> absolute_capture_timestamp_ms() const = 0;
};

/**
 * SoraAudioFrame を SoraAudioStreamSinkImpl から生成した際にデータを持つクラスです。
 * 
 * libwebrtc でオーディオデータを扱う際の単位である webrtc::AudioFrame のまま扱います。
 */
class SoraAudioFrameDefaultImpl : public SoraAudioFrameImpl {
 public:
  SoraAudioFrameDefaultImpl(std::unique_ptr<webrtc::AudioFrame> audio_frame);

  const int16_t* RawData() const override;
  std::vector<uint16_t> VectorData() const override;
  size_t samples_per_channel() const override;
  size_t num_channels() const override;
  int sample_rate_hz() const override;
  std::optional<int64_t> absolute_capture_timestamp_ms() const override;

 private:
  std::unique_ptr<webrtc::AudioFrame> audio_frame_;
};

/**
 * SoraAudioFrame を pickle した状態から __setstate__ で戻した場合にデータを持つクラスです。
 * 
 * nanobind でハンドリングできる型のみでコンストラクタを構成しています。
 */
class SoraAudioFrameVectorImpl : public SoraAudioFrameImpl {
 public:
  SoraAudioFrameVectorImpl(
      std::vector<uint16_t> vector,
      size_t samples_per_channel,
      size_t num_channels,
      int sample_rate_hz,
      std::optional<int64_t> absolute_capture_timestamp_ms);

  const int16_t* RawData() const override;
  std::vector<uint16_t> VectorData() const override;
  size_t samples_per_channel() const override;
  size_t num_channels() const override;
  int sample_rate_hz() const override;
  std::optional<int64_t> absolute_capture_timestamp_ms() const override;

 private:
  std::vector<uint16_t> vector_;
  size_t samples_per_channel_;
  size_t num_channels_;
  int sample_rate_hz_;
  std::optional<int64_t> absolute_capture_timestamp_ms_;
};

/**
 * 受信した 10ms 単位の音声データを保持する SoraAudioFrame です。
 * 
 * SoraAudioStreamSinkImpl から生成するための webrtc::AudioFrame を引数にもつコンストラクタと
 * pickle に対応するための Python から生成ためのコンストラクタが存在します。
 * それぞれでデータの持ち方が異なるため実際のデータは SoraAudioFrameImpl の impl_ 内にもっていて、
 * このクラスは Python へのインターフェイスを提供します。
 * pickle に対応するために抽象クラスだけでなく、このようなクラスが必要になりました。
 */
class SoraAudioFrame {
 public:
  // SoraAudioStreamSinkImpl から生成する際のコンストラクタ
  SoraAudioFrame(std::unique_ptr<webrtc::AudioFrame> audio_frame);
  // pickle した状態から __setstate__ で戻す際に使うコンストラクタ
  SoraAudioFrame(std::vector<uint16_t> vector,
                 size_t samples_per_channel,
                 size_t num_channels,
                 int sample_rate_hz,
                 std::optional<int64_t> absolute_capture_timestamp_ms);
  /**
   * SoraAudioFrame 内の音声データへの numpy.ndarray での参照を返します。
   * 
   * @return NumPy の配列 numpy.ndarray で サンプル数 x チャンネル数 になっている音声データ
   */
  nb::ndarray<nb::numpy, int16_t, nb::shape<-1, -1>> Data() const;
  /**
   * SoraAudioFrame 内の音声データへの直接参照を返します。
   * 
   * Python SDK 内で使う関数です。
   * 
   * @return 音声データの int16_t* ポインタ
   */
  const int16_t* RawData() const;
  /**
   * SoraAudioFrame 内の音声データを std::vector<uint16_t> で返します。
   * 
   * Python SDK 内で使う関数で pickle 化するために使います。
   * 
   * @return 音声データの std::vector<uint16_t>
   */
  std::vector<uint16_t> VectorData() const;
  /**
   * チャネルあたりのサンプル数を返します。
   * 
   * @return チャネルあたりのサンプル数
   */
  size_t samples_per_channel() const;
  /**
   * チャネル数を返します。
   * 
   * @return チャネル数
   */
  size_t num_channels() const;
  /**
   * サンプリングレートを返します。
   * 
   * @return サンプリングレート
   */
  int sample_rate_hz() const;
  /**
   * キャプチャした際のタイムスタンプがあればミリ秒で返します。
   * 
   * @return キャプチャした際のタイムスタンプ
   */
  std::optional<int64_t> absolute_capture_timestamp_ms() const;

 private:
  std::unique_ptr<SoraAudioFrameImpl> impl_;
};

/**
 * Sora からの音声を受け取る SoraAudioStreamSinkImpl です。
 * 
 * Connection の OnTrack コールバックから渡されるリモート Track から音声を取り出すことができます。
 * Track からの音声はコンストラクタで設定したサンプリングレートとチャネル数に変換し、
 * SoraAudioFrame に格納した上でコールバックで Python に音声データを渡します。
 * コールバックは libwebrtc 内部での扱いから 10ms 間隔で呼び出されるため、
 * コールバックは速やかに処理を返すことが求められます。 10ms 単位の高いリアルタム性を求めないのであれば、
 * 内部にバッファを持ち任意のタイミングで音声を取り出すことができる SoraAudioSink の利用を推奨します。
 * 
 * 実装上の留意点：Track の参照保持のための Impl のない SoraAudioStreamSink を __init__.py に定義しています。
 * SoraAudioStreamSinkImpl を直接 Python から呼び出すことは想定していません。
 */
class SoraAudioStreamSinkImpl : public webrtc::AudioTrackSinkInterface,
                                public DisposeSubscriber {
 public:
  SoraAudioStreamSinkImpl(SoraTrackInterface* track,
                          int output_sample_rate,
                          size_t output_channels);
  ~SoraAudioStreamSinkImpl();

  void Del();
  void Disposed();
  void PublisherDisposed() override;
  // webrtc::AudioTrackSinkInterface
  void OnData(const void* audio_data,
              int bits_per_sample,
              int sample_rate,
              size_t number_of_channels,
              size_t number_of_frames,
              absl::optional<int64_t> absolute_capture_timestamp_ms) override;
  /**
   * 音声データが来るたびに呼び出されるコールバック変数です。
   * 
   * Track から音声データが渡される 10ms 間隔で呼び出されます。このコールバック関数内では重い処理は行わないでください。
   * 渡される SoraAudioFrame は pickle が利用可能のため別プロセスなどにオフロードすることを推奨します。
   * また、この関数はメインスレッドから呼び出されないため留意してください。
   * 実装上の留意点：このコールバックで渡す引数は shared_ptr にしておかないとリークします。
   */
  std::function<void(std::shared_ptr<SoraAudioFrame>)> on_frame_;

 private:
  SoraTrackInterface* track_;
  const int output_sample_rate_;
  const size_t output_channels_;
  // ACMResampler の前に std::unique_ptr がなんでも良いので無いと何故かビルドが通らない
  std::unique_ptr<uint8_t> dummy_;
  webrtc::acm2::ACMResampler resampler_;
};

#endif