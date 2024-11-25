#include "dynamic_h264_decoder.h"

#include <dlfcn.h>

// WebRTC
#include <api/video/i420_buffer.h>
#include <modules/video_coding/include/video_error_codes.h>
#include <rtc_base/logging.h>
#include <third_party/libyuv/include/libyuv.h>

// OpenH264
#include <wels/codec_api.h>

namespace webrtc {

DynamicH264Decoder::DynamicH264Decoder(std::string openh264)
    : openh264_(std::move(openh264)) {}
DynamicH264Decoder::~DynamicH264Decoder() {
  Release();
}

bool DynamicH264Decoder::Configure(const Settings& settings) {
  Release();

  void* handle = ::dlopen(openh264_.c_str(), RTLD_LAZY);
  if (handle == nullptr) {
    RTC_LOG(LS_ERROR) << "Failed to dlopen";
    return false;
  }
  openh264_handle_ = handle;
  create_decoder_ = (CreateDecoderFunc)::dlsym(handle, "WelsCreateDecoder");
  if (create_decoder_ == nullptr) {
    RTC_LOG(LS_ERROR) << "Failed to dlsym(WelsCreateDecoder)";
    Release();
    return false;
  }
  destroy_decoder_ = (DestroyDecoderFunc)::dlsym(handle, "WelsDestroyDecoder");
  if (destroy_decoder_ == nullptr) {
    RTC_LOG(LS_ERROR) << "Failed to dlsym(WelsDestroyDecoder)";
    Release();
    return false;
  }

  ISVCDecoder* decoder = nullptr;
  int r = create_decoder_(&decoder);
  if (r != 0) {
    RTC_LOG(LS_ERROR) << "Failed to WelsCreateDecoder: r=" << r;
    Release();
    return false;
  }

  SDecodingParam param = {};
  r = decoder->Initialize(&param);
  if (r != 0) {
    RTC_LOG(LS_ERROR) << "Failed to ISVCDecoder::Initialize: r=" << r;
    Release();
    return false;
  }
  decoder_ = decoder;

  return true;
}
int32_t DynamicH264Decoder::Release() {
  if (decoder_ != nullptr) {
    decoder_->Uninitialize();
    destroy_decoder_(decoder_);
    decoder_ = nullptr;
  }

  if (openh264_handle_ != nullptr) {
    ::dlclose(openh264_handle_);
    openh264_handle_ = nullptr;
  }

  return WEBRTC_VIDEO_CODEC_OK;
}

int32_t DynamicH264Decoder::RegisterDecodeCompleteCallback(
    DecodedImageCallback* callback) {
  callback_ = callback;
  return WEBRTC_VIDEO_CODEC_OK;
}

int32_t DynamicH264Decoder::Decode(const EncodedImage& input_image,
                                   bool missing_frames,
                                   int64_t render_time_ms) {
  if (decoder_ == nullptr) {
    return WEBRTC_VIDEO_CODEC_UNINITIALIZED;
  }

  h264_bitstream_parser_.ParseBitstream(input_image);
  std::optional<int> qp = h264_bitstream_parser_.GetLastSliceQp();

  std::array<std::uint8_t*, 3> yuv;
  SBufferInfo info = {};
  int r = decoder_->DecodeFrameNoDelay(input_image.data(), input_image.size(),
                                       yuv.data(), &info);
  if (r != 0) {
    RTC_LOG(LS_ERROR) << "Failed to ISVCDecoder::DecodeFrameNoDelay: r=" << r;
    return WEBRTC_VIDEO_CODEC_ERROR;
  }

  if (info.iBufferStatus == 0) {
    return WEBRTC_VIDEO_CODEC_OK;
  }

  int width_y = info.UsrData.sSystemBuffer.iWidth;
  int height_y = info.UsrData.sSystemBuffer.iHeight;
  int width_uv = (width_y + 1) / 2;
  int height_uv = (height_y + 1) / 2;
  int stride_y = info.UsrData.sSystemBuffer.iStride[0];
  int stride_uv = info.UsrData.sSystemBuffer.iStride[1];
  rtc::scoped_refptr<webrtc::I420Buffer> i420_buffer(
      webrtc::I420Buffer::Create(width_y, height_y));
  libyuv::I420Copy(yuv[0], stride_y, yuv[1], stride_uv, yuv[2], stride_uv,
                   i420_buffer->MutableDataY(), i420_buffer->StrideY(),
                   i420_buffer->MutableDataU(), i420_buffer->StrideU(),
                   i420_buffer->MutableDataV(), i420_buffer->StrideV(), width_y,
                   height_y);

  webrtc::VideoFrame video_frame =
      webrtc::VideoFrame::Builder()
          .set_video_frame_buffer(i420_buffer)
          .set_timestamp_rtp(input_image.RtpTimestamp())
          .build();
  if (input_image.ColorSpace() != nullptr) {
    video_frame.set_color_space(*input_image.ColorSpace());
  }

  callback_->Decoded(video_frame, std::nullopt, qp);

  return WEBRTC_VIDEO_CODEC_OK;
}

const char* DynamicH264Decoder::ImplementationName() const {
  return "OpenH264";
}

}  // namespace webrtc
