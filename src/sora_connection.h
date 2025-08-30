#ifndef SORA_CONNECTION_H_
#define SORA_CONNECTION_H_

#include <condition_variable>
#include <memory>
#include <thread>

// nonobind
// clang-format off
#include <nanobind/nanobind.h>
// clang-format on
#include <nanobind/intrusive/counter.h>
#include <nanobind/intrusive/ref.h>
#include <nanobind/stl/shared_ptr.h>

// Boost
#include <boost/asio/io_context.hpp>

// WebRTC
#include <api/media_stream_interface.h>
#include <api/rtp_sender_interface.h>

// Sora
#include <sora/sora_signaling.h>

#include "dispose_listener.h"
#include "sora_frame_transformer.h"
#include "sora_track_interface.h"

namespace nb = nanobind;

class SoraSignalingObserver;

/**
 * Sora との接続ごとに生成する SoraConnection です。
 * 
 * Python に Connection を制御する関数を提供します。
 */
class SoraConnection : public DisposePublisher,
                       public DisposeSubscriber,
                       public nb::intrusive_base {
 public:
  /**
   * コンストラクタではインスタンスの生成のみで実際の生成処理は Init 関数で行います。
   */
  SoraConnection(CountedPublisher* publisher,
                 boost::asio::io_context* ioc,
                 std::shared_ptr<SoraSignalingObserver> observer);
  ~SoraConnection();

  void Disposed() override;
  void PublisherDisposed() override;

  /**
   * SoraConnection の初期化を行う関数です。
   * 
   * この関数は現在記述されている 1 箇所以外での呼び出しは禁止です。
   * 実際に Sora との接続である sora::SoraSignaling を生成しているのはこの関数です。
   * Python から Connection に各種コールバックを容易に設定できるようにするために、
   * SoraConnection に sora::SoraSignalingObserver を継承させました。
   * しかし sora::SoraSignalingConfig::observer が sora::SoraSignalingObserver の弱参照を要求するので、
   * SoraConnection 生成時には何もせず、ここで sora::SoraSignalingConfig を受け取って初期化するようにしました。
   * 
   * @param config Sora への接続設定を持つ sora::SoraSignalingConfig
   */
  void Init(sora::SoraSignalingConfig& config);
  /**
   * Sora と接続する関数です。
   */
  void Connect();
  /**
   * Sora から切断する関数です。
   */
  void Disconnect();
  /**
   * 音声トラックを入れ替える javascript でいう replaceTrack に相当する関数です。
   * 
   * TODO(tnoho): Python で呼び出すことを想定しているが、動作確認していないため NB_MODULE に定義していない
   * 
   * @param audio_source 入れ替える新しい音声トラック
   */
  void SetAudioTrack(nb::ref<SoraTrackInterface> audio_source);
  /**
   * 映像トラックを入れ替える javascript でいう replaceTrack に相当する関数です。
   * 
   * TODO(tnoho): Python で呼び出すことを想定しているが、動作確認していないため NB_MODULE に定義していない
   * 
   * @param audio_source 入れ替える新しい映像トラック
   */
  void SetVideoTrack(nb::ref<SoraTrackInterface> video_source);
  /**
   * 音声送信時の Encoded Transform を設定する関数です。
   * 
   * TODO(tnoho): Python で呼び出すことを想定しているが、動作確認していないため NB_MODULE に定義していない
   * 
   * @param audio_sender_frame_transformer エンコードされたフレームが経由する SoraAudioFrameTransformer
   */
  void SetAudioSenderFrameTransformer(
      SoraAudioFrameTransformer* audio_sender_frame_transformer);
  /**
   * 映像送信時の Encoded Transform を設定する関数です。
   * 
   * TODO(tnoho): Python で呼び出すことを想定しているが、動作確認していないため NB_MODULE に定義していない
   * 
   * @param video_sender_frame_transformer エンコードされたフレームが経由する SoraVideoFrameTransformer
   */
  void SetVideoSenderFrameTransformer(
      SoraVideoFrameTransformer* video_sender_frame_transformer);
  /**
   * DataChannel でデータを送信する関数です。
   * 
   * @param label 送信する DataChannel の label
   * @param data 送信するデータ
   */
  bool SendDataChannel(const std::string& label, nb::bytes& data);

  /**
   * WebRTC の統計情報を取得します。
   *
   * この関数は PeerConnection::GetStats() を呼んで、結果のコールバックがやってくるまでスレッドをブロックすることに注意してください。
   * また、libwebrtc のシグナリングスレッドから呼ぶとデッドロックするので、必ずそれ以外のスレッドから呼ぶようにしてください。
   */
  std::string GetStats();

  // sora::SoraSignalingObserver に定義されているコールバック関数
  void OnSetOffer(std::string offer);
  void OnDisconnect(sora::SoraSignalingErrorCode ec, std::string message);
  void OnNotify(std::string text);
  void OnPush(std::string text);
  void OnMessage(std::string label, std::string data);
  void OnRpc(std::string data);
  void OnSwitched(std::string text);
  void OnSignalingMessage(sora::SoraSignalingType type,
                          sora::SoraSignalingDirection direction,
                          std::string message);
  void OnWsClose(uint16_t code, std::string message);
  void OnTrack(
      webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver);
  void OnRemoveTrack(
      webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver);
  void OnDataChannel(std::string label);

  // sora::SoraSignalingObserver のコールバック関数が呼び出された時に対応して呼び出す Python の関数を保持する
  std::function<
      void(sora::SoraSignalingType, sora::SoraSignalingDirection, std::string)>
      on_signaling_message_;
  std::function<void(std::string)> on_set_offer_;
  std::function<void(int, std::string)> on_ws_close_;
  std::function<void(sora::SoraSignalingErrorCode, std::string)> on_disconnect_;
  std::function<void(std::string)> on_notify_;
  std::function<void(std::string)> on_push_;
  std::function<void(std::string, nb::bytes)> on_message_;
  std::function<void(nb::bytes)> on_rpc_;
  std::function<void(std::string)> on_switched_;
  std::function<void(nb::ref<SoraMediaTrack>)> on_track_;
  std::function<void(std::string)> on_data_channel_;

 private:
  CountedPublisher* publisher_;
  std::shared_ptr<SoraSignalingObserver> observer_;
  boost::asio::io_context* ioc_;
  std::shared_ptr<sora::SoraSignaling> conn_;
  nb::ref<SoraTrackInterface> audio_source_ = nullptr;
  nb::ref<SoraTrackInterface> video_source_ = nullptr;
  webrtc::scoped_refptr<webrtc::RtpSenderInterface> audio_sender_;
  webrtc::scoped_refptr<webrtc::RtpSenderInterface> video_sender_;
  webrtc::scoped_refptr<SoraFrameTransformerInterface>
      audio_sender_frame_transformer_;
  webrtc::scoped_refptr<SoraFrameTransformerInterface>
      video_sender_frame_transformer_;
  bool on_disconnected_ = false;
  std::condition_variable_any on_disconnect_cv_;
};

