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

class SoraAudioSinkImpl : public webrtc::AudioTrackSinkInterface,
                          public DisposeSubscriber {
 public:
  SoraAudioSinkImpl(SoraTrackInterface* track,
                    int output_sample_rate,
                    size_t output_channels);
  ~SoraAudioSinkImpl();

  void Del();
  void Disposed();
  void PubliserDisposed() override;
  // webrtc::AudioTrackSinkInterface
  void OnData(const void* audio_data,
              int bits_per_sample,
              int sample_rate,
              size_t number_of_channels,
              size_t number_of_frames,
              absl::optional<int64_t> absolute_capture_timestamp_ms) override;

  std::function<void(
      nb::ndarray<nb::numpy, int16_t, nb::shape<nb::any, nb::any>>)>
      on_data_;
  std::function<void(int, size_t)> on_format_;

  nb::tuple Read(size_t frames, float timeout);

 private:
  void AppendData(const int16_t* audio_data,
                  int sample_rate,
                  size_t number_of_channels,
                  size_t number_of_frames);

  SoraTrackInterface* track_;
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