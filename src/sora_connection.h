#ifndef SORA_CONNECTION_H_
#define SORA_CONNECTION_H_

#include <memory>
#include <thread>

// nonobind
#include <nanobind/nanobind.h>
#include <nanobind/stl/shared_ptr.h>

// Boost
#include <boost/asio/io_context.hpp>

// WebRTC
#include <api/media_stream_interface.h>
#include <api/rtp_sender_interface.h>

// Sora
#include <sora/sora_signaling.h>

#include "dispose_listener.h"
#include "sora_track_interface.h"

namespace nb = nanobind;

/**
 * Sora との接続ごとに生成する SoraConnection です。
 * 
 * Python に Connection を制御する関数を提供します。
 */
class SoraConnection : public sora::SoraSignalingObserver,
                       public DisposePublisher,
                       public DisposeSubscriber {
 public:
  /**
   * コンストラクタではインスタンスの生成のみで実際の生成処理は Init 関数で行います。
   */
  SoraConnection(DisposePublisher* publisher);
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
  void SetAudioTrack(SoraTrackInterface* audio_source);
  /**
   * 映像トラックを入れ替える javascript でいう replaceTrack に相当する関数です。
   * 
   * TODO(tnoho): Python で呼び出すことを想定しているが、動作確認していないため NB_MODULE に定義していない
   * 
   * @param audio_source 入れ替える新しい映像トラック
   */
  void SetVideoTrack(SoraTrackInterface* video_source);
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
  void OnSetOffer(std::string offer) override;
  void OnDisconnect(sora::SoraSignalingErrorCode ec,
                    std::string message) override;
  void OnNotify(std::string text) override;
  void OnPush(std::string text) override;
  void OnMessage(std::string label, std::string data) override;
  void OnSwitched(std::string text) override;
  void OnSignaling(std::string text) override;
  void OnTrack(
      rtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) override;
  void OnRemoveTrack(
      rtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver) override;
  void OnDataChannel(std::string label) override;

  // sora::SoraSignalingObserver のコールバック関数が呼び出された時に対応して呼び出す Python の関数を保持する
  std::function<void(std::string)> on_signaling_;
  std::function<void(std::string)> on_set_offer_;
  std::function<void(sora::SoraSignalingErrorCode, std::string)> on_disconnect_;
  std::function<void(std::string)> on_notify_;
  std::function<void(std::string)> on_push_;
  std::function<void(std::string, nb::bytes)> on_message_;
  std::function<void(std::string)> on_switched_;
  std::function<void(std::shared_ptr<SoraMediaTrack>)> on_track_;
  std::function<void(std::string)> on_data_channel_;

 private:
  DisposePublisher* publisher_;
  std::unique_ptr<boost::asio::io_context> ioc_;
  std::shared_ptr<sora::SoraSignaling> conn_;
  std::unique_ptr<std::thread> thread_;
  // javascript でいう replaceTrack された際に RemoveSubscriber を呼び出すために参照を保持する
  SoraTrackInterface* audio_source_ = nullptr;
  SoraTrackInterface* video_source_ = nullptr;
  // javascript でいう replaceTrack を実装するために webrtc::RtpSenderInterface の参照を保持する
  rtc::scoped_refptr<webrtc::RtpSenderInterface> audio_sender_;
  rtc::scoped_refptr<webrtc::RtpSenderInterface> video_sender_;
};

#endif
