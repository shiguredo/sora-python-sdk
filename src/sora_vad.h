#ifndef SORA_VAD_H_
#define SORA_VAD_H_

// nonobind
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>

// WebRTC
#include <common_audio/vad/include/webrtc_vad.h>
#include <modules/audio_processing/agc2/vad_wrapper.h>
#include <modules/audio_processing/audio_buffer.h>
#include <modules/audio_processing/include/audio_processing.h>

#include "sora_audio_sink2.h"

namespace nb = nanobind;

class SoraVAD {
 public:
  SoraVAD();

  float Analyze(std::shared_ptr<SoraAudioFrame> frame);

 private:
  std::unique_ptr<webrtc::AudioBuffer> audio_buffer_;
  webrtc::StreamConfig vad_input_config_;
  std::unique_ptr<webrtc::VoiceActivityDetectorWrapper> vad_;
};

#endif