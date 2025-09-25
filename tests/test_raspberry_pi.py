import os
import time

import pytest
from client import (
    SoraClient,
    SoraRole,
    codec_type_string_to_codec_type,
)

from sora_sdk import (
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
    get_video_codec_capability,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RASPBERRY_PI") is None, reason="Raspberry Pi でのみ実行する"
)


def test_intel_vpl_available():
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
