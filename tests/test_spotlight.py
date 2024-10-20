import sys
import time
import uuid

import pytest
from client import SoraClient, SoraRole


@pytest.mark.parametrize(
    ("video_codec_type", "expected_implementation"),
    [
        ("VP8", "SimulcastEncoderAdapter (libvpx, libvpx)"),
        ("VP9", "SimulcastEncoderAdapter (libvpx, libvpx)"),
        ("AV1", "SimulcastEncoderAdapter (libaom, libaom)"),
    ],
)
def test_spotlight_simulcast(setup, video_codec_type, expected_implementation):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendrecv1 = SoraClient(
        signaling_urls,
        SoraRole.SENDRECV,
        channel_id,
        audio=True,
        video=True,
        simulcast=True,
        spotlight=True,
        video_codec_type=video_codec_type,
        video_bit_rate=3000,
        video_width=1280,
        video_height=720,
        metadata=metadata,
    )
    sendrecv1.connect(fake_audio=True, fake_video=True)

    sendrecv2 = SoraClient(
        signaling_urls,
        SoraRole.SENDRECV,
        channel_id,
        audio=True,
        video=True,
        simulcast=True,
        spotlight=True,
        video_codec_type=video_codec_type,
        video_bit_rate=3000,
        video_width=1280,
        video_height=720,
        metadata=metadata,
    )
    sendrecv2.connect(fake_audio=True, fake_video=True)

    time.sleep(5)

    sendrecv1_stats = sendrecv1.get_stats()
    sendrecv2_stats = sendrecv2.get_stats()

    sendrecv1.disconnect()
    sendrecv2.disconnect()

    assert sendrecv1.connect_message is not None
    assert sendrecv1.connect_message.message["spotlight"] is True

    assert sendrecv2.connect_message is not None
    assert sendrecv2.connect_message.message["spotlight"] is True

    # codec が無かったら StopIteration 例外が上がる
    sendrecv1_codec_stats = next(
        s for s in sendrecv1_stats if s.get("type") == "codec" and s.get("mimeType") == "audio/opus"
    )
    assert sendrecv1_codec_stats["mimeType"] == "audio/opus"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(
        s for s in sendrecv1_stats if s.get("type") == "outbound-rtp" and s.get("kind") == "audio"
    )
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    sendrecv1_codec_stats = next(
        s
        for s in sendrecv1_stats
        if s.get("type") == "codec" and s.get("mimeType") == f"video/{video_codec_type}"
    )
    assert sendrecv1_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # 複数の outbound-rtp 統計情報を取得
    outbound_rtp_stats = [
        s for s in sendrecv1_stats if s.get("type") == "outbound-rtp" and s.get("kind") == "video"
    ]
    assert len(outbound_rtp_stats) == 3

    # rid でソート
    sorted_stats = sorted(outbound_rtp_stats, key=lambda x: x.get("rid", ""))
    for i, rtp_stat in enumerate(sorted_stats):
        assert rtp_stat["rid"] == f"r{i}"
        assert rtp_stat["encoderImplementation"] == expected_implementation
        if rtp_stat["rid"] in ["r0", "r1"]:
            assert rtp_stat["bytesSent"] > 0
            assert rtp_stat["packetsSent"] > 0
        else:
            assert rtp_stat["bytesSent"] == 0
            assert rtp_stat["packetsSent"] == 0
