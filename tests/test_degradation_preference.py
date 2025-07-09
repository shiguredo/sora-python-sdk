import os
import sys
import time

import pytest
from client import SoraClient, SoraDegradationPreference, SoraRole

VIDEO_CODEC_TYPE = "VP8"
VIDEO_BIT_RATE = 300
VIDEO_WIDTH = 960
VIDEO_HEIGHT = 528


@pytest.mark.skipif(
    os.getenv("CI") == "true" and sys.platform == "darwin",
    reason="CI の macOS では性能がでないためスキップする",
)
def test_degradation_preference_maintain_framerate(settings):
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type=VIDEO_CODEC_TYPE,
        video_bit_rate=VIDEO_BIT_RATE,
        video_width=VIDEO_WIDTH,
        video_height=VIDEO_HEIGHT,
        degradation_preference=SoraDegradationPreference.MAINTAIN_FRAMERATE,
    )
    sendonly.connect(fake_video=True)

    time.sleep(10)

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == "video/VP8"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
    assert outbound_rtp_stats["frameWidth"] <= 640
    assert outbound_rtp_stats["frameHeight"] <= 360
    # ビットレートが 500 kbps 以下
    assert outbound_rtp_stats["targetBitrate"] < VIDEO_BIT_RATE * 1000
    # 20 以上を維持してる
    assert outbound_rtp_stats["framesPerSecond"] > 20

    print(
        outbound_rtp_stats["frameWidth"],
        outbound_rtp_stats["frameHeight"],
        outbound_rtp_stats["framesPerSecond"],
        outbound_rtp_stats["targetBitrate"],
    )


@pytest.mark.skipif(
    os.getenv("CI") == "true" and sys.platform == "darwin",
    reason="CI の macOS では性能がでないためスキップする",
)
def test_degradation_preference_maintain_resolution(settings):
    """
    フレームレートがあまり変わらない
    """
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type=VIDEO_CODEC_TYPE,
        video_bit_rate=VIDEO_BIT_RATE,
        video_width=VIDEO_WIDTH,
        video_height=VIDEO_HEIGHT,
        degradation_preference=SoraDegradationPreference.MAINTAIN_RESOLUTION,
    )
    sendonly.connect(fake_video=True)

    time.sleep(10)

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{VIDEO_CODEC_TYPE}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
    # 解像度が維持されてる
    assert outbound_rtp_stats["frameWidth"] == VIDEO_WIDTH
    assert outbound_rtp_stats["frameHeight"] == VIDEO_HEIGHT
    # ビットレートが 500 kbps 以下
    assert outbound_rtp_stats["targetBitrate"] < VIDEO_BIT_RATE * 1000

    print(
        outbound_rtp_stats["frameWidth"],
        outbound_rtp_stats["frameHeight"],
        outbound_rtp_stats["framesPerSecond"],
        outbound_rtp_stats["targetBitrate"],
    )


@pytest.mark.skipif(
    os.getenv("CI") == "true" and sys.platform == "darwin",
    reason="CI の macOS では性能がでないためスキップする",
)
def test_degradation_preference_balanced(settings):
    """
    バランス思った以上に両方悪くなる
    """
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type=VIDEO_CODEC_TYPE,
        video_bit_rate=VIDEO_BIT_RATE,
        video_width=VIDEO_WIDTH,
        video_height=VIDEO_HEIGHT,
        degradation_preference=SoraDegradationPreference.BALANCED,
    )
    sendonly.connect(fake_video=True)

    time.sleep(10)

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{VIDEO_CODEC_TYPE}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
    assert outbound_rtp_stats["frameWidth"] <= 640
    assert outbound_rtp_stats["frameHeight"] <= 360
    # ビットレートが 500 kbps 未満
    assert outbound_rtp_stats["targetBitrate"] < VIDEO_BIT_RATE * 1000
    # フレームレートが 30 未満
    assert outbound_rtp_stats["framesPerSecond"] < 30

    print(
        outbound_rtp_stats["frameWidth"],
        outbound_rtp_stats["frameHeight"],
        outbound_rtp_stats["framesPerSecond"],
        outbound_rtp_stats["targetBitrate"],
    )


@pytest.mark.skipif(
    os.getenv("CI") == "true" and sys.platform == "darwin",
    reason="CI の macOS では性能がでないためスキップする",
)
def test_degradation_preference_disabled(settings):
    """
    無効にする
    """
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type=VIDEO_CODEC_TYPE,
        video_bit_rate=VIDEO_BIT_RATE,
        video_width=VIDEO_WIDTH,
        video_height=VIDEO_HEIGHT,
        degradation_preference=SoraDegradationPreference.DISABLED,
    )
    sendonly.connect(fake_video=True)

    time.sleep(10)

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{VIDEO_CODEC_TYPE}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
    assert outbound_rtp_stats["frameWidth"] == VIDEO_WIDTH
    assert outbound_rtp_stats["frameHeight"] == VIDEO_HEIGHT
    # ビットレートが 500 kbps 未満
    assert outbound_rtp_stats["targetBitrate"] < VIDEO_BIT_RATE * 1000
    # フレームレートが 30 未満
    assert outbound_rtp_stats["framesPerSecond"] < 30

    print(
        outbound_rtp_stats["frameWidth"],
        outbound_rtp_stats["frameHeight"],
        outbound_rtp_stats["framesPerSecond"],
        outbound_rtp_stats["targetBitrate"],
    )
