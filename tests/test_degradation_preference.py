import sys
import time
import uuid

from client import SoraClient, SoraDegradationPreference, SoraRole


def test_degradation_preference_maintain_framerate(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=False,
        video=True,
        video_codec_type="VP8",
        video_bit_rate=100,
        metadata=metadata,
        video_width=1280,
        video_height=720,
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
    assert outbound_rtp_stats["frameWidth"] <= 320
    assert outbound_rtp_stats["frameHeight"] <= 180
    # ビットレートが 100 kbps 以下
    assert outbound_rtp_stats["targetBitrate"] < 100_000
    # 20 以上を維持してる
    assert outbound_rtp_stats["framesPerSecond"] > 20

    print(
        outbound_rtp_stats["frameWidth"],
        outbound_rtp_stats["frameHeight"],
        outbound_rtp_stats["framesPerSecond"],
        outbound_rtp_stats["targetBitrate"],
    )


def test_degradation_preference_maintain_resolution(setup):
    """
    フレームレートがあまり変わらない
    """
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=False,
        video=True,
        video_codec_type="VP8",
        video_bit_rate=100,
        metadata=metadata,
        video_width=1280,
        video_height=720,
        degradation_preference=SoraDegradationPreference.MAINTAIN_RESOLUTION,
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
    # 解像度が維持されてる
    assert outbound_rtp_stats["frameWidth"] == 1280
    assert outbound_rtp_stats["frameHeight"] == 720
    # ビットレートが 100 kbps 以下
    assert outbound_rtp_stats["targetBitrate"] < 100_000

    print(
        outbound_rtp_stats["frameWidth"],
        outbound_rtp_stats["frameHeight"],
        outbound_rtp_stats["framesPerSecond"],
        outbound_rtp_stats["targetBitrate"],
    )


def test_degradation_preference_balanced(setup):
    """
    バランス思った以上に両方悪くなる
    """
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=False,
        video=True,
        video_codec_type="VP8",
        video_bit_rate=100,
        metadata=metadata,
        video_width=1280,
        video_height=720,
        degradation_preference=SoraDegradationPreference.BALANCED,
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
    assert outbound_rtp_stats["frameWidth"] <= 320
    assert outbound_rtp_stats["frameHeight"] <= 180
    # ビットレートが 100 kbps 以下
    assert outbound_rtp_stats["targetBitrate"] < 100_000
    # フレームレートが 20 未満
    assert outbound_rtp_stats["framesPerSecond"] < 20

    print(
        outbound_rtp_stats["frameWidth"],
        outbound_rtp_stats["frameHeight"],
        outbound_rtp_stats["framesPerSecond"],
        outbound_rtp_stats["targetBitrate"],
    )


def test_degradation_preference_disabled(setup):
    """
    無効にする
    """
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=False,
        video=True,
        video_codec_type="VP8",
        video_bit_rate=100,
        metadata=metadata,
        video_width=1280,
        video_height=720,
        degradation_preference=SoraDegradationPreference.DISABLED,
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
    assert outbound_rtp_stats["frameWidth"] == 1280
    assert outbound_rtp_stats["frameHeight"] == 720
    # ビットレートが 100 kbps 以下
    assert outbound_rtp_stats["targetBitrate"] < 100_000
    # フレームレートが 20 以上
    assert outbound_rtp_stats["framesPerSecond"] >= 20

    print(
        outbound_rtp_stats["frameWidth"],
        outbound_rtp_stats["frameHeight"],
        outbound_rtp_stats["framesPerSecond"],
        outbound_rtp_stats["targetBitrate"],
    )
