#ifndef SORA_H_
#define SORA_H_

#include <memory>
#include <optional>
#include <vector>

#include "dispose_listener.h"
#include "sora_audio_source.h"
#include "sora_connection.h"
#include "sora_factory.h"
#include "sora_frame_transformer.h"
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
  /**
   * このタイミングで SoraFactory の生成まで行うため SoraFactory の生成にあたって必要な引数はここで設定します。
   * 
   * @param use_hardware_encoder (オプション)ハードウェアエンコーダーの有効無効 デフォルト: true
   * @param openh264 (オプション) OpenH264 ライブラリへのパス
   */
  Sora(std::optional<bool> use_hardware_encoder,
       std::optional<std::string> openh264);
  ~Sora();

  /**
   * Sora と接続する Connection を生成します。
   * 
   * 実装上の留意点：Sora C++ SDK が observer に std::weak_ptr を要求するためポインタで返す Source とは異なり、
   * std::shared_ptr で返しますが Python での扱いは変わりません。
   * 
   * @param signaling_urls シグナリングに使用する URL のリスト
   * @param role ロール recvonly | sendonly | sendrecv
   * @param channel_id チャネル ID
   * @param client_id (オプション)クライアント ID
   * @param bundle_id (オプション)バンドル ID
   * @param metadata (オプション)認証メタデータ
   * @param signaling_notify_metadata (オプション)シグナリング通知メタデータ
   * @param audio_source (オプション)音声ソース CreateAudioSource で生成した SoraAudioSource を渡してください
   * @param video_source (オプション)映像ソース CreateVideoSource で生成した SoraVideoSource を渡してください
   * @param audio_frame_transformer (オプション)音声送信時の Encoded Transform
   * @param video_frame_transformer (オプション)映像送信時の Encoded Transform
   * @param audio (オプション)音声の有効無効 デフォルト: true
   * @param video (オプション)映像の有効無効 デフォルト: true
   * @param audio_codec_type (オプション)音声コーデック OPUS デフォルト: OPUS
   * @param video_codec_type (オプション)映像コーデック VP8 | VP9 | AV1 | H264 デフォルト: VP9
   * @param video_bit_rate (オプション)映像ビットレート kbps 単位です
   * @param audio_bit_rate (オプション)音声ビットレート kbps 単位です
   * @param video_vp9_params (オプション)映像コーデック VP9 設定
   * @param video_av1_params (オプション)映像コーデック AV1 設定
   * @param video_h264_params (オプション)映像コーデック H264 設定
   * @param audio_opus_params (オプション)音声コーデック OPUS 設定
   * @param simulcast (オプション)サイマルキャストの有効無効
   * @param spotlight (オプション)スポットライトの有効無効
   * @param spotlight_number (オプション)スポットライトのフォーカス数
   * @param simulcast_rid (オプション)サイマルキャストで受信したい RID
   * @param spotlight_focus_rid (オプション)スポットライトでフォーカスしているときのサイマルキャスト RID
   * @param spotlight_unfocus_rid (オプション)スポットライトでフォーカスしていないときのサイマルキャスト RID
   * @param forwarding_filter (オプション)転送フィルター設定
   * @param data_channels (オプション) DataChannel 設定
   * @param data_channel_signaling (オプション)シグナリングを DataChannel に切り替える機能の有効無効
   * @param ignore_disconnect_websocket (オプション)シグナリングを DataChannel に切り替えた際に WebSocket が切断されても切断としない機能の有効無効
   * @param data_channel_signaling_timeout (オプション) DataChannel シグナリングタイムアウト
   * @param disconnect_wait_timeout (オプション) 切断待ちタイムアウト
   * @param websocket_close_timeout (オプション) WebSocket クローズタイムアウト
   * @param websocket_connection_timeout (オプション) WebSocket 接続タイムアウト
   * @param audio_streaming_language_code (オプション) 音声ストリーミング機能で利用する言語コード設定
   * @param insecure (オプション) 証明書チェックの有効無効 デフォルト: false
   * @param client_cert (オプション) クライアント証明書
   * @param client_key (オプション) クライアントシークレットキー
   * @param ca_cert (オプション) サーバー証明書チェック用の CA 証明書
   * @param proxy_url (オプション) Proxy URL
   * @param proxy_username (オプション) Proxy ユーザー名
   * @param proxy_password (オプション) Proxy パスワード
   * @param proxy_agent (オプション) Proxy エージェント
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
      SoraAudioFrameTransformer* audio_frame_transformer,
      SoraVideoFrameTransformer* video_frame_transformer,
      std::optional<bool> audio,
      std::optional<bool> video,
      std::optional<std::string> audio_codec_type,
      std::optional<std::string> video_codec_type,
      std::optional<int> video_bit_rate,
      std::optional<int> audio_bit_rate,
      const nb::handle& video_vp9_params,
      const nb::handle& video_av1_params,
      const nb::handle& video_h264_params,
      const nb::handle& audio_opus_params,
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
      std::optional<std::string> audio_streaming_language_code,
      std::optional<bool> insecure,
      std::optional<nb::bytes> client_cert,
      std::optional<nb::bytes> client_key,
      std::optional<nb::bytes> ca_cert,
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
  /**
   * Python で渡された値を boost::json::value に変換します。
   * 
   * metadata のように JSON の値として扱える内容であれば自由に指定できるものを、
   * nanobind::handle で受け取って Sora C++ SDK で使っている boost::json::value に変換します。
   * 
   * @param value Python から渡された値の nanobind::handle
   * @param error_message 変換に失敗した際に nanobind::type_error で返す際のエラーメッセージ
   * @return boost::json::value
   */
  boost::json::value ConvertJsonValue(nb::handle value,
                                      const char* error_message);
  std::vector<sora::SoraSignalingConfig::DataChannel> ConvertDataChannels(
      const nb::handle value);
  std::vector<std::string> ConvertSignalingUrls(const nb::handle value);

  std::optional<sora::SoraSignalingConfig::ForwardingFilter>
  ConvertForwardingFilter(const nb::handle value);

  std::unique_ptr<SoraFactory> factory_;
};
#endif
