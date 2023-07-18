#include "sora_audio_sink2.h"

#include <chrono>

// WebRTC
#include <api/audio/channel_layout.h>
#include <modules/audio_mixer/audio_frame_manipulator.h>

SoraAudioSink2Impl::SoraAudioSink2Impl(SoraTrackInterface* track,
                                       int output_sample_rate,
                                       size_t output_channels)
    : track_(track),
      output_sample_rate_(output_sample_rate),
      output_channels_(output_channels),
      sample_rate_(0),
      number_of_channels_(0) {
  audio_frame_ = std::make_unique<webrtc::AudioFrame>();
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
  if (absolute_capture_timestamp_ms) {
    audio_frame_->set_absolute_capture_timestamp_ms(
        *absolute_capture_timestamp_ms);
  }
  // Resampling して sampling_rate を揃える
  bool need_resample =
      output_sample_rate_ != -1 && sample_rate != output_sample_rate_;
  if (need_resample) {
    int samples_per_channel_int = resampler_.Resample10Msec(
        static_cast<const int16_t*>(audio_data), sample_rate,
        output_sample_rate_, number_of_channels,
        webrtc::AudioFrame::kMaxDataSizeSamples, audio_frame_->mutable_data());
    if (samples_per_channel_int < 0) {
      return;
    }
    audio_frame_->samples_per_channel_ =
        static_cast<size_t>(samples_per_channel_int);
    audio_frame_->sample_rate_hz_ = output_sample_rate_;
    audio_frame_->num_channels_ = number_of_channels;
    audio_frame_->channel_layout_ =
        webrtc::GuessChannelLayout(number_of_channels);
  }
  // Remix して channel 数を揃える
  bool need_remix =
      output_channels_ != 0 && number_of_channels != output_channels_;
  if (need_remix) {
    if (!need_resample) {
      audio_frame_->UpdateFrame(
          audio_frame_->timestamp_, static_cast<const int16_t*>(audio_data),
          number_of_frames, sample_rate, audio_frame_->speech_type_,
          audio_frame_->vad_activity_, number_of_channels);
    }
    webrtc::RemixFrame(output_channels_, audio_frame_.get());
  }

  if (need_resample || need_remix) {
    AppendData(audio_frame_->data(), audio_frame_->sample_rate_hz_,
               audio_frame_->num_channels_, audio_frame_->samples_per_channel_);
  } else {
    AppendData(static_cast<const int16_t*>(audio_data), sample_rate,
               number_of_channels, number_of_frames);
  }
}

void SoraAudioSink2Impl::AppendData(const int16_t* audio_data,
                                    int sample_rate,
                                    size_t number_of_channels,
                                    size_t number_of_frames) {
  {
    std::unique_lock<std::mutex> lock(buffer_mtx_);

    if (sample_rate_ != sample_rate ||
        number_of_channels_ != number_of_channels) {
      /* 実行中にフォーマットが変更されることは想定しないはずなので、その場合はエラーに落とすようにする */
      sample_rate_ = sample_rate;
      number_of_channels_ = number_of_channels;
      if (on_format_) {
        on_format_(sample_rate_, number_of_channels_);
      }
    }

    const size_t num_elements = number_of_channels_ * number_of_frames;
    buffer_.AppendData(num_elements, [&](rtc::ArrayView<int16_t> buf) {
      memcpy(buf.data(), audio_data, num_elements * sizeof(int16_t));
      return num_elements;
    });

    buffer_cond_.notify_all();
  }

  if (on_data_) {
    size_t shape[2] = {number_of_frames, number_of_channels_};
    auto data = nb::ndarray<nb::numpy, int16_t, nb::shape<nb::any, nb::any>>(
        (void*)audio_data, 2, shape);
    /* まだ使ったことながない。現状 Python 側で on_frame と同じ感覚でコールバックの外に値を持ち出すと落ちるはず。 */
    on_data_(data);
  }
}