import os
import sys
import time
import uuid

import pytest
from client import SoraClient, SoraRole

from sora_sdk import (
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
)


@pytest.mark.skipif(
    os.environ.get("SIMULCAST_MULTICODEC") is None,
    reason="サイマルキャストマルチコーデックが有効な場合のみ実行する",
)
@pytest.mark.parametrize(
    (
        "video_codecs",
        "video_bit_rate",
        "video_width",
        "video_height",
        "simulcast_count",
    ),
    [
        # 1080p
        ((("H264", "OpenH264"), ("VP9", "libvpx"), ("AV1", "libaom")), 5000, 1920, 1080, 3),
        # 720p
        ((("H264", "OpenH264"), ("VP9", "libvpx"), ("AV1", "libaom")), 2500, 1280, 720, 3),
        # 540p
        ((("H264", "OpenH264"), ("VP9", "libvpx"), ("AV1", "libaom")), 1200, 960, 540, 3),
        # 360p
        ((("H264", "OpenH264"), ("VP9", "libvpx"), ("AV1", "libaom")), 700, 640, 360, 3),
        # 270p
        ((("H264", "OpenH264"), ("VP9", "libvpx"), ("AV1", "libaom")), 450, 480, 270, 3),
        # 180p
        ((("H264", "OpenH264"), ("VP9", "libvpx"), ("AV1", "libaom")), 200, 320, 180, 3),
    ],
)
def test_simulcast_multicodec(
    setup,
    video_codecs,
    video_bit_rate,
    video_width,
    video_height,
    simulcast_count,
):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")
    openh264_path = setup.get("openh264_path")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        simulcast=True,
        simulcast_multicodec=True,
        audio=False,
        video=True,
        video_bit_rate=video_bit_rate,
        openh264_path=openh264_path,
        metadata=metadata,
        video_width=video_width,
        video_height=video_height,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.H264,
                    encoder=SoraVideoCodecImplementation.CISCO_OPENH264,
                ),
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.VP9,
                    encoder=SoraVideoCodecImplementation.INTERNAL,
                ),
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.AV1,
                    encoder=SoraVideoCodecImplementation.INTERNAL,
                ),
            ]
        ),
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
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codecs[0][0]}"

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
        # SimulcastEncoderAdapter (OpenH264, libvpx, libaom) のような文字列になってるはず
        assert "SimulcastEncoderAdapter" in s["encoderImplementation"]
        for _, encoder_implementation in video_codecs:
            assert encoder_implementation in s["encoderImplementation"]

        video_codec, encoder_implementation = video_codecs[i]

        assert s["bytesSent"] > 500
        assert s["packetsSent"] > 10
        # targetBitrate が指定したビットレートの 90% 以上、100% 以下に収まることを確認
        expected_bitrate = video_bit_rate * 1000
        print(
            s["rid"],
            video_codec,
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
