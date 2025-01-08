import sys
import time
import uuid

import pytest
from client import SoraClient, SoraRole


@pytest.mark.parametrize(
    (
        "video_codec_type",
        "expected_implementation",
        "video_bit_rate",
        "video_width",
        "video_height",
    ),
    [
        # 720p
        ("VP8", "libvpx", 2500, 1280, 720),
        ("VP9", "libvpx", 1524, 1280, 720),
        ("AV1", "libaom", 1524, 1280, 720),
        # 540p
        ("VP8", "libvpx", 1200, 960, 540),
        ("VP9", "libvpx", 879, 960, 540),
        # AV1 は 879 だと 3 本でない
        ("AV1", "libaom", 1200, 960, 540),
    ],
)
def test_simulcast(
    setup, video_codec_type, expected_implementation, video_bit_rate, video_width, video_height
):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        simulcast=True,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        video_bit_rate=video_bit_rate,
        metadata=metadata,
        video_width=video_width,
        video_height=video_height,
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
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # 複数のoutbound-rtp統計情報を取得
    outbound_rtp_stats = [
        s for s in sendonly_stats if s.get("type") == "outbound-rtp" and s.get("kind") == "video"
    ]
    assert len(outbound_rtp_stats) == 3

    # rid でソート
    sorted_stats = sorted(outbound_rtp_stats, key=lambda x: x.get("rid", ""))

    for i, s in enumerate(sorted_stats):
        assert s["rid"] == f"r{i}"
        assert "SimulcastEncoderAdapter" in s["encoderImplementation"]
        assert expected_implementation in s["encoderImplementation"]
        assert s["bytesSent"] > 0
        assert s["packetsSent"] > 0
        # targetBitrate が指定したビットレートの 90% 以上、100% 以下に収まることを確認
        expected_bitrate = video_bit_rate * 1000
        print(
            s["rid"],
            video_codec_type,
            expected_bitrate,
            s["targetBitrate"],
            s["frameWidth"],
            s["frameHeight"],
        )
        # 期待値七割
        assert expected_bitrate * 0.7 <= s["targetBitrate"] <= expected_bitrate
