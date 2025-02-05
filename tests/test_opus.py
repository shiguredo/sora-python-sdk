import sys
import time
import uuid

import pytest
from client import SoraClient, SoraRole

# opus params のテストは test_signaling.py にある


# 失敗する前提のテスト、成功したらエラーになる
@pytest.mark.xfail(
    reason="Opus の mono/16khz は SDP で指定すると正常に libwebrtc が動作しない", strict=True
)
def test_sendonly_audio_opus_params_16khz_mono(setup):
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
            "channels": 1,
            "stereo": False,
            "maxplaybackrate": 16000,
            "sprop_stereo": False,
        },
        video=False,
        metadata=metadata,
    ) as sendonly:
        time.sleep(5)

        assert sendonly.connect_message is not None
        assert "audio" in sendonly.connect_message
        assert "opus_params" in sendonly.connect_message["audio"]

        print(sendonly.connect_message)

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
