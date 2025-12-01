import os
import time

import pytest
from client import (
    SoraClient,
    SoraRole,
    codec_type_string_to_codec_type,
)
from simulcast import default_video_bit_rate, expect_target_bitrate

from sora_sdk import (
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
    get_video_codec_capability,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RASPBERRY_PI") is None, reason="Raspberry Pi でのみ実行する"
)


def test_raspberry_pi_available():
    capability = get_video_codec_capability()

    intel_vpl_available = False
    for e in capability.engines:
        if e.name == SoraVideoCodecImplementation.RASPI_V4L2M2M:
            intel_vpl_available = True

    assert intel_vpl_available is True

    for e in capability.engines:
        if e.name == SoraVideoCodecImplementation.RASPI_V4L2M2M:
            # 対応コーデックは 5 種類
            assert len(e.codecs) == 5

            for c in e.codecs:
                match c.type:
                    case SoraVideoCodecType.VP8:
                        assert c.decoder is False
                        assert c.encoder is False
                    case SoraVideoCodecType.VP9:
                        assert c.decoder is False
                        assert c.encoder is False
                    case SoraVideoCodecType.AV1:
                        assert c.decoder is False
                        assert c.encoder is False
                    case SoraVideoCodecType.H264:
                        assert c.decoder is True
                        assert c.encoder is True
                    case SoraVideoCodecType.H265:
                        assert c.decoder is False
                        assert c.encoder is False
                    case _:
                        pytest.fail(f"未実装の codec_type: {c.type}")


def test_raspberry_pi_sendonly(settings):
    video_codec_type = "H264"
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=codec_type_string_to_codec_type(video_codec_type),
                    encoder=SoraVideoCodecImplementation.RASPI_V4L2M2M,
                ),
            ]
        ),
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    assert sendonly.connect_message is not None
    assert sendonly.connect_message["channel_id"] == settings.channel_id
    assert "video" in sendonly.connect_message
    assert sendonly.connect_message["video"]["codec_type"] == video_codec_type

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    # H.264 が採用されているかどうか確認する
    assert codec_stats["mimeType"] == f"video/{video_codec_type}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "V4L2M2M H264"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0


@pytest.mark.parametrize(
    (
        "video_width",
        "video_height",
        "simulcast_count",
    ),
    [
        # 1080p
        (1920, 1080, 3),
        # 720p
        (1280, 720, 3),
        # 540p
        (960, 540, 3),
        # 360p
        (640, 360, 2),
        # 270p
        (480, 270, 2),
        # 180p
        (320, 180, 1),
    ],
)
def test_raspberry_pi_simulcast(
    settings,
    video_width,
    video_height,
    simulcast_count,
):
    video_codec_type = "H264"
    expected_implementation = "V4L2M2M H264"

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
                    type=codec_type_string_to_codec_type(video_codec_type),
                    encoder=SoraVideoCodecImplementation.RASPI_V4L2M2M,
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
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # 複数の outbound-rtp 統計情報を取得
    outbound_rtp_stats = [
        s for s in sendonly_stats if s.get("type") == "outbound-rtp" and s.get("kind") == "video"
    ]
    # simulcast_count に関係なく統計情報はかならず 3 本出力される
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
            assert expected_implementation in s["encoderImplementation"]

            assert s["bytesSent"] > 500
            assert s["packetsSent"] > 5

            assert s["targetBitrate"] >= expect_target_bitrate(
                video_codec_type, s["frameWidth"], s["frameHeight"]
            )

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
        else:
            # 本来は 0 なのだが、simulcast_count が 1 の場合、
            # packetSent が 0 ではなく 1 や 2 になる場合がある
            # byteSent は 0
            print(
                s["rid"],
                video_codec_type,
                s["bytesSent"],
                s["packetsSent"],
            )
            assert s["bytesSent"] == 0
            assert s["packetsSent"] <= 2


def test_raspberry_pi_libcamera(settings):
    video_codec_type = "H264"
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=codec_type_string_to_codec_type(video_codec_type),
                    encoder=SoraVideoCodecImplementation.RASPI_V4L2M2M,
                ),
            ]
        ),
        libcamera=True,
        libcamera_controls=[("AfMode", "Auto")],
        native_frame_output=True,
        force_i420_conversion=False,
    )
    sendonly.connect(fake_video=False)

    time.sleep(5)

    assert sendonly.connect_message is not None
    assert sendonly.connect_message["channel_id"] == settings.channel_id
    assert "video" in sendonly.connect_message
    assert sendonly.connect_message["video"]["codec_type"] == video_codec_type

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    # H.264 が採用されているかどうか確認する
    assert codec_stats["mimeType"] == f"video/{video_codec_type}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "V4L2M2M H264"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
