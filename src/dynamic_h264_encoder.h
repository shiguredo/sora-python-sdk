/*
 *  Copyright (c) 2015 The WebRTC project authors. All Rights Reserved.
 *
 *  Use of this source code is governed by a BSD-style license
 *  that can be found in the LICENSE file in the root of the source
 *  tree. An additional intellectual property rights grant can be found
 *  in the file PATENTS.  All contributing project authors may
 *  be found in the AUTHORS file in the root of the source tree.
 *
 */

// modules/video_coding/codecs/h264/h264_encoder_impl.{h,cc} の
// OpenH264 の関数を動的に読むようにしただけ

#ifndef MODULES_VIDEO_CODING_CODECS_H264_H264_ENCODER_IMPL_H_
#define MODULES_VIDEO_CODING_CODECS_H264_H264_ENCODER_IMPL_H_

#if defined(WEBRTC_WIN) && !defined(__clang__)
#error "See: bugs.webrtc.org/9213#c13."
#endif

#include <memory>
#include <vector>

// WebRTC
#include <absl/container/inlined_vector.h>
#include <api/transport/rtp/dependency_descriptor.h>
#include <api/video/i420_buffer.h>
#include <api/video/video_codec_constants.h>
#include <api/video_codecs/scalability_mode.h>
#include <api/video_codecs/video_encoder.h>
#include <common_video/h264/h264_bitstream_parser.h>
#include <modules/video_coding/codecs/h264/include/h264.h>
#include <modules/video_coding/svc/scalable_video_controller.h>
#include <modules/video_coding/utility/quality_scaler.h>

// OpenH264
#include <wels/codec_app_def.h>

class ISVCEncoder;

namespace webrtc {

class DynamicH264Encoder : public VideoEncoder {
 public:
  static std::unique_ptr<VideoEncoder> Create(const Environment& env,
                                              H264EncoderSettings settings,
                                              std::string openh264) {
    return std::unique_ptr<VideoEncoder>(
        new DynamicH264Encoder(env, settings, std::move(openh264)));
  }

 public:
  struct LayerConfig {
    int simulcast_idx = 0;
    int width = -1;
    int height = -1;
    bool sending = true;
    bool key_frame_request = false;
    float max_frame_rate = 0;
    uint32_t target_bps = 0;
    uint32_t max_bps = 0;
    bool frame_dropping_on = false;
    int key_frame_interval = 0;
    int num_temporal_layers = 1;

    void SetStreamState(bool send_stream);
  };

  DynamicH264Encoder(const Environment& env,
                     H264EncoderSettings settings,
                     std::string openh264);

  ~DynamicH264Encoder() override;

  // `settings.max_payload_size` is ignored.
  // The following members of `codec_settings` are used. The rest are ignored.
  // - codecType (must be kVideoCodecH264)
  // - targetBitrate
  // - maxFramerate
  // - width
  // - height
  int32_t InitEncode(const VideoCodec* codec_settings,
                     const VideoEncoder::Settings& settings) override;
  int32_t Release() override;

  int32_t RegisterEncodeCompleteCallback(
      EncodedImageCallback* callback) override;
  void SetRates(const RateControlParameters& parameters) override;

  // The result of encoding - an EncodedImage and CodecSpecificInfo - are
  // passed to the encode complete callback.
  int32_t Encode(const VideoFrame& frame,
                 const std::vector<VideoFrameType>* frame_types) override;

  EncoderInfo GetEncoderInfo() const override;

  // Exposed for testing.
  H264PacketizationMode PacketizationModeForTesting() const {
    return packetization_mode_;
  }

 private:
  SEncParamExt CreateEncoderParams(size_t i) const;

  webrtc::H264BitstreamParser h264_bitstream_parser_;
  // Reports statistics with histograms.
  void ReportInit();
  void ReportError();

  std::vector<ISVCEncoder*> encoders_;
  std::vector<SSourcePicture> pictures_;
  std::vector<rtc::scoped_refptr<I420Buffer>> downscaled_buffers_;
  std::vector<LayerConfig> configurations_;
  std::vector<EncodedImage> encoded_images_;
  std::vector<std::unique_ptr<ScalableVideoController>> svc_controllers_;
  absl::InlinedVector<std::optional<ScalabilityMode>, kMaxSimulcastStreams>
      scalability_modes_;

  const Environment env_;
  VideoCodec codec_;
  H264PacketizationMode packetization_mode_;
  size_t max_payload_size_;
  int32_t number_of_cores_;
  std::optional<int> encoder_thread_limit_;
  EncodedImageCallback* encoded_image_callback_;

  bool has_reported_init_;
  bool has_reported_error_;

  std::vector<uint8_t> tl0sync_limit_;

 private:
  bool InitOpenH264();
  void ReleaseOpenH264();

  std::string openh264_;
  void* openh264_handle_ = nullptr;
  using CreateEncoderFunc = int (*)(ISVCEncoder**);
  using DestroyEncoderFunc = void (*)(ISVCEncoder*);
  CreateEncoderFunc create_encoder_ = nullptr;
  DestroyEncoderFunc destroy_encoder_ = nullptr;
};

}  // namespace webrtc

#endif  // MODULES_VIDEO_CODING_CODECS_H264_H264_ENCODER_IMPL_H_