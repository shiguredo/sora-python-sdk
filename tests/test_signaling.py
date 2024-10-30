import sys
import time
import uuid

from client import SoraClient, SoraRole


def test_sendonly_audio_opus_params_none(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    with SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=True,
        audio_codec_type="OPUS",
        video=False,
        metadata=metadata,
    ) as sendonly:
        time.sleep(5)

        assert sendonly.connect_message is not None
        assert "audio" in sendonly.connect_message
        assert "opus_params" not in sendonly.connect_message["audio"]

        assert sendonly.offer_message is not None
        assert "sdp" in sendonly.offer_message
        ## usedtx=1 がない事を確認する
        assert "usedtx=1" not in sendonly.offer_message["sdp"]

        sendonly_stats = sendonly.get_stats()

        sendonly.disconnect()

        # codec が無かったら StopIteration 例外が上がる
        sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
        assert sendonly_codec_stats["mimeType"] == "audio/opus"

        # outbound-rtp が無かったら StopIteration 例外が上がる
        outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
        assert outbound_rtp_stats["bytesSent"] > 0
        assert outbound_rtp_stats["packetsSent"] > 0


def test_sendonly_audio_opus_params_usedtx_true(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    with SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=True,
        audio_codec_type="OPUS",
        audio_opus_params={
            "usedtx": True,
        },
        video=False,
        metadata=metadata,
    ) as sendonly:
        time.sleep(5)

        assert sendonly.connect_message is not None
        assert "audio" in sendonly.connect_message
        assert "opus_params" in sendonly.connect_message["audio"]
        assert "usedtx" in sendonly.connect_message["audio"]["opus_params"]
        assert sendonly.connect_message["audio"]["opus_params"]["usedtx"] is True

        assert sendonly.offer_message is not None
        assert "sdp" in sendonly.offer_message
        ## usedtx=1 がある事を確認する
        assert "usedtx=1" in sendonly.offer_message["sdp"]

        sendonly_stats = sendonly.get_stats()

        sendonly.disconnect()

        # codec が無かったら StopIteration 例外が上がる
        sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
        assert sendonly_codec_stats["mimeType"] == "audio/opus"

        # outbound-rtp が無かったら StopIteration 例外が上がる
        outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
        assert outbound_rtp_stats["bytesSent"] > 0
        assert outbound_rtp_stats["packetsSent"] > 0
