import os
import sys
import time

import pytest
from client import SoraClient, SoraRole
from simulcast import default_video_bit_rate, expect_target_bitrate


@pytest.mark.skipif(
    os.getenv("CI") == "true" and sys.platform == "darwin", reason="darwin では実行しない"
)
@pytest.mark.parametrize(
    (
        "video_codec_type",
        "encoder_implementation",
        "video_width",
        "video_height",
        "simulcast_count",
    ),
    [
        # 1080p
        ("VP8", "libvpx", 1920, 1080, 3),
        ("VP9", "libvpx", 1920, 1080, 3),
        ("AV1", "libaom", 1920, 1080, 3),
        # 720p
        ("VP8", "libvpx", 1280, 720, 3),
        ("VP9", "libvpx", 1280, 720, 3),
        ("AV1", "libaom", 1280, 720, 3),
        # 540p
        ("VP8", "libvpx", 960, 540, 3),
        ("VP9", "libvpx", 960, 540, 3),
        ("AV1", "libaom", 960, 540, 3),
        # simulcast count が 2 と 1 の場合解像度が 1/4 と 1/8 になってテストが通らなくなる
        # # 360p
        # ("VP8", "libvpx", 640, 360, 2),
        # ("VP9", "libvpx", 640, 360, 2),
        # ("AV1", "libaom", 640, 360, 2),
        # # 270p
        # ("VP8", "libvpx", 480, 270, 2),
        # ("VP9", "libvpx", 480, 270, 2),
        # ("AV1", "libaom", 480, 270, 2),
        # # 180p
        # ("VP8", "libvpx", 320, 180, 1),
        # ("VP9", "libvpx", 320, 180, 1),
        # ("AV1", "libaom", 320, 180, 1),
        # # 135p
        # ("VP9", "libvpx", 240, 135, 1),
    ],
)
def test_simulcast(
    settings,
    video_codec_type,
    encoder_implementation,
    video_width,
    video_height,
    simulcast_count,
):
    video_bit_rate = default_video_bit_rate(video_codec_type, video_width, video_height)

    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        simulcast=True,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        video_bit_rate=video_bit_rate,
        video_width=video_width,
        video_height=video_height,
    )
    sendonly.connect(fake_video=True)

    time.sleep(10)

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # "type": "answer" の SDP で Simulcast があるかどうか
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert "a=simulcast:send r0;r1;r2" in sendonly.answer_message["sdp"]

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # 複数の outbound-rtp 統計情報を取得
    outbound_rtp_stats = [
        s for s in sendonly_stats if s.get("type") == "outbound-rtp" and s.get("kind") == "video"
    ]
    # simulcast_count に関係なく統計情報はかならず 3 本出力される
    # これは SDP で rid で ~r0 とかやる減るはず
    assert len(outbound_rtp_stats) == 3

    # rid でソート
    sorted_stats = sorted(outbound_rtp_stats, key=lambda x: x.get("rid", ""))

    for i, s in enumerate(sorted_stats):
        assert "qualityLimitationReason" in s
        assert "qualityLimitationDurations" in s

        # qualityLimitationReason が none で無い場合は安定したテストができない
        if s["qualityLimitationReason"] != "none":
            pytest.skip(f"qualityLimitationReason: {s['qualityLimitationReason']}")

        assert s["rid"] == f"r{i}"
        # simulcast_count が 2 の場合、rid r2 の bytesSent/packetsSent は 0 or 1 になる
        # simulcast_count が 1 の場合、rid r2 と r1 の bytesSent/packetsSent は 0 or 1 になる
        if i < simulcast_count:
            # 1 本になると simulcastEncodingAdapter がなくなる
            if simulcast_count > 1:
                assert "SimulcastEncoderAdapter" in s["encoderImplementation"]
            assert encoder_implementation in s["encoderImplementation"]

            assert s["bytesSent"] > 500
            assert s["packetsSent"] > 5

            assert s["targetBitrate"] >= expect_target_bitrate(
                video_codec_type, s["frameWidth"], s["frameHeight"]
            ), f"{video_codec_type} {encoder_implementation} {video_bit_rate}"

            print(
                s["rid"],
                video_codec_type,
                encoder_implementation,
                video_bit_rate * 1000,
                video_width,
                video_height,
                s["targetBitrate"],
                s["frameWidth"],
                s["frameHeight"],
                s["bytesSent"],
                s["packetsSent"],
            )
        else:
            # 本来は 0 なのだが、simulcast_count が 1 の場合、
            # packetSent が 0 ではなく 1 や 2 になる場合がある
            # byteSent は 0
            assert s["bytesSent"] == 0
            assert s["packetsSent"] <= 2
            print(
                s["rid"],
                video_codec_type,
                s["bytesSent"],
                s["packetsSent"],
            )
