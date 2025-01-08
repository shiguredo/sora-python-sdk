import sys
import time
import uuid

import jwt
import pytest
from client import SoraClient, SoraRole


@pytest.mark.skipif(reason="Sora C++ SDK 側の対応が必要")
def test_sendonly_authz_video_true(setup):
    """
    - type: connect で audio: true / video: false で繫ぐ
    - 認証成功時の払い出しで audio: false / video: true を払い出す
    """
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    secret = setup.get("secret")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    access_token = jwt.encode(
        {
            "channel_id": channel_id,
            "audio": False,
            "video": True,
            # 現在時刻 + 300 秒 (5分)
            "exp": int(time.time()) + 300,
        },
        secret,
        algorithm="HS256",
    )

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=True,
        video=False,
        metadata={"access_token": access_token},
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
    "video_codec_params",
    [
        # video_codec, encoder_implementation, decoder_implementation
        ("VP8", "libvpx"),
        ("VP9", "libvpx"),
        ("AV1", "libaom"),
    ],
)
def test_sendonly_authz_video_codec_type(setup, video_codec_params):
    video_codec_type, encoder_implementation = video_codec_params

    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    secret = setup.get("secret")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    access_token = jwt.encode(
        {
            "channel_id": channel_id,
            "video": True,
            "video_codec_type": video_codec_type,
            # 現在時刻 + 300 秒 (5分)
            "exp": int(time.time()) + 300,
        },
        secret,
        algorithm="HS256",
    )

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=False,
        video=True,
        metadata={"access_token": access_token},
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
    assert outbound_rtp_stats["encoderImplementation"] == encoder_implementation
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
