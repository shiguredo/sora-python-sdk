#ifndef SORA_TRANSFORMER_H_
#define SORA_TRANSFORMER_H_

#include <unordered_map>

// nonobind
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
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
      : transformer_(transformer), default_callback_(nullptr) {}
  void ReleaseTransformer() {
    // SoraFrameTransformer が先になくなっても実害が出ないようにする
    StartShortCircuiting();
    transformer_ = nullptr;
  }
  // エンコードされたフレームがくる
  void Transform(std::unique_ptr<webrtc::TransformableFrameInterface>
                     transformable_frame) override {
    if (transformer_) {
      transformer_->Transform(std::move(transformable_frame));
    }
  }
  // Transform で渡されたフレームを返す
  void Enqueue(std::unique_ptr<webrtc::TransformableFrameInterface> frame) {
    uint32_t ssrc = frame->GetSsrc();
    auto it = callbacks_.find(ssrc);
    if (it != callbacks_.end() && it->second) {
      it->second->OnTransformedFrame(std::move(frame));
    } else if (default_callback_) {
      default_callback_->OnTransformedFrame(std::move(frame));
    }
  }
  // これを呼ぶと Transform が呼び出されることなく OnTransformedFrame に転送されるようになる
  void StartShortCircuiting() {
    if (default_callback_) {
      default_callback_->StartShortCircuiting();
    }
    for (const auto& pair : callbacks_) {
      if (pair.second) {
        pair.second->StartShortCircuiting();
      }
    }
  }
  // webrtc::TransformedFrameCallback を渡してくる関数が Audio と Video で異なる
  // Audio はこっち
  void RegisterTransformedFrameCallback(
      webrtc::scoped_refptr<webrtc::TransformedFrameCallback> callback)
      override {
    default_callback_ = callback;
  }
  // Video はこっち
  void RegisterTransformedFrameSinkCallback(
      webrtc::scoped_refptr<webrtc::TransformedFrameCallback> callback,
      uint32_t ssrc) override {
    callbacks_[ssrc] = callback;
  }
  // Audio はこっち
  void UnregisterTransformedFrameCallback() override {
    default_callback_ = nullptr;
  }
  // Video はこっち
  void UnregisterTransformedFrameSinkCallback(uint32_t ssrc) override {
    callbacks_.erase(ssrc);
  }

 private:
  SoraTransformFrameCallback* transformer_;
  webrtc::scoped_refptr<webrtc::TransformedFrameCallback> default_callback_;
  std::unordered_map<uint32_t,
                     webrtc::scoped_refptr<webrtc::TransformedFrameCallback>>
      callbacks_;
};

/**
 * Transform で渡される webrtc::TransformableFrameInterface を格納する SoraTransformableFrame です。
 * エンコード済みのフレームデータを格納します。
 * 
 * コピーすることはできません。
 * enqueue に渡した時点で所有権を失うため利用できなくなるので注意してください。
 * 
 * Audio, Video で共通する部分をここに実装して、それぞれで継承して利用します。
 */
class SoraTransformableFrame {
 public:
  SoraTransformableFrame(
      std::unique_ptr<webrtc::TransformableFrameInterface> frame)
      : frame_(std::move(frame)) {}

  std::unique_ptr<webrtc::TransformableFrameInterface> ReleaseFrame() {
    // ReleaseFrame() で frame_ はなくなるが、
    // SoraTransformableFrame 自体を unique_ptr で扱っている前提のため参照時に frame_ の有無は確認しない
    return std::move(frame_);
  }

