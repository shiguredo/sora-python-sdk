import time

from client import SoraClient, SoraRole

# opus params のテストは test_signaling.py にある

# https://tex2e.github.io/rfc-translater/html/rfc7587.html


def test_sendonly_audio_opus_params_16khz_mono(settings):
    """
    SDP では 48000/2 だが、Opus の設定で 16000/1 を配信してみる
    """
    with SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=True,
        audio_codec_type="OPUS",
        audio_opus_params={
            #
            "maxplaybackrate": 16000,
            # 受信のみに有効
            "stereo": False,
            # 送信のみに有効
            "sprop_stereo": False,
        },
        video=False,
    ) as sendonly:
        time.sleep(5)

        assert sendonly.connect_message is not None
        assert "audio" in sendonly.connect_message
        assert "opus_params" in sendonly.connect_message["audio"]
        assert sendonly.connect_message["audio"]["opus_params"]["stereo"] is False
        assert sendonly.connect_message["audio"]["opus_params"]["maxplaybackrate"] == 16000
        assert sendonly.connect_message["audio"]["opus_params"]["sprop_stereo"] is False

        assert sendonly.offer_message is not None
        assert "sdp" in sendonly.offer_message

        assert "opus/48000/2" in sendonly.offer_message["sdp"]

        assert "maxplaybackrate=16000" in sendonly.offer_message["sdp"]
        assert "stereo=0" in sendonly.offer_message["sdp"]
        assert "sprop-stereo=0" in sendonly.offer_message["sdp"]

        sendonly_stats = sendonly.get_stats()

        sendonly.disconnect()

        # codec が無かったら StopIteration 例外が上がる
        sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
        assert sendonly_codec_stats["mimeType"] == "audio/opus"

        # outbound-rtp が無かったら StopIteration 例外が上がる
        outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
        assert outbound_rtp_stats["bytesSent"] > 0
        assert outbound_rtp_stats["packetsSent"] > 0
