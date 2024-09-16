import sys
import time
import uuid

import pytest
from client import Sendonly


@pytest.fixture(
    params=[
        ("VP8", "SimulcastEncoderAdapter (libvpx, libvpx, libvpx)"),
        ("VP9", "SimulcastEncoderAdapter (libvpx, libvpx, libvpx)"),
        ("AV1", "SimulcastEncoderAdapter (libaom, libaom, libaom)"),
    ]
)
def video_codec_params(request):
    return request.param


def test_simulcast(setup, video_codec_params):
    video_codec, expected_implementation = video_codec_params
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

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
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # "type": "answer" の SDP で Simulcast があるかどうか
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert "a=simulcast:send r0;r1;r2" in sendonly.answer_message["sdp"]

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
