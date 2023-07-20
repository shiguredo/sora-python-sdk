#include "sora_audio_sink2.h"

#include <chrono>

// WebRTC
#include <api/audio/channel_layout.h>
#include <modules/audio_mixer/audio_frame_manipulator.h>
#include <modules/audio_processing/agc2/agc2_common.h>
#include <modules/audio_processing/agc2/cpu_features.h>
#include <modules/audio_processing/agc2/rnn_vad/common.h>
#include <modules/audio_processing/include/audio_frame_view.h>

SoraAudioFrame::SoraAudioFrame(std::unique_ptr<webrtc::AudioFrame> audio_frame)
    : audio_frame_(std::move(audio_frame)) {}

nb::ndarray<nb::numpy, int16_t, nb::shape<nb::any, nb::any>>
SoraAudioFrame::Data() const {
  size_t shape[2] = {static_cast<size_t>(audio_frame_->samples_per_channel()),
                     static_cast<size_t>(audio_frame_->num_channels())};
  return nb::ndarray<nb::numpy, int16_t, nb::shape<nb::any, nb::any>>(
      (int16_t*)audio_frame_->data(), 2, shape);
}

const int16_t* SoraAudioFrame::RawData() const {
  return audio_frame_->data();
}

size_t SoraAudioFrame::samples_per_channel() const {
  return audio_frame_->samples_per_channel();
}

size_t SoraAudioFrame::num_channels() const {
  return audio_frame_->num_channels();
}

int SoraAudioFrame::sample_rate_hz() const {
  return audio_frame_->sample_rate_hz();
}

std::optional<int64_t> SoraAudioFrame::absolute_capture_timestamp_ms() const {
  if (audio_frame_->absolute_capture_timestamp_ms()) {
    std::optional<int64_t> value =
        *audio_frame_->absolute_capture_timestamp_ms();
    return value;
  } else {
    return std::nullopt;
  }
}

SoraAudioSink2Impl::SoraAudioSink2Impl(SoraTrackInterface* track,
                                       int output_sample_rate,
                                       size_t output_channels)
    : track_(track),
      output_sample_rate_(output_sample_rate),
      output_channels_(output_channels) {
  track_->AddSubscriber(this);
  webrtc::AudioTrackInterface* audio_track =
      static_cast<webrtc::AudioTrackInterface*>(track_->GetTrack().get());
  audio_track->AddSink(this);
}

SoraAudioSink2Impl::~SoraAudioSink2Impl() {
  Del();
}

void SoraAudioSink2Impl::Del() {
  if (track_) {
    track_->RemoveSubscriber(this);
  }
  Disposed();
}

void SoraAudioSink2Impl::Disposed() {
  if (track_ && track_->GetTrack()) {
    webrtc::AudioTrackInterface* audio_track =
        static_cast<webrtc::AudioTrackInterface*>(track_->GetTrack().get());
    audio_track->RemoveSink(this);
  }
  track_ = nullptr;
}

void SoraAudioSink2Impl::PublisherDisposed() {
  Disposed();
}

void SoraAudioSink2Impl::OnData(
    const void* audio_data,
    int bits_per_sample,
    int sample_rate,
    size_t number_of_channels,
    size_t number_of_frames,
    absl::optional<int64_t> absolute_capture_timestamp_ms) {
  auto tuned_frame = std::make_unique<webrtc::AudioFrame>();
  tuned_frame->UpdateFrame(
      0, static_cast<const int16_t*>(audio_data), number_of_frames, sample_rate,
      webrtc::AudioFrame::SpeechType::kUndefined,
      webrtc::AudioFrame::VADActivity::kVadUnknown, number_of_channels);
  if (absolute_capture_timestamp_ms) {
    tuned_frame->set_absolute_capture_timestamp_ms(
        *absolute_capture_timestamp_ms);
  }
  // Resampling して sampling_rate を揃える
  bool need_resample = output_sample_rate_ != -1 &&
                       tuned_frame->sample_rate_hz() != output_sample_rate_;
  if (need_resample) {
    int samples_per_channel_int = resampler_.Resample10Msec(
        tuned_frame->data(), tuned_frame->sample_rate_hz(), output_sample_rate_,
        tuned_frame->num_channels(), webrtc::AudioFrame::kMaxDataSizeSamples,
        tuned_frame->mutable_data());
    if (samples_per_channel_int < 0) {
      return;
    }
    tuned_frame->samples_per_channel_ =
        static_cast<size_t>(samples_per_channel_int);
    tuned_frame->sample_rate_hz_ = output_sample_rate_;
  }
  // Remix して channel 数を揃える
  if (output_channels_ != 0 &&
      tuned_frame->num_channels() != output_channels_) {
    webrtc::RemixFrame(output_channels_, tuned_frame.get());
  }

  on_frame_(std::make_shared<SoraAudioFrame>(std::move(tuned_frame)));
}
