import sys
import time

from client import Sendonly


def test_macos_h26_sendonly(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}"

    sendonly = Sendonly(signaling_urls, channel_id, metadata, video_codec_type="H264")
    sendonly.connect()

    time.sleep(5)

    stats = sendonly.get_stats()

    # codec が無かったら StopIteration 例外が上がる
    codec_stats = next(s for s in stats if s.get("type") == "codec")
    # H.264 が採用されているかどうか確認する
    assert codec_stats["mimeType"] == "video/H264"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "VideoToolbox"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    sendonly.disconnect()


def test_macos_h265_sendonly(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}"

    sendonly = Sendonly(signaling_urls, channel_id, metadata, video_codec_type="H265")
    sendonly.connect()

    time.sleep(5)

    stats = sendonly.get_stats()

    # codec が無かったら StopIteration 例外が上がる
    codec_stats = next(s for s in stats if s.get("type") == "codec")
    # H.265 が採用されているかどうか確認する
    assert codec_stats["mimeType"] == "video/H265"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "VideoToolbox"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    sendonly.disconnect()
