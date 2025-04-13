import sys
import time
import uuid

import pytest
from client import SoraClient, SoraRole

from sora_sdk import (
    Sora,
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
    get_video_codec_capability,
)


def test_openh264_get_codec_capability(setup):
    openh264_path = setup.get("openh264_path")
    capability = get_video_codec_capability(openh264_path)

    cisco_openh264_available = False

    for e in capability.engines:
        if e.name == SoraVideoCodecImplementation.CISCO_OPENH264:
            cisco_openh264_available = True
    assert cisco_openh264_available is True

    codecs = []
    for e in capability.engines:
        # macOS では INTERNAL の Video Toolbox が利用されるので OpenH264 は採用しないようにする
        if sys.platform == "darwin":
            if e.name == SoraVideoCodecImplementation.CISCO_OPENH264:
                continue

        for c in e.codecs:
            if c.decoder or c.encoder:
                # encoder/decoder どちらかが true であれば採用する
                if c.decoder or c.encoder:
                    codecs.append(
                        SoraVideoCodecPreference.Codec(
                            type=c.type,
                            decoder=e.name,
                            encoder=e.name,
                        )
                    )

    # エラーにならないことを確認する
    Sora(
        video_codec_preference=SoraVideoCodecPreference(
            codecs=codecs,
        ),
        openh264=openh264_path,
    )


def test_openh264_video_codec_preference(setup):
    openh264_path = setup.get("openh264_path")
    Sora(
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.VP8,
                    decoder=SoraVideoCodecImplementation.INTERNAL,
                    encoder=SoraVideoCodecImplementation.INTERNAL,
                ),
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.VP9,
                    decoder=SoraVideoCodecImplementation.INTERNAL,
                    encoder=SoraVideoCodecImplementation.INTERNAL,
                ),
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.AV1,
                    decoder=SoraVideoCodecImplementation.INTERNAL,
                    encoder=SoraVideoCodecImplementation.INTERNAL,
                ),
                # H.264 だけは OpenH264 を利用するようにする
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.H264,
                    decoder=SoraVideoCodecImplementation.CISCO_OPENH264,
                    encoder=SoraVideoCodecImplementation.CISCO_OPENH264,
                ),
            ],
        ),
        openh264=openh264_path,
    )


def test_openh264_sendonly_recvonly(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    openh264_path = setup.get("openh264_path")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        metadata=metadata,
        audio=False,
        video=True,
        video_codec_type="H264",
        openh264_path=openh264_path,
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

    recvonly = SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        metadata=metadata,
        openh264_path=openh264_path,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.H264,
                    decoder=SoraVideoCodecImplementation.CISCO_OPENH264,
                )
            ]
        ),
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


@pytest.mark.parametrize(
    (
        "video_codec_type",
        "expected_implementation",
        "video_bit_rate",
        "video_width",
        "video_height",
        "simulcast_count",
    ),
    [
        # 1080p
        ("H264", "OpenH264", 5000, 1920, 1080, 3),
        # 720p
        ("H264", "OpenH264", 2500, 1280, 720, 3),
        # 540p
        ("H264", "OpenH264", 1200, 960, 540, 3),
        # 360p
        ("H264", "OpenH264", 700, 640, 360, 2),
        # 270p
        ("H264", "OpenH264", 450, 480, 270, 2),
        # 180p
        ("H264", "OpenH264", 200, 320, 180, 1),
    ],
)
def test_openh264_simulcast(
    setup,
    video_codec_type,
    expected_implementation,
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
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        video_bit_rate=video_bit_rate,
        metadata=metadata,
        video_width=video_width,
        video_height=video_height,
        openh264_path=openh264_path,
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

    time.sleep(5)

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
        assert s["rid"] == f"r{i}"
        # simulcast_count が 2 の場合、rid r2 の bytesSent/packetsSent は 0 or 1 になる
        # simulcast_count が 1 の場合、rid r2 と r1 の bytesSent/packetsSent は 0 or 1 になる
        if i < simulcast_count:
            # 1 本になると simulcastEncodingAdapter がなくなる
            if simulcast_count > 1:
                assert "SimulcastEncoderAdapter" in s["encoderImplementation"]
            assert expected_implementation in s["encoderImplementation"]

            assert s["bytesSent"] > 500
            assert s["packetsSent"] > 20

            scalability_mode = None
            if "scalabilityMode" in s:
                assert s["scalabilityMode"] == "L1T1"
                scalability_mode = s["scalabilityMode"]

            # targetBitrate が指定したビットレートの 90% 以上、100% 以下に収まることを確認
            expected_bitrate = video_bit_rate * 1000
            print(
                s["rid"],
                video_codec_type,
                expected_implementation,
                scalability_mode,
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
