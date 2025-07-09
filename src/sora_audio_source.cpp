#include "sora_audio_source.h"

SoraAudioSourceInterface::SoraAudioSourceInterface(size_t channels,
                                                   int sample_rate)
    : channels_(channels),
      sample_rate_(sample_rate),
      buffer_samples_(sample_rate / 100),
      buffer_size_(sample_rate / 100 * channels),
      buffer_used_(0),
      last_timestamp_(0) {
  buffer_ = new int16_t[buffer_size_];
}

SoraAudioSourceInterface::~SoraAudioSourceInterface() {
  delete[] buffer_;
}

void SoraAudioSourceInterface::OnData(const int16_t* data,
                                      size_t samples_per_channel,
                                      std::optional<int64_t> timestamp) {
  size_t size = samples_per_channel * channels_;
  if (buffer_used_ > 0) {
    // 先に 10 ms に満たず残したデータを新たなデータと繋げて 10 ms を超える場合は送る
    bool continuous = true;
    if (timestamp && last_timestamp_ != 0) {
      // 先の残りの先頭におけるタイムスタンプを渡されたタイムスタンプから算出する
      int64_t prev_ts =
          *timestamp - buffer_used_ * 1000 / (sample_rate_ * channels_);
      // 最後に送ったタイムスタンプ + 10 ms 前後でない場合は連続でないので先の残りは捨てる
      // 元の型が double なので余裕を入れた
      continuous =
          prev_ts > last_timestamp_ + 8 && prev_ts < last_timestamp_ + 12;
      if (continuous) {
        // 連続として扱う場合は次のバッファ先頭タイムスタンプは算出したものになる
        *timestamp = prev_ts;
      } else {
        // 非連続と判定した場合、後続のデータをバッファに貯め込むことを阻害しないように 0 にする
        last_timestamp_ = 0;
      }
    }

    if (continuous) {
      size_t copy = buffer_size_ - buffer_used_;
      if (size < copy) {
        copy = size;
      }

      memcpy(&buffer_[buffer_used_], data, copy * sizeof(int16_t));
      buffer_used_ += copy;
      data = static_cast<const int16_t*>(data) + copy;
      size -= copy;

      if (buffer_used_ != buffer_size_) {
        return;
      }

      Add10MsData(buffer_, timestamp);
      if (timestamp) {
        *timestamp += 10;
      }
      buffer_used_ = 0;
    }
  }

  while (size >= buffer_size_) {
    // 10 ms に足りなくなるまでデータを送る
    Add10MsData(data, timestamp);
    if (timestamp) {
      *timestamp += 10;
    }

    data = static_cast<const int16_t*>(data) + buffer_size_;
    size -= buffer_size_;
  }

  if (size > 0) {
    // 10 ms に満たず余ったデータをバッファに残す
    memcpy(buffer_, data, size * sizeof(int16_t));
    buffer_used_ = size;
  }
}

webrtc::MediaSourceInterface::SourceState SoraAudioSourceInterface::state()
    const {
  return kLive;
}

bool SoraAudioSourceInterface::remote() const {
  return false;
}

void SoraAudioSourceInterface::SetVolume(double volume) {
  for (auto* observer : audio_observers_) {
    observer->OnSetVolume(volume);
  }
}

void SoraAudioSourceInterface::RegisterAudioObserver(AudioObserver* observer) {
  audio_observers_.push_back(observer);
}

void SoraAudioSourceInterface::UnregisterAudioObserver(
    AudioObserver* observer) {
  audio_observers_.remove(observer);
}

void SoraAudioSourceInterface::AddSink(webrtc::AudioTrackSinkInterface* sink) {
  webrtc::MutexLock lock(&sink_lock_);
  sinks_.push_back(sink);
}

void SoraAudioSourceInterface::RemoveSink(
    webrtc::AudioTrackSinkInterface* sink) {
  webrtc::MutexLock lock(&sink_lock_);
  sinks_.remove(sink);
}

void SoraAudioSourceInterface::Add10MsData(const int16_t* data,
                                           std::optional<int64_t> timestamp) {
  if (timestamp) {
    last_timestamp_ = *timestamp;
  }
  webrtc::MutexLock lock(&sink_lock_);
  for (auto* sink : sinks_) {
    sink->OnData(data, 16, sample_rate_, channels_, buffer_samples_, timestamp);
  }
}

SoraAudioSource::SoraAudioSource(
    DisposePublisher* publisher,
    webrtc::scoped_refptr<SoraAudioSourceInterface> source,
    webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track,
    size_t channels,
    int sample_rate)
    : SoraTrackInterface(publisher, track), source_(source) {
  publisher_->AddSubscriber(this);
}

void SoraAudioSource::OnData(const int16_t* data,
                             size_t samples_per_channel,
                             double timestamp) {
  if (!track_) {
    return;
  }
  source_->OnData(data, samples_per_channel, (int64_t)(timestamp * 1000));
}

void SoraAudioSource::OnData(const int16_t* data, size_t samples_per_channel) {
  source_->OnData(data, samples_per_channel, std::nullopt);
}

void SoraAudioSource::OnData(
    nb::ndarray<int16_t, nb::shape<-1, -1>, nb::c_contig, nb::device::cpu>
        ndarray,
    double timestamp) {
  if (!track_) {
    return;
  }
  source_->OnData(ndarray.data(), ndarray.shape(0),
                  (int64_t)(timestamp * 1000));
}

void SoraAudioSource::OnData(
    nb::ndarray<int16_t, nb::shape<-1, -1>, nb::c_contig, nb::device::cpu>
        ndarray) {
  if (!track_) {
    return;
  }
  source_->OnData(ndarray.data(), ndarray.shape(0), std::nullopt);
}