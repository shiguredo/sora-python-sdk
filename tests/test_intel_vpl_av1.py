import os
import sys
import time
import uuid

import pytest
from client import (
    SoraClient,
    SoraRole,
)

from sora_sdk import (
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
)


@pytest.mark.skipif(os.environ.get("INTEL_VPL") is None, reason="Intel VPL でのみ実行する")
def test_intel_vpl_av1_decoder_dynamic_resolution(setup):
    """
    - AV1 の映像の解像度が変わっても正常に動作するかを確認する
    """

    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    # 送信側は libaom を利用してソフトウェアエンコードを利用する
    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=False,
        video=True,
        video_codec_type="AV1",
        video_bit_rate=5000,
        metadata=metadata,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.AV1,
                    encoder=SoraVideoCodecImplementation.INTERNAL,
                ),
            ]
        ),
        video_width=1280,
        video_height=720,
    )
    sendonly.connect(fake_video=True)

    # 受信側は libvpl を利用してハードウェアデコードを利用する
    recvonly = SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        metadata=metadata,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.AV1,
                    decoder=SoraVideoCodecImplementation.INTEL_VPL,
                ),
            ]
        ),
    )
    recvonly.connect()

    time.sleep(5)

    # offer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.offer_message is not None
    assert "sdp" in sendonly.offer_message
    assert "AV1" in sendonly.offer_message["sdp"]

    # answer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert "AV1" in sendonly.answer_message["sdp"]

    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == "video/AV1"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "libaom"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
    assert outbound_rtp_stats["frameWidth"] == 1280
    assert outbound_rtp_stats["frameHeight"] == 720

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    # H.264/H.265 が採用されているかどうか確認する
    assert recvonly_codec_stats["mimeType"] == "video/AV1"

    # inbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert inbound_rtp_stats["decoderImplementation"] == "libvpl"
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0
    assert inbound_rtp_stats["frameWidth"] == 1280
    assert inbound_rtp_stats["frameHeight"] == 720

    # 解像度を回転させる
    sendonly.set_video_resolution(720, 1280)

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "libaom"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
    # 送信側の解像度が回転していることを確認する
    assert outbound_rtp_stats["frameWidth"] == 720
    assert outbound_rtp_stats["frameHeight"] == 1280

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    assert recvonly_codec_stats["mimeType"] == "video/AV1"

    # inbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert inbound_rtp_stats["decoderImplementation"] == "libvpl"
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0
    # 受信側の解像度が回転していることを確認する
    assert inbound_rtp_stats["frameWidth"] == 720
    assert inbound_rtp_stats["frameHeight"] == 1280

    sendonly.disconnect()
    recvonly.disconnect()


@pytest.mark.skipif(os.environ.get("INTEL_VPL") is None, reason="Intel VPL でのみ実行する")
def test_intel_vpl_av1_decoder_8k_resolution(setup):
    """
    - 8K でも正常に動作するかを確認する
    """

    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    # 送信側は libaom を利用してソフトウェアエンコードを利用する
    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=False,
        video=True,
        video_codec_type="AV1",
        video_bit_rate=15000,
        metadata=metadata,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.AV1,
                    encoder=SoraVideoCodecImplementation.INTERNAL,
                ),
            ]
        ),
        video_width=7680,
        video_height=4320,
    )
    sendonly.connect(fake_video=True)

    # 受信側は libvpl を利用してハードウェアデコードを利用する
    recvonly = SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        metadata=metadata,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.AV1,
                    decoder=SoraVideoCodecImplementation.INTEL_VPL,
                ),
            ]
        ),
    )
    recvonly.connect()

    time.sleep(10)

    # offer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.offer_message is not None
    assert "sdp" in sendonly.offer_message
    assert "AV1" in sendonly.offer_message["sdp"]

    # answer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert "AV1" in sendonly.answer_message["sdp"]

    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == "video/AV1"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "libaom"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
    assert outbound_rtp_stats["frameWidth"] == 7680
    assert outbound_rtp_stats["frameHeight"] == 4320

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    assert recvonly_codec_stats["mimeType"] == "video/AV1"

    # inbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert inbound_rtp_stats["decoderImplementation"] == "libvpl"
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0
    assert inbound_rtp_stats["frameWidth"] == 7680
    assert inbound_rtp_stats["frameHeight"] == 4320

    sendonly.disconnect()
    recvonly.disconnect()
