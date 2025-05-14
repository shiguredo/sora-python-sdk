import sys
import time
import uuid

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

        if e.name == SoraVideoCodecImplementation.CISCO_OPENH264:
            for c in e.codecs:
                if c.decoder or c.encoder:
                    # encoder/decoder どちらかが true であれば採用する
                    if c.decoder or c.encoder:
                        codecs.append(
                            SoraVideoCodecPreference.Codec(
                                type=c.type,
                                decoder=e.name,
                                encoder=e.name,
                                parameters=SoraVideoCodecPreference.Parameters(),
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
