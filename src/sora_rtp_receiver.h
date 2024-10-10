#ifndef SORA_RTP_RECEIVER_H_
#define SORA_RTP_RECEIVER_H_

#include <optional>

// nanobind
#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>

// WebRTC
#include <api/rtp_receiver_interface.h>
#include <api/scoped_refptr.h>

#include "sora_frame_transformer.h"

/**
 * SoraConnection の on_track で渡される webrtc::RtpReceiverInterface を格納する SoraRTPReceiver です。
 * 
 * 受信側の Encoded Transform を設定できるようにするために追加しました。
 */
class SoraRTPReceiver {
 public:
  SoraRTPReceiver(rtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver)
      : receiver_(receiver) {}

  /**
   * 受信側のジッターバッファの最小ディレイを設定します。
   * 
   * @param delay_seconds ジッターバッファの最初ディレイ(秒)。None をしてするとデフォルト値になります
   */
  void SetJitterBufferMinimumDelay(std::optional<double> delay_seconds) {
    receiver_->SetJitterBufferMinimumDelay(delay_seconds);
  }
  /**
   * 受信側の Encoded Transform を設定します。
   * 
   * @param transformer エンコードされたフレームが経由する SoraFrameTransformer
   */
  void SetFrameTransformer(SoraFrameTransformer* transformer) {
    auto interface = transformer->GetFrameTransformerInterface();
    receiver_->SetFrameTransformer(interface);
  }

 private:
  rtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver_;
};
#endif  // SORA_RTP_RECEIVER_H_