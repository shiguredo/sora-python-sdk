import os
import sys
import time
import uuid

import pytest
from client import SoraClient, SoraRole


@pytest.mark.skipif(os.environ.get("INTEL_VPL") is None, reason="Intel VPL でのみ実行する")
@pytest.mark.parametrize(
    (
        "video_codec_type",
        "encoder_implementation",
    ),
    [
        # encoder_implementation は適当です
        ("H264", "VPL"),
        ("H265", "VPL"),
    ],
)
def test_intel_vpl_video_hwa_sendonly(setup, video_codec_type, encoder_implementation):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        metadata=metadata,
        use_hwa=True,
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    assert sendonly.connect_message is not None
    assert sendonly.connect_message["channel_id"] == channel_id
    assert "video" in sendonly.connect_message
    assert sendonly.connect_message["video"]["codec_type"] == video_codec_type

    # offer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.offer_message is not None
    assert "sdp" in sendonly.offer_message
    assert video_codec_type in sendonly.offer_message["sdp"]

    # answer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert video_codec_type in sendonly.answer_message["sdp"]

    sendonly_stats = sendonly.get_stats()
    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    # H.264 が採用されているかどうか確認する
    assert codec_stats["mimeType"] == f"video/{video_codec_type}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == encoder_implementation
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
