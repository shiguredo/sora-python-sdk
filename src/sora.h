#ifndef SORA_H_
#define SORA_H_

#include <memory>
#include <optional>
#include <vector>

#include "dispose_listener.h"
#include "sora_audio_source.h"
#include "sora_connection.h"
#include "sora_factory.h"
#include "sora_track_interface.h"
#include "sora_video_source.h"

/**
 * Sora Python SDK のベースになるクラスです。
 * 
 * SoraFactory を内包し Connection や AudioSource、VideoSource を生成します。
 * 一つの Sora インスタンスから複数の Connection、AudioSource、VideoSource が生成できます。
 * 同じ Sora インスタンス内でしか Connection や AudioSource、VideoSource を共有できないので、
 * 複数の Sora インスタンスを生成することは不具合の原因になります。
 */
class Sora : public DisposePublisher {
 public:
  Sora(std::optional<bool> use_hardware_encoder,
       std::optional<std::string> openh264);
  ~Sora();

  /**
   * Sora と接続する Connection を生成します。
   * 
   * 実装上の留意点：Sora C++ SDK が observer に std::weak_ptr を要求するためポインタで返す Source とは異なり、
   * std::shared_ptr で返しますが Python での扱いは変わりません。
   * 
   * @return SoraConnection インスタンス
   */
  std::shared_ptr<SoraConnection> CreateConnection(
      // 必須パラメータ
      const nb::handle& signaling_urls,
      const std::string& role,
      const std::string& channel_id,

      // オプショナルパラメータ
      // （Python 側で省略するか None が指定された場合には C++ SDK のデフォルト値が使われる）
      std::optional<std::string> client_id,
      std::optional<std::string> bundle_id,
      const nb::handle& metadata,
      const nb::handle& signaling_notify_metadata,
      SoraTrackInterface* audio_source,
      SoraTrackInterface* video_source,
      std::optional<bool> audio,
      std::optional<bool> video,
      std::optional<std::string> audio_codec_type,
      std::optional<std::string> video_codec_type,
      std::optional<int> video_bit_rate,
      std::optional<int> audio_bit_rate,
      const nb::handle& video_vp9_params,
      const nb::handle& video_av1_params,
      const nb::handle& video_h264_params,
      std::optional<bool> simulcast,
      std::optional<bool> spotlight,
      std::optional<int> spotlight_number,
      std::optional<std::string> simulcast_rid,
      std::optional<std::string> spotlight_focus_rid,
      std::optional<std::string> spotlight_unfocus_rid,
      const nb::handle& forwarding_filter,
      const nb::handle& data_channels,
      std::optional<bool> data_channel_signaling,
      std::optional<bool> ignore_disconnect_websocket,
      std::optional<int> data_channel_signaling_timeout,
      std::optional<int> disconnect_wait_timeout,
      std::optional<int> websocket_close_timeout,
      std::optional<int> websocket_connection_timeout,
      std::optional<int> audio_codec_lyra_bitrate,
      std::optional<bool> audio_codec_lyra_usedtx,
      std::optional<bool> check_lyra_version,
      std::optional<std::string> audio_streaming_language_code,
      std::optional<bool> insecure,
      std::optional<std::string> client_cert,
      std::optional<std::string> client_key,
      std::optional<std::string> proxy_url,
      std::optional<std::string> proxy_username,
      std::optional<std::string> proxy_password,
      std::optional<std::string> proxy_agent);

  /**
   * Sora に音声データを送る受け口である SoraAudioSource を生成します。
   * 
   * AudioSource に音声データを渡すことで、 Sora に音声を送ることができます。
   * AudioSource は MediaStreamTrack として振る舞うため、
   * AudioSource と同一の Sora インスタンスから生成された複数の Connection で共用できます。
   * 
   * @param channels AudioSource に入力する音声データのチャネル数
   * @param sample_rate AudioSource に入力する音声データのサンプリングレート
   * @return SoraAudioSource インスタンス
   */
  SoraAudioSource* CreateAudioSource(size_t channels, int sample_rate);
  /**
   * Sora に映像データを送る受け口である SoraVideoSource を生成します。
   * 
   * VideoSource にフレームデータを渡すことで、 Sora に映像を送ることができます。
   * VideoSource は MediaStreamTrack として振る舞うため、
   * VideoSource と同一の Sora インスタンスから生成された複数の Connection で共用できます。
   * 
   * @return SoraVideoSource インスタンス
   */
  SoraVideoSource* CreateVideoSource();

 private:
  boost::json::value ConvertJsonValue(nb::handle value,
                                      const char* error_message);
  std::vector<sora::SoraSignalingConfig::DataChannel> ConvertDataChannels(
      const nb::handle value);
  std::vector<std::string> ConvertSignalingUrls(const nb::handle value);

  boost::optional<sora::SoraSignalingConfig::ForwardingFilter>
  ConvertForwardingFilter(const nb::handle value);

  std::unique_ptr<SoraFactory> factory_;
};
#endif