class SoraSignalingObserver : public sora::SoraSignalingObserver {
 private:
  SoraConnection* conn;

 public:
  void SetSoraConnection(SoraConnection* c) { conn = c; }

  // sora::SoraSignalingObserver に定義されているコールバック関数
  void OnSetOffer(std::string offer) override {
    conn->OnSetOffer(std::move(offer));
  }
  void OnDisconnect(sora::SoraSignalingErrorCode ec,
                    std::string message) override {
    conn->OnDisconnect(ec, std::move(message));
  }
  void OnNotify(std::string text) override { conn->OnNotify(std::move(text)); }
  void OnPush(std::string text) override { conn->OnPush(std::move(text)); }
  void OnMessage(std::string label, std::string data) override {
    conn->OnMessage(std::move(label), std::move(data));
  }
  void OnRpc(std::string data) override { conn->OnRpc(std::move(data)); }
  void OnSwitched(std::string text) override {
    conn->OnSwitched(std::move(text));
  }
  void OnSignalingMessage(sora::SoraSignalingType type,
                          sora::SoraSignalingDirection direction,
                          std::string message) override {
    conn->OnSignalingMessage(type, direction, std::move(message));
  }
  void OnWsClose(uint16_t code, std::string message) override {
    conn->OnWsClose(code, std::move(message));
  }
  void OnTrack(webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>
                   transceiver) override {
    conn->OnTrack(transceiver);
  }
  void OnRemoveTrack(
      webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver) override {
    conn->OnRemoveTrack(receiver);
  }
  void OnDataChannel(std::string label) override {
    conn->OnDataChannel(std::move(label));
  }
};

#endif
