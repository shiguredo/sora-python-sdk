import sys
import time
import uuid

from client import Sendonly


def test_sendonly(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = Sendonly(
        signaling_urls,
        channel_id,
        metadata,
        video_codec_type="VP8",
    )
    sendonly.connect()

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()

    # codec が無かったら StopIteration 例外が上がる
    codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert codec_stats["mimeType"] == "video/VP8"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    sendonly.disconnect()
