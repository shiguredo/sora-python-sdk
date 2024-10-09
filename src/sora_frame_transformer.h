#ifndef SORA_TRANSFORMER_H_
#define SORA_TRANSFORMER_H_

// nonobind
#include <nanobind/nanobind.h>
#include <nanobind/stl/unique_ptr.h>

// WebRTC
#include <api/frame_transformer_interface.h>

namespace nb = nanobind;

class SoraTransformFrameCallback {
 public:
  virtual void Transform(std::unique_ptr<webrtc::TransformableFrameInterface>
                             transformable_frame) = 0;
};

/**
 * webrtc::FrameTransformerInterface を継承する SoraFrameTransformerInterface です。
 * 
 * webrtc::FrameTransformerInterface は rtc::scoped_refptr なので、
 * nanobind で直接のハンドリングが難しいので用意しました。
 */
class SoraFrameTransformerInterface : public webrtc::FrameTransformerInterface {
 public:
  SoraFrameTransformerInterface(SoraTransformFrameCallback* transformer)
      : transformer_(transformer) {}
  void Release() {
    // SoraFrameTransformer が先になくなっても実害が出ないようにする
    StartShortCircuiting();
    transformer_ = nullptr;
  }

  void Transform(std::unique_ptr<webrtc::TransformableFrameInterface>
                     transformable_frame) override {
    if (transformer_) {
      transformer_->Transform(std::move(transformable_frame));
    }
  }
  void OnTransformedFrame(
      std::unique_ptr<webrtc::TransformableFrameInterface> frame) {
    if (callback_) {
      callback_->OnTransformedFrame(std::move(frame));
    }
  }
  void StartShortCircuiting() {
    if (callback_) {
      callback_->StartShortCircuiting();
    }
  }
  void RegisterTransformedFrameCallback(
      rtc::scoped_refptr<webrtc::TransformedFrameCallback> callback) override {
    callback_ = callback;
  }
  void UnregisterTransformedFrameCallback() override { callback_ = nullptr; }

 private:
  SoraTransformFrameCallback* transformer_;
  rtc::scoped_refptr<webrtc::TransformedFrameCallback> callback_;
};

class SoraTransformableFrame {
 public:
  SoraTransformableFrame(
      std::unique_ptr<webrtc::TransformableFrameInterface> frame)
      : frame_(std::move(frame)) {}

  std::unique_ptr<webrtc::TransformableFrameInterface> ReleaseFrame() {
    return std::move(frame_);
  }
  const nb::object GetData() const {
    if (!frame_) {
      return nb::none();
    }
    auto view = frame_->GetData();
    return nb::bytes(view.data(), view.size());
  }
  void SetData(nb::bytes data) {
    if (!frame_) {
      return;
    }
    frame_->SetData(rtc::ArrayView<const uint8_t>(
        reinterpret_cast<const uint8_t*>(data.c_str()), data.size()));
  }
  const nb::object GetPayloadType() const {
    return frame_ ? nb::int_(frame_->GetPayloadType()) : nb::none();
  }
  const nb::object GetSsrc() const {
    return frame_ ? nb::int_(frame_->GetSsrc()) : nb::none();
  }
  const nb::object GetTimestamp() const {
    return frame_ ? nb::int_(frame_->GetTimestamp()) : nb::none();
  }
  void SetRTPTimestamp(uint32_t timestamp) {
    if (!frame_) {
      return;
    }
    frame_->SetRTPTimestamp(timestamp);
  }
  // TODO(tnoho) まだある

 protected:
  std::unique_ptr<webrtc::TransformableFrameInterface> frame_;
};

class SoraFrameTransformer : public SoraTransformFrameCallback {
 public:
  SoraFrameTransformer() {
    interface_ = rtc::make_ref_counted<SoraFrameTransformerInterface>(this);
  }
  virtual ~SoraFrameTransformer() { Del(); }

  void Del() { interface_->Release(); }
  void OnTransformedFrame(std::unique_ptr<SoraTransformableFrame> frame) {
    interface_->OnTransformedFrame(frame->ReleaseFrame());
  }
  void StartShortCircuiting() { interface_->StartShortCircuiting(); }
  /**
   * SoraFrameTransformerInterface を取り出すため Python SDK 内で使う関数です。
   * 
   * @return rtc::scoped_refptr<SoraFrameTransformerInterface>
   */
  const rtc::scoped_refptr<SoraFrameTransformerInterface>
  GetFrameTransformerInterface() const {
    return interface_;
  }

 private:
  rtc::scoped_refptr<SoraFrameTransformerInterface> interface_;
};

class SoraTransformableAudioFrame : public SoraTransformableFrame {
 public:
  // TODO(tnoho) まだある
 private:
  const webrtc::TransformableAudioFrameInterface* frame() const {
    return static_cast<const webrtc::TransformableAudioFrameInterface*>(
        frame_.get());
  }
};

class SoraAudioFrameTransformer : public SoraFrameTransformer {
 public:
  void Transform(std::unique_ptr<webrtc::TransformableFrameInterface>
                     transformable_frame) override {
    on_transform_(std::make_unique<SoraTransformableAudioFrame>(
        std::move(transformable_frame)));
  }
  std::function<void(std::unique_ptr<SoraTransformableAudioFrame>)>
      on_transform_;
};

class SoraTransformableVideoFrame : public SoraTransformableFrame {
 public:
  // TODO(tnoho) まだある
 private:
  const webrtc::TransformableVideoFrameInterface* frame() const {
    return static_cast<const webrtc::TransformableVideoFrameInterface*>(
        frame_.get());
  }
};

class SoraVideoFrameTransformer : public SoraFrameTransformer {
 public:
  void Transform(std::unique_ptr<webrtc::TransformableFrameInterface>
                     transformable_frame) override {
    on_transform_(std::make_unique<SoraTransformableVideoFrame>(
        std::move(transformable_frame)));
  }
  std::function<void(std::unique_ptr<SoraTransformableVideoFrame>)>
      on_transform_;
};
#endif  // SORA_TRANSFORMER_H_