#ifndef DYNAMIC_H264_DECODER_H_
#define DYNAMIC_H264_DECODER_H_

#include <memory>

// WebRTC
#include <common_video/h264/h264_bitstream_parser.h>
#include <modules/video_coding/codecs/h264/include/h264.h>

class ISVCDecoder;

namespace webrtc {

class DynamicH264Decoder : public H264Decoder {
 public:
  static std::unique_ptr<VideoDecoder> Create(std::string openh264) {
    return std::unique_ptr<VideoDecoder>(
        new DynamicH264Decoder(std::move(openh264)));
  }

  DynamicH264Decoder(std::string openh264);
  ~DynamicH264Decoder() override;

  bool Configure(const Settings& settings) override;
  int32_t Release() override;

  int32_t RegisterDecodeCompleteCallback(
      DecodedImageCallback* callback) override;

  int32_t Decode(const EncodedImage& input_image,
                 bool missing_frames,
                 int64_t render_time_ms = -1) override;

  const char* ImplementationName() const override;

 private:
  DecodedImageCallback* callback_ = nullptr;
  ISVCDecoder* decoder_ = nullptr;
  webrtc::H264BitstreamParser h264_bitstream_parser_;

  std::string openh264_;
  void* openh264_handle_ = nullptr;
  using CreateDecoderFunc = int (*)(ISVCDecoder**);
  using DestroyDecoderFunc = void (*)(ISVCDecoder*);
  CreateDecoderFunc create_decoder_ = nullptr;
  DestroyDecoderFunc destroy_decoder_ = nullptr;
};

}  // namespace webrtc

#endif
