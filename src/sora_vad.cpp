#include "sora_vad.h"

#include <chrono>

// WebRTC
#include <api/audio/channel_layout.h>
#include <modules/audio_mixer/audio_frame_manipulator.h>
#include <modules/audio_processing/agc2/agc2_common.h>
#include <modules/audio_processing/agc2/cpu_features.h>
#include <modules/audio_processing/agc2/rnn_vad/common.h>

SoraVAD::SoraVAD() {
  vad_ = std::make_unique<webrtc::VoiceActivityDetectorWrapper>(
      webrtc::kVadResetPeriodMs,  // libWebRTC 内部の設定に合わせる
      webrtc::GetAvailableCpuFeatures(),
      webrtc::rnn_vad::
          kSampleRate24kHz  // 24kHz にしておかないと、VAD 前にリサンプリングが走る
  );
}

float SoraVAD::Analyze(std::shared_ptr<SoraAudioFrame> frame) {
  if (!audio_buffer_ ||
      vad_input_config_.sample_rate_hz() != frame->sample_rate_hz() ||
      vad_input_config_.num_channels() != frame->num_channels()) {
    // audio_buffer_ のサンプリングレートやチャネル数と frame のそれが一致しない場合は audio_buffer_ を初期化する
    audio_buffer_.reset(new webrtc::AudioBuffer(
        frame->sample_rate_hz(), frame->num_channels(),
        webrtc::rnn_vad::kSampleRate24kHz,  // VAD は 24kHz なので合わせる
        1,                                  // VAD は 1 チャンネルなので合わせる
        webrtc::rnn_vad::
            kSampleRate24kHz,  // 出力はしないが、余計なインスタンスを生成しないよう合わせる
        1                      // 出力はしないが VAD とチャネル数は合わせておく
        ));
    vad_input_config_ =
        webrtc::StreamConfig(frame->sample_rate_hz(), frame->num_channels());
  }
  audio_buffer_->CopyFrom(frame->RawData(), vad_input_config_);
  return vad_->Analyze(audio_buffer_->view());
}
