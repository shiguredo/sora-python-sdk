import sys
import time
import uuid

from media import Sendrecv


def test_sendrecv(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendrecv1 = Sendrecv(
        signaling_urls,
        channel_id,
        audio=False,
        video=True,
        video_codec_type="VP8",
        metadata=metadata,
    )
    sendrecv1.connect(fake_video=True)

    sendrecv2 = Sendrecv(
        signaling_urls,
        channel_id,
        metadata=metadata,
    )
    sendrecv2.connect(fake_audio=True, fake_video=True)

    time.sleep(5)

    sendrecv1_stats = sendrecv1.get_stats()
    sendrecv2_stats = sendrecv2.get_stats()

    sendrecv1.disconnect()
    sendrecv2.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendrecv1_codec_stats = next(s for s in sendrecv1_stats if s.get("type") == "codec")
    assert sendrecv1_codec_stats["mimeType"] == "video/VP8"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    sendrecv1_outbound_rtp_stats = next(
        s for s in sendrecv1_stats if s.get("type") == "outbound-rtp"
    )
    assert sendrecv1_outbound_rtp_stats["encoderImplementation"] == "libvpx"
    assert sendrecv1_outbound_rtp_stats["bytesSent"] > 0
    assert sendrecv1_outbound_rtp_stats["packetsSent"] > 0

    # outbound-rtp が無かったら StopIteration 例外が上がる
    sendrecv1_inbound_rtp_stats = next(s for s in sendrecv1_stats if s.get("type") == "inbound-rtp")
    assert sendrecv1_inbound_rtp_stats["decoderImplementation"] == "libvpx"
    assert sendrecv1_inbound_rtp_stats["bytesReceived"] > 0
    assert sendrecv1_inbound_rtp_stats["packetsReceived"] > 0
