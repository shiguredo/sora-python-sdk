#ifndef DUMMY_AUDIO_MIXER_H_
#define DUMMY_AUDIO_MIXER_H_

#include <memory>

// WebRTC
#include <api/audio/audio_frame.h>
#include <api/audio/audio_mixer.h>
#include <api/scoped_refptr.h>
#include <rtc_base/synchronization/mutex.h>
#include <rtc_base/task_queue.h>
#include <rtc_base/task_utils/repeating_task.h>
#include <rtc_base/thread_annotations.h>

class DummyAudioMixer : public webrtc::AudioMixer {
 public:
  struct SourceStatus;
  static rtc::scoped_refptr<DummyAudioMixer> Create(
      webrtc::TaskQueueFactory* task_queue_factory);

  // AudioMixer functions
  bool AddSource(Source* audio_source) override;
  void RemoveSource(Source* audio_source) override;

  void Mix(size_t number_of_channels,
           webrtc::AudioFrame* audio_frame_for_mixing) override
      RTC_LOCKS_EXCLUDED(mutex_);

 protected:
  DummyAudioMixer(webrtc::TaskQueueFactory* task_queue_factory);

 private:
  void ProcessAudio();
  const webrtc::TaskQueueFactory* task_queue_factory_;
  std::unique_ptr<rtc::TaskQueue> task_queue_;

  mutable webrtc::Mutex mutex_;
  std::vector<std::unique_ptr<SourceStatus>> audio_source_list_
      RTC_GUARDED_BY(mutex_);
};

#endif