import os
import time

import pytest
from client import SoraClient, SoraRole
from simulcast import default_video_bit_rate, expect_target_bitrate

from sora_sdk import (
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("OPENH264_PATH") is None,
    reason="OpenH264 のときだけ実行する",
)


@pytest.mark.parametrize(
    (
        "video_codec_type",
        "expected_implementation",
        "video_width",
        "video_height",
        "simulcast_count",
    ),
    [
        # 1080p
        ("H264", "OpenH264", 1920, 1080, 3),
        # 720p
        ("H264", "OpenH264", 1280, 720, 3),
        # 540p
        ("H264", "OpenH264", 960, 540, 3),
    ],
)
def test_openh264_simulcast(
    settings,
    video_codec_type,
    expected_implementation,
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
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.H264,
                    encoder=SoraVideoCodecImplementation.CISCO_OPENH264,
                )
            ]
        ),
    )
    sendonly.connect(fake_video=True)

    time.sleep(10)

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

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
            assert expected_implementation in s["encoderImplementation"]

            assert s["bytesSent"] > 500
            assert s["packetsSent"] > 5

            assert s["targetBitrate"] >= expect_target_bitrate(
                video_codec_type, s["frameWidth"], s["frameHeight"]
            )

            scalability_mode = None
            if "scalabilityMode" in s:
                assert s["scalabilityMode"] == "L1T1"
                scalability_mode = s["scalabilityMode"]

            print(
                s["rid"],
                video_codec_type,
                expected_implementation,
                scalability_mode,
                video_bit_rate * 1000,
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


@pytest.mark.parametrize(
    (
        "video_codec_type",
        "expected_implementation",
        "video_width",
        "video_height",
    ),
    [
        # 360p
        ("H264", "OpenH264", 640, 360),
        # 270p
        ("H264", "OpenH264", 480, 270),
    ],
)
def test_openh264_authz_simulcast_r2_active_false(
    settings,
    video_codec_type,
    expected_implementation,
    video_width,
    video_height,
):
    video_bit_rate = default_video_bit_rate(video_codec_type, video_width, video_height)

    simulcast_encodings = [
        {
            "rid": "r0",
            "active": True,
            "scaleResolutionDownBy": 2,
            "scalabilityMode": "L1T1",
        },
        {
            "rid": "r1",
            "active": True,
            "scaleResolutionDownBy": 1,
            "scalabilityMode": "L1T1",
        },
        {
            "rid": "r2",
            "active": False,
        },
    ]

    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        simulcast=True,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        video_bit_rate=video_bit_rate,
        jwt_private_claims={
            "video": True,
            "video_codec_type": video_codec_type,
            "video_bit_rate": video_bit_rate,
            "simulcast": True,
            "simulcast_encodings": simulcast_encodings,
        },
        video_width=video_width,
        video_height=video_height,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.H264,
                    encoder=SoraVideoCodecImplementation.CISCO_OPENH264,
                )
            ]
        ),
    )
    sendonly.connect(fake_video=True)

    time.sleep(10)

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # 複数の outbound-rtp 統計情報を取得
    outbound_rtp_stats = [
        s
        for s in sendonly_stats
        if s.get("type") == "outbound-rtp" and s.get("kind") == "video" and s.get("active") is True
    ]
    # simulcast_count に関係なく統計情報はかならず 3 本出力される
    # これは SDP で rid で ~r0 とかやる減るはず
    assert len(outbound_rtp_stats) == 2

    # rid でソート
    sorted_stats = sorted(outbound_rtp_stats, key=lambda x: x.get("rid", ""))

    for i, s in enumerate(sorted_stats):
        assert "qualityLimitationReason" in s
        assert "qualityLimitationDurations" in s

        # qualityLimitationReason が none で無い場合は安定したテストができない
        if s["qualityLimitationReason"] != "none":
            pytest.skip(f"qualityLimitationReason: {s['qualityLimitationReason']}")

        assert s["rid"] == f"r{i}"
        print(s.get("encoderImplementation"))
        assert expected_implementation in s["encoderImplementation"]

        assert s["bytesSent"] > 500
        assert s["packetsSent"] > 5

        assert s["targetBitrate"] >= expect_target_bitrate(
            video_codec_type, s["frameWidth"], s["frameHeight"]
        )

        assert s["scalabilityMode"] == "L1T1"

        print(
            s["rid"],
            video_codec_type,
            expected_implementation,
            video_bit_rate * 1000,
            s["targetBitrate"],
            s["frameWidth"],
            s["frameHeight"],
            s["bytesSent"],
            s["packetsSent"],
        )


@pytest.mark.parametrize(
    (
        "video_codec_type",
        "expected_implementation",
        "video_width",
        "video_height",
    ),
    [
        # 180p
        ("H264", "OpenH264", 320, 180),
    ],
)
def test_openh264_authz_simulcast_r2_and_r1_active_false(
    settings,
    video_codec_type,
    expected_implementation,
    video_width,
    video_height,
):
    video_bit_rate = default_video_bit_rate(video_codec_type, video_width, video_height)

    simulcast_encodings = [
        {
            "rid": "r0",
            "active": True,
            "scaleResolutionDownBy": 1,
            "scalabilityMode": "L1T1",
        },
        {
            "rid": "r1",
            "active": False,
        },
        {
            "rid": "r2",
            "active": False,
        },
    ]

    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        simulcast=True,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        video_bit_rate=video_bit_rate,
        jwt_private_claims={
            "video": True,
            "video_codec_type": video_codec_type,
            "video_bit_rate": video_bit_rate,
            "simulcast": True,
            "simulcast_encodings": simulcast_encodings,
        },
        video_width=video_width,
        video_height=video_height,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.H264,
                    encoder=SoraVideoCodecImplementation.CISCO_OPENH264,
                )
            ]
        ),
    )
    sendonly.connect(fake_video=True)

    time.sleep(10)

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # 複数の outbound-rtp 統計情報を取得
    outbound_rtp_stats = [
        s
        for s in sendonly_stats
        if s.get("type") == "outbound-rtp" and s.get("kind") == "video" and s.get("active") is True
    ]
    # simulcast_count に関係なく統計情報はかならず 3 本出力される
    # これは SDP で rid で ~r0 とかやる減るはず
    assert len(outbound_rtp_stats) == 1

    # rid でソート
    sorted_stats = sorted(outbound_rtp_stats, key=lambda x: x.get("rid", ""))

    for i, s in enumerate(sorted_stats):
        assert "qualityLimitationReason" in s
        assert "qualityLimitationDurations" in s

        # qualityLimitationReason が none で無い場合は安定したテストができない
        if s["qualityLimitationReason"] != "none":
            pytest.skip(f"qualityLimitationReason: {s['qualityLimitationReason']}")

        assert s["rid"] == f"r{i}"
        print(s.get("encoderImplementation"))
        assert expected_implementation in s["encoderImplementation"]

        assert s["bytesSent"] > 500
        assert s["packetsSent"] > 5

        assert s["targetBitrate"] >= expect_target_bitrate(
            video_codec_type, s["frameWidth"], s["frameHeight"]
        )

        assert s["scalabilityMode"] == "L1T1"

        print(
            s["rid"],
            video_codec_type,
            expected_implementation,
            video_bit_rate * 1000,
            s["targetBitrate"],
            s["frameWidth"],
            s["frameHeight"],
            s["bytesSent"],
            s["packetsSent"],
        )
