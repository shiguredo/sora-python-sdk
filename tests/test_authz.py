import time

import pytest
from client import SoraClient, SoraRole


@pytest.mark.skipif(reason="Sora C++ SDK 側の対応が必要")
def test_sendonly_authz_video_true(settings):
    """
    - type: connect で audio: true / video: false で繫ぐ
    - 認証成功時の払い出しで audio: false / video: true を払い出す
    """

    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=True,
        video=False,
        jwt_private_claims={
            "audio": True,
            "video": False,
        },
    )
    sendonly.connect(fake_video=False, fake_audio=True)

    time.sleep(5)

    assert sendonly.offer_message is not None
    assert sendonly.offer_message["sdp"] is not None
    assert "VP9" in sendonly.offer_message["sdp"]

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    # 統計で video が見つからないので謎挙動になってる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == "video/VP9"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "libvpx"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0


@pytest.mark.parametrize(
    ("video_codec_type", "expected_implementation"),
    [
        # video_codec, expected_implementation
        ("VP8", "libvpx"),
        ("VP9", "libvpx"),
        ("AV1", "libaom"),
    ],
)
def test_sendonly_authz_video_codec_type(settings, video_codec_type, expected_implementation):
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        jwt_private_claims={
            "video": True,
            "video_codec_type": video_codec_type,
        },
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    assert sendonly.offer_message is not None
    assert sendonly.offer_message["sdp"] is not None
    assert video_codec_type in sendonly.offer_message["sdp"]

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    # 統計で video が見つからないので謎挙動になってる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == expected_implementation
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
