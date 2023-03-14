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

class SoraAudioSource : public SoraTrackInterface {
 public:
  SoraAudioSource(DisposePublisher* publisher,
                  rtc::scoped_refptr<SoraAudioSourceInterface> source,
                  rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track,
                  size_t channels,
                  int sample_rate);

  void OnData(const int16_t* data,
              size_t samples_per_channel,
              double timestamp);
  void OnData(const int16_t* data, size_t samples_per_channel);
  void OnData(nb::ndarray<int16_t,
                          nb::shape<nb::any, nb::any>,
                          nb::c_contig,
                          nb::device::cpu> ndarray,
              double timestamp);
  void OnData(nb::ndarray<int16_t,
                          nb::shape<nb::any, nb::any>,
                          nb::c_contig,
                          nb::device::cpu> ndarray);

 private:
  rtc::scoped_refptr<SoraAudioSourceInterface> source_;
};

#endif