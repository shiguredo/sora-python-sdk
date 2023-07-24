#ifndef SORA_AUDIO_SINK2_H_
#define SORA_AUDIO_SINK2_H_

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

class SoraAudioFrame {
 public:
  SoraAudioFrame(std::unique_ptr<webrtc::AudioFrame> audio_frame);
  SoraAudioFrame(std::vector<uint16_t> vector,
                 size_t samples_per_channel,
                 size_t num_channels,
                 int sample_rate_hz);

  nb::ndarray<nb::numpy, int16_t, nb::shape<nb::any, nb::any>> Data() const;
  const int16_t* RawData() const;
  std::vector<uint16_t> VectorData() const;
  size_t samples_per_channel() const;
  size_t num_channels() const;
  int sample_rate_hz() const;
  std::optional<int64_t> absolute_capture_timestamp_ms() const;

 private:
  std::unique_ptr<webrtc::AudioFrame> audio_frame_;
  std::vector<uint16_t> vector_;
  size_t samples_per_channel_;
  size_t num_channels_;
  int sample_rate_hz_;
};

class SoraAudioSink2Impl : public webrtc::AudioTrackSinkInterface,
                           public DisposeSubscriber {
 public:
  SoraAudioSink2Impl(SoraTrackInterface* track,
                     int output_sample_rate,
                     size_t output_channels);
  ~SoraAudioSink2Impl();

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

  // このコールバックは shared_ptr にしないとリークする
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