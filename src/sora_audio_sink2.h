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

class SoraAudioFrame {
 public:
  SoraAudioFrame(std::unique_ptr<webrtc::AudioFrame> audio_frame);
  SoraAudioFrame(std::vector<uint16_t> vector,
                 size_t samples_per_channel,
                 size_t num_channels,
                 int sample_rate_hz,
                 std::optional<int64_t> absolute_capture_timestamp_ms);

  nb::ndarray<nb::numpy, int16_t, nb::shape<nb::any, nb::any>> Data() const;
  const int16_t* RawData() const;
  std::vector<uint16_t> VectorData() const;
  size_t samples_per_channel() const;
  size_t num_channels() const;
  int sample_rate_hz() const;
  std::optional<int64_t> absolute_capture_timestamp_ms() const;

 private:
  std::unique_ptr<SoraAudioFrameImpl> impl_;
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