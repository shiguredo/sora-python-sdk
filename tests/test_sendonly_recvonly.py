import time

import pytest
from client import SoraClient, SoraRole


def test_sendonly_recvonly_audio(settings):
    sendonly = SoraClient(
        settings.signaling_urls,
        SoraRole.SENDONLY,
        settings.channel_id_prefix,
        audio=True,
        video=False,
        metadata=settings.metadata,
    )
    sendonly.connect(fake_audio=True)

    recvonly = SoraClient(
        settings.signaling_urls,
        SoraRole.RECVONLY,
        settings.channel_id_prefix,
        metadata=settings.metadata,
    )
    recvonly.connect()

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    sendonly.disconnect()
    recvonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == "audio/opus"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    # audio には encoderImplementation が無い
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    assert recvonly_codec_stats["mimeType"] == "audio/opus"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    # audio には decoderImplementation が無い
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0


@pytest.mark.parametrize(
    "video_codec_type, encoder_implementation, decoder_implementation",
    [
        ("VP8", "libvpx", "libvpx"),
        ("VP9", "libvpx", "libvpx"),
        ("AV1", "libaom", "dav1d"),
    ],
)
def test_sendonly_recvonly_video(
    settings, video_codec_type, encoder_implementation, decoder_implementation
):
    sendonly = SoraClient(
        settings.signaling_urls,
        SoraRole.SENDONLY,
        settings.channel_id_prefix,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        metadata=settings.metadata,
    )
    sendonly.connect(fake_video=True)

    recvonly = SoraClient(
        settings.signaling_urls,
        SoraRole.RECVONLY,
        settings.channel_id_prefix,
        metadata=settings.metadata,
    )
    recvonly.connect()

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    sendonly.disconnect()
    recvonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == encoder_implementation
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    assert recvonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # inbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert inbound_rtp_stats["decoderImplementation"] == decoder_implementation
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0
