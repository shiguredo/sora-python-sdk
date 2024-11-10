import sys
import time
import uuid

import jwt
import pytest
from client import SoraClient, SoraRole


@pytest.mark.parametrize(
    "video_codec_params",
    [
        # video_codec, encoder_implementation, decoder_implementation
        ("VP8", "libvpx", "libvpx"),
        ("VP9", "libvpx", "libvpx"),
        ("AV1", "libaom", "dav1d"),
    ],
)
def test_sendonly_authz_video_codec_type(setup, video_codec_params):
    video_codec, encoder_implementation, decoder_implementation = video_codec_params

    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    secret = setup.get("secret")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    access_token = jwt.encode(
        {
            "channel_id": channel_id,
            "video": True,
            "video_codec_type": video_codec,
        },
        secret,
        algorithm="HS256",
    )
    metadata = {"access_token": access_token}

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=False,
        video=True,
        metadata=metadata,
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    assert sendonly.offer_message is not None
    print(sendonly.offer_message)

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == encoder_implementation
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
