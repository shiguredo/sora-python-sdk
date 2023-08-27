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

/**
 * SoraAudioFrame の音声データに音声である率を返す VAD です。
 * 
 * 受信した音声データに対して何らかの処理を Python で行う場合、
 * 全体の負荷軽減を考えるのであれば音声データから音声であると推測されるデータのみに、
 * 処理を行うようにした方が全体の負荷を下げることができます。
 * libwebrtc には優秀な VAD が含まれているため、これを活用したユーティリティクラスとして用意しました。
 */
class SoraVAD {
 public:
  SoraVAD();

  /**
   * SoraAudioFrame 内の音声データが音声である確率を返します。
   * 
   * libwebrtc 内部では 0.95 より大きい場合に音声とみなしています。
   * 
   * @param frame 音声である確率を求める SoraAudioFrame
   * @return 0 - 1 で表される音声である確率
   */
  float Analyze(std::shared_ptr<SoraAudioFrame> frame);

 private:
  std::unique_ptr<webrtc::AudioBuffer> audio_buffer_;
  webrtc::StreamConfig vad_input_config_;
  std::unique_ptr<webrtc::VoiceActivityDetectorWrapper> vad_;
};

#endif