  /**
   * フレームデータを取得する関数です。
   * 
   * @return NumPy の配列 numpy.ndarray のフレームデータ
   */
  const nb::ndarray<nb::numpy, const uint8_t, nb::shape<-1>> GetData() const {
    auto view = frame_->GetData();

    // pybind11 なら memoryview があるが、 nanobind にはなく ndarray に const をつけて ReadOnly にする
    size_t shape[1] = {static_cast<size_t>(view.size())};
    return nb::ndarray<nb::numpy, const uint8_t, nb::shape<-1>>(
        view.data(), 1, shape, nb::handle());
  }
  /**
   * フレームデータを入れ替える関数です。
   * 
   * @param data 入れ替える NumPy の配列 numpy.ndarray のフレームデータ
   */
  void SetData(
      nb::ndarray<const uint8_t, nb::shape<-1>, nb::c_contig, nb::device::cpu>
          data) {
    frame_->SetData(
        webrtc::ArrayView<const uint8_t>(data.data(), data.shape(0)));
  }
  const uint8_t GetPayloadType() const { return frame_->GetPayloadType(); }
  const uint32_t GetSsrc() const { return frame_->GetSsrc(); }
  const uint32_t GetTimestamp() const {
    // これは RTPTimestamp なので注意
    return frame_->GetTimestamp();
  }
  void SetRTPTimestamp(uint32_t timestamp) {
    frame_->SetRTPTimestamp(timestamp);
  }
  std::optional<int64_t> GetCaptureTimeIdentifier() const {
    // Audio, Video, Direction によっては実装されていないため optional
    auto opt = frame_->GetPresentationTimestamp();
    return opt.has_value() ? std::optional<int64_t>(opt->us()) : std::nullopt;
  }
  webrtc::TransformableFrameInterface::Direction GetDirection() {
    return frame_->GetDirection();
  }
  std::string GetMimeType() { return std::move(frame_->GetMimeType()); }

 protected:
  std::unique_ptr<webrtc::TransformableFrameInterface> frame_;
};

/**
 * Encoded Transform を行う SoraFrameTransformer です。
 * 
 * Audio, Video で共通する部分をここに実装して、それぞれで継承して利用します。
 */
class SoraFrameTransformer : public SoraTransformFrameCallback {
 public:
  SoraFrameTransformer() {
    interface_ = webrtc::make_ref_counted<SoraFrameTransformerInterface>(this);
  }
  virtual ~SoraFrameTransformer() { Del(); }

  void Del() { interface_->ReleaseTransformer(); }
  /**
   * SoraTransformableFrame をストリームに戻す関数です。
   * 
   * この関数を呼び出すと SoraTransformableFrame の所有権がライブラリに渡るため、
   * 以後 SoraTransformableFrame を操作することはできません。
   * 
   * @param frame on_transform で渡された SoraTransformableFrame
   */
  void Enqueue(std::unique_ptr<SoraTransformableFrame> frame) {
    interface_->Enqueue(frame->ReleaseFrame());
  }
  void StartShortCircuiting() { interface_->StartShortCircuiting(); }
  /**
   * SoraFrameTransformerInterface を取り出すため Python SDK 内で使う関数です。
   * 
   * @return webrtc::scoped_refptr<SoraFrameTransformerInterface>
   */
  const webrtc::scoped_refptr<SoraFrameTransformerInterface>
  GetFrameTransformerInterface() const {
    return interface_;
  }

 private:
  webrtc::scoped_refptr<SoraFrameTransformerInterface> interface_;
};

/**
 * エンコード済みの Audio フレームデータを格納します。
 * 
 * 様々なパラメータが取得できますが optional になっているのもは、
 * Direction によっては実装されていない、
 * もしくは RTP Extension など他の依存から None を返す場合があります。
 */
class SoraTransformableAudioFrame : public SoraTransformableFrame {
 public:
  SoraTransformableAudioFrame(
      std::unique_ptr<webrtc::TransformableFrameInterface> frame)
      : SoraTransformableFrame(std::move(frame)) {}

  nb::ndarray<nb::numpy, const uint32_t, nb::shape<-1>> GetContributingSources()
      const {
    auto view = frame()->GetContributingSources();
    size_t shape[1] = {static_cast<size_t>(view.size())};
    return nb::ndarray<nb::numpy, const uint32_t, nb::shape<-1>>(
        view.data(), 1, shape, nb::handle());
  }
  const std::optional<uint16_t> SequenceNumber() const {
    // SENDER の時にしか入っていない
    return frame()->SequenceNumber();
  }
  std::optional<uint64_t> AbsoluteCaptureTimestamp() const {
    // SENDER の時にしか入っていない
    return frame()->AbsoluteCaptureTimestamp();
  }
  webrtc::TransformableAudioFrameInterface::FrameType Type() const {
    // RECEIVER の時には RTP Header Extension で Audio Level がないときは常に CN が返る
    return frame()->Type();
  }
  std::optional<uint8_t> AudioLevel() const {
    // RECEIVER の時には RTP Header Extension で Audio Level がないときは入っていない
    return frame()->AudioLevel();
  }
  std::optional<int64_t> ReceiveTime() const {
    // RECEIVER の時にしか入っていない
    auto opt = frame()->ReceiveTime();
    return opt.has_value() ? std::optional<int64_t>(opt->us()) : std::nullopt;
  }

