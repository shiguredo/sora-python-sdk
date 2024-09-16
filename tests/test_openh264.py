import sys
import time
import uuid

import pytest
from client import Recvonly, Sendonly


def test_openh264_sendonly_recvonly(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    openh264_path = setup.get("openh264_path")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = Sendonly(
        signaling_urls,
        channel_id,
        metadata=metadata,
        audio=False,
        video=True,
        video_codec_type="H264",
        openh264_path=openh264_path,
        use_hwa=False,
    )
    sendonly.connect(fake_video=True)

    recvonly = Recvonly(
        signaling_urls,
        channel_id,
        metadata=metadata,
        openh264_path=openh264_path,
        use_hwa=False,
    )
    recvonly.connect()

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    sendonly.disconnect()
    recvonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == "video/H264"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "OpenH264"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    assert recvonly_codec_stats["mimeType"] == "video/H264"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "OpenH264"
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0


@pytest.fixture(
    params=[
        ("H264", "SimulcastEncoderAdapter (OpenH264, OpenH264, OpenH264)"),
    ]
)
def video_codec_params(request):
    return request.param


def test_openh264_simulcast(setup, video_codec_params):
    video_codec, expected_implementation = video_codec_params
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    openh264_path = setup.get("openh264_path")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = Sendonly(
        signaling_urls,
        channel_id,
        simulcast=True,
        audio=False,
        video=True,
        video_codec_type=video_codec,
        video_bit_rate=3000,
        metadata=metadata,
        video_width=1280,
        video_height=720,
        openh264_path=openh264_path,
        use_hwa=False,
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec}"

    # 複数のoutbound-rtp統計情報を取得
    outbound_rtp_stats = [
        s for s in sendonly_stats if s.get("type") == "outbound-rtp" and s.get("kind") == "video"
    ]
    assert len(outbound_rtp_stats) == 3

    # rid でソート
    sorted_stats = sorted(outbound_rtp_stats, key=lambda x: x.get("rid", ""))

    for i, rtp_stat in enumerate(sorted_stats):
        assert rtp_stat["rid"] == f"r{i}"
        assert rtp_stat["encoderImplementation"] == expected_implementation
        assert rtp_stat["bytesSent"] > 0
        assert rtp_stat["packetsSent"] > 0
