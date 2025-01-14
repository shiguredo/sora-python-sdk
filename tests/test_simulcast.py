import os
import sys
import time
import uuid

import pytest
from client import SoraClient, SoraRole


@pytest.mark.skipif(
    os.getenv("CI") == "true" and sys.platform == "darwin", reason="darwin では実行しない"
)
@pytest.mark.parametrize(
    (
        "video_codec_type",
        "encoder_implementation",
        "video_bit_rate",
        "video_width",
        "video_height",
        "simulcast_count",
    ),
    [
        # AV1 は VP8 と同じビットレートとして扱う
        # https://source.chromium.org/chromium/chromium/src/+/main:third_party/webrtc/video/config/simulcast.cc;l=219-222
        # 1080p
        ("VP8", "libvpx", 5000, 1920, 1080, 3),
        ("VP9", "libvpx", 3367, 1920, 1080, 3),
        ("AV1", "libaom", 5000, 1920, 1080, 3),
        # 720p
        ("VP8", "libvpx", 2500, 1280, 720, 3),
        ("VP9", "libvpx", 1524, 1280, 720, 3),
        ("AV1", "libaom", 2500, 1280, 720, 3),
        # 540p
        ("VP8", "libvpx", 1200, 960, 540, 3),
        ("VP9", "libvpx", 879, 960, 540, 3),
        ("AV1", "libaom", 1200, 960, 540, 3),
        # 360p
        ("VP8", "libvpx", 700, 640, 360, 2),
        ("VP9", "libvpx", 420, 640, 360, 2),
        ("AV1", "libaom", 700, 640, 360, 2),
        # 270p
        ("VP8", "libvpx", 450, 480, 270, 2),
        ("VP9", "libvpx", 257, 480, 270, 2),
        ("AV1", "libaom", 450, 480, 270, 2),
        # 180p
        ("VP8", "libvpx", 200, 320, 180, 1),
        ("VP9", "libvpx", 142, 320, 180, 1),
        ("AV1", "libaom", 200, 320, 180, 1),
        # 135p
        ("VP9", "libvpx", 101, 240, 135, 1),
    ],
)
def test_simulcast(
    setup,
    video_codec_type,
    encoder_implementation,
    video_bit_rate,
    video_width,
    video_height,
    simulcast_count,
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
        assert s["rid"] == f"r{i}"
        # simulcast_count が 2 の場合、rid r2 の bytesSent/packetsSent は 0 or 1 になる
        # simulcast_count が 1 の場合、rid r2 と r1 の bytesSent/packetsSent は 0 or 1 になる
        if i < simulcast_count:
            # 1 本になると simulcastEncodingAdapter がなくなる
            if simulcast_count > 1:
                assert "SimulcastEncoderAdapter" in s["encoderImplementation"]
            assert encoder_implementation in s["encoderImplementation"]

            assert s["bytesSent"] > 500
            assert s["packetsSent"] > 10
            # targetBitrate が指定したビットレートの 90% 以上、100% 以下に収まることを確認
            expected_bitrate = video_bit_rate * 1000
            print(
                s["rid"],
                video_codec_type,
                encoder_implementation,
                expected_bitrate,
                s["targetBitrate"],
                s["frameWidth"],
                s["frameHeight"],
                s["bytesSent"],
                s["packetsSent"],
            )
            # 期待値の 20% 以上、100% 以下に収まることを確認
            assert expected_bitrate * 0.2 <= s["targetBitrate"] <= expected_bitrate
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
