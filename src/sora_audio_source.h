#ifndef SORA_AUDIO_SOURCE_H_
#define SORA_AUDIO_SOURCE_H_

#include <list>

// nonobind
#include <nanobind/ndarray.h>

// WebRTC
#include <absl/types/optional.h>
#include <api/media_stream_interface.h>
#include <api/notifier.h>
#include <api/peer_connection_interface.h>
#include <api/scoped_refptr.h>
#include <rtc_base/synchronization/mutex.h>

#include "sora_track_interface.h"

namespace nb = nanobind;

/**
 * SoraAudioSourceInterface は SoraAudioSource の実体です。
 * 
 * 実装上の留意点：webrtc::Notifier<webrtc::AudioSourceInterface> を継承しているクラスは
 * nanobind で直接的な紐付けを行うとエラーが出るため SoraAudioSource とはクラスを分けました。
 */
class SoraAudioSourceInterface
    : public webrtc::Notifier<webrtc::AudioSourceInterface> {
 public:
  SoraAudioSourceInterface(size_t channels, int sample_rate);
  ~SoraAudioSourceInterface();

  void OnData(const int16_t* data,
              size_t samples_per_channel,
              absl::optional<int64_t> timestamp);

  // MediaSourceInterface implementation.
  webrtc::MediaSourceInterface::SourceState state() const override;
  bool remote() const override;

  // AudioSourceInterface implementation.
  void SetVolume(double volume) override;
  void RegisterAudioObserver(AudioObserver* observer) override;
  void UnregisterAudioObserver(AudioObserver* observer) override;
  void AddSink(webrtc::AudioTrackSinkInterface* sink) override;
  void RemoveSink(webrtc::AudioTrackSinkInterface* sink) override;

 private:
  void Add10MsData(const int16_t* data, absl::optional<int64_t> timestamp);

  std::list<AudioObserver*> audio_observers_;
  webrtc::Mutex sink_lock_;
  std::list<webrtc::AudioTrackSinkInterface*> sinks_;

  const size_t channels_;
  const int sample_rate_;
  const size_t buffer_size_;
  const size_t buffer_samples_;
  size_t buffer_used_;
  int16_t* buffer_;
  int64_t last_timestamp_;
};

/**
 * Sora に音声データを送る受け口である SoraAudioSource です。
 * 
 * AudioSource に音声データを渡すことで、 Sora に音声を送ることができます。
 * AudioSource は MediaStreamTrack として振る舞うため、
 * AudioSource と同一の Sora インスタンスから生成された複数の Connection で共用できます。
 */
class SoraAudioSource : public SoraTrackInterface {
 public:
  SoraAudioSource(DisposePublisher* publisher,
                  rtc::scoped_refptr<SoraAudioSourceInterface> source,
                  rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track,
                  size_t channels,
                  int sample_rate);

  /**
   * Sora に送る音声データを渡します。
   * 
   * @param data 送信する 16bit PCM データの参照
   * @param samples_per_channel チャンネルごとのサンプル数
   * @param timestamp Python の time.time() で取得できるエポック秒で表されるフレームのタイムスタンプ
   */
  void OnData(const int16_t* data,
              size_t samples_per_channel,
              double timestamp);
  /**
   * Sora に送る音声データを渡します。
   * 
   * タイムスタンプは先に受け取ったデータと連続になっていると想定してサンプル数から自動生成します。
   * 
   * @param data 送信する 16bit PCM データの参照
   * @param samples_per_channel チャンネルごとのサンプル数
   */
  void OnData(const int16_t* data, size_t samples_per_channel);
  /**
   * Sora に送る音声データを渡します。
   * 
   * @param ndarray NumPy の配列 numpy.ndarray で チャンネルごとのサンプル数 x チャンネル数 になっている音声データ
   * @param timestamp Python の time.time() で取得できるエポック秒で表されるフレームのタイムスタンプ
   */
  void OnData(
      nb::ndarray<int16_t, nb::shape<-1, -1>, nb::c_contig, nb::device::cpu>
          ndarray,
      double timestamp);
  /**
   * Sora に送る音声データを渡します。
   * 
   * タイムスタンプは先に受け取ったデータと連続になっていると想定してサンプル数から自動生成します。
   * 
   * @param ndarray NumPy の配列 numpy.ndarray で チャンネルごとのサンプル数 x チャンネル数 になっている音声データ
   */
  void OnData(
      nb::ndarray<int16_t, nb::shape<-1, -1>, nb::c_contig, nb::device::cpu>
          ndarray);

 private:
  rtc::scoped_refptr<SoraAudioSourceInterface> source_;
};

#endif