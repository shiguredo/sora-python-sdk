#include "dummy_audio_mixer.h"

struct DummyAudioMixer::SourceStatus {
  SourceStatus(Source* audio_source) : audio_source(audio_source) {}
  Source* audio_source = nullptr;

  webrtc::AudioFrame audio_frame;
};

rtc::scoped_refptr<DummyAudioMixer> DummyAudioMixer::Create(
    webrtc::TaskQueueFactory* task_queue_factory) {
  return rtc::make_ref_counted<DummyAudioMixer>(task_queue_factory);
}

void DummyAudioMixer::Mix(size_t number_of_channels,
                          webrtc::AudioFrame* audio_frame_for_mixing) {
  webrtc::MutexLock lock(&mutex_);
  for (auto& source_and_status : audio_source_list_) {
    /**
     * webrtc::AudioTrackSinkInterface の OnData はこの関数内で呼ばれる
     * 
     * 第一引数の設定値にサンプリングレートがリサンプリングされるが、
     * -1 を指定するとリサンプリングされなくなる。
     * SoraAudioSinkImpl の OnData 内でリサンプリングするため、
     * ここでは -1 を指定している。
    */
    source_and_status->audio_source->GetAudioFrameWithInfo(
        -1, &source_and_status->audio_frame);
  }
}

bool DummyAudioMixer::AddSource(Source* audio_source) {
  webrtc::MutexLock lock(&mutex_);
  audio_source_list_.emplace_back(new SourceStatus(audio_source));
  return true;
}

void DummyAudioMixer::RemoveSource(Source* audio_source) {
  webrtc::MutexLock lock(&mutex_);
  const auto iter = std::find_if(
      audio_source_list_.begin(), audio_source_list_.end(),
      [audio_source](const std::unique_ptr<DummyAudioMixer::SourceStatus>& p) {
        return p->audio_source == audio_source;
      });
  audio_source_list_.erase(iter);
}

DummyAudioMixer::DummyAudioMixer(webrtc::TaskQueueFactory* task_queue_factory)
    : task_queue_factory_(task_queue_factory) {
  /**
   * 通常 webrtc::AudioMixer の Mix は音声出力デバイスのループで呼ばれるが、
   * sora::SoraClientContextConfig::use_audio_device を false にした際に設定される、
   * webrtc::AudioDeviceDummy はループを回さないため、ここでループを作ることとした。
   */
  task_queue_ =
      std::make_unique<rtc::TaskQueue>(task_queue_factory_->CreateTaskQueue(
          "TestAudioDeviceModuleImpl",
          webrtc::TaskQueueFactory::Priority::NORMAL));

  webrtc::RepeatingTaskHandle::Start(task_queue_->Get(), [this]() {
    ProcessAudio();
    // オーディオフレームは 10 ms ごとに処理するため 10000 us を指定する
    return webrtc::TimeDelta::Micros(10000);
  });
}

void DummyAudioMixer::ProcessAudio() {
  // 意味はないけど呼ばないと AudioSinkInterface::OnData が発火しない
  Mix(0, nullptr);
}