 private:
  const webrtc::TransformableAudioFrameInterface* frame() const {
    return static_cast<const webrtc::TransformableAudioFrameInterface*>(
        frame_.get());
  }
};

/**
 * Audio の Encoded Transform を行う SoraAudioFrameTransformer です。
 * 
 * on_transform_ コールバックで SoraTransformableAudioFrame を渡してくるので、
 * 必要な処理を行った上で enqueue に返してください。
 */
class SoraAudioFrameTransformer : public SoraFrameTransformer {
 public:
  SoraAudioFrameTransformer() : SoraFrameTransformer() {}

  void Transform(std::unique_ptr<webrtc::TransformableFrameInterface>
                     transformable_frame) override {
    on_transform_(std::make_unique<SoraTransformableAudioFrame>(
        std::move(transformable_frame)));
  }
  std::function<void(std::unique_ptr<SoraTransformableAudioFrame>)>
      on_transform_;
};

/**
 * エンコード済みの Video フレームデータを格納します。
 * 
 * 様々なパラメータが取得できますが optional になっているのもは、
 * Direction によっては実装されていない、
 * もしくは RTP Extension など他の依存から None を返す場合があります。
 */
class SoraTransformableVideoFrame : public SoraTransformableFrame {
 public:
  SoraTransformableVideoFrame(
      std::unique_ptr<webrtc::TransformableFrameInterface> frame)
      : SoraTransformableFrame(std::move(frame)) {}

  bool IsKeyFrame() const { return frame()->IsKeyFrame(); }
  // 以下は VideoFrameMetadata のメンバーだが以下の理由からメンバーで参照可能にする
  // ・SetMetadata は javascript にない
  // ・Audio では Metadata が切られていない
  // ・VideoFrameMetadata でもメンバーが多すぎて削らないといけない
  std::optional<int64_t> GetFrameId() const {
    return frame()->Metadata().GetFrameId();
  }
  nb::ndarray<nb::numpy, const int64_t, nb::shape<-1>> GetFrameDependencies()
      const {
    auto view = frame()->Metadata().GetFrameDependencies();
    size_t shape[1] = {static_cast<size_t>(view.size())};
    return nb::ndarray<nb::numpy, const int64_t, nb::shape<-1>>(
        view.data(), 1, shape, nb::handle());
  }
  uint16_t GetWidth() const { return frame()->Metadata().GetWidth(); }
  uint16_t GetHeight() const { return frame()->Metadata().GetHeight(); }
  int GetSpatialIndex() const { return frame()->Metadata().GetSpatialIndex(); }
  int GetTemporalIndex() const {
    return frame()->Metadata().GetTemporalIndex();
  }
  nb::ndarray<nb::numpy, const uint32_t, nb::shape<-1>> GetCsrcs() const {
    auto vector = frame()->Metadata().GetCsrcs();
    size_t shape[1] = {static_cast<size_t>(vector.size())};
    return nb::ndarray<nb::numpy, const uint32_t, nb::shape<-1>>(
        vector.data(), 1, shape, nb::handle());
  };

 private:
  const webrtc::TransformableVideoFrameInterface* frame() const {
    return static_cast<const webrtc::TransformableVideoFrameInterface*>(
        frame_.get());
  }
};

/**
 * Video の Encoded Transform を行う SoraAudioFrameTransformer です。
 * 
 * on_transform_ コールバックで SoraTransformableVideoFrame を渡してくるので、
 * 必要な処理を行った上で enqueue に返してください。
 */
class SoraVideoFrameTransformer : public SoraFrameTransformer {
 public:
  SoraVideoFrameTransformer() : SoraFrameTransformer() {}

  void Transform(std::unique_ptr<webrtc::TransformableFrameInterface>
                     transformable_frame) override {
    on_transform_(std::make_unique<SoraTransformableVideoFrame>(
        std::move(transformable_frame)));
  }
  std::function<void(std::unique_ptr<SoraTransformableVideoFrame>)>
      on_transform_;
};
#endif  // SORA_TRANSFORMER_H_