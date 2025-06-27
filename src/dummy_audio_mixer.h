#ifndef DUMMY_AUDIO_MIXER_H_
#define DUMMY_AUDIO_MIXER_H_

#include <memory>

// WebRTC
#include <api/audio/audio_frame.h>
#include <api/audio/audio_mixer.h>
#include <api/environment/environment.h>
#include <api/scoped_refptr.h>
#include <api/task_queue/task_queue_base.h>
#include <rtc_base/synchronization/mutex.h>
#include <rtc_base/task_utils/repeating_task.h>
#include <rtc_base/thread_annotations.h>

/**
 * webrtc::AudioMixer を継承した DummyAudioMixer です。
 * 
 * PeerConnectionFactory 生成時に渡す cricket::MediaEngineDependencies の
 * audio_mixer を指定しない場合 webrtc::AudioMixerImpl が使用されます。
 * これはすべての AudioTrack の出力データのサンプリングレートとチャネル数を揃え、
 * ミキシングした上で音声出力デバイスに渡す役割を担います。
 * しかし、 Python SDK では音声をデバイスに出力することはありません。
 * ですが、 AudioTrack からデータを受け取る AudioSinkInterface::OnData は
 * AudioMixer により駆動されているため、 AudioSinkInterface::OnData を呼び出す仕組みだけを持つ
 * シンプルな webrtc::AudioMixer になっています。
 */
class DummyAudioMixer : public webrtc::AudioMixer {
 public:
  struct SourceStatus;
  static webrtc::scoped_refptr<DummyAudioMixer> Create(
      const webrtc::Environment& env);
  ~DummyAudioMixer();

  // AudioMixer functions
  bool AddSource(Source* audio_source) override;
  void RemoveSource(Source* audio_source) override;

  void Mix(size_t number_of_channels,
           webrtc::AudioFrame* audio_frame_for_mixing) override
      RTC_LOCKS_EXCLUDED(mutex_);

 protected:
  DummyAudioMixer(const webrtc::Environment& env);

 private:
  void ProcessAudio();
  const webrtc::Environment& env_;
  std::unique_ptr<webrtc::TaskQueueBase, webrtc::TaskQueueDeleter> task_queue_;
  webrtc::RepeatingTaskHandle handle_;

  mutable webrtc::Mutex mutex_;
  std::vector<std::unique_ptr<SourceStatus>> audio_source_list_
      RTC_GUARDED_BY(mutex_);
};

#endif