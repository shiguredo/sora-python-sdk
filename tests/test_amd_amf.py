import os
import sys
import time
import uuid

import pytest
from client import (
    SoraClient,
    SoraRole,
    codec_type_string_to_codec_type,
    is_codec_supported,
)

from sora_sdk import (
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
    get_video_codec_capability,
)


@pytest.mark.skipif(os.environ.get("AMD_AMF") is None, reason="AMD AMF でのみ実行する")
def test_amd_amf_available(setup):
    capability = get_video_codec_capability()

    intel_vpl_available = False
    for e in capability.engines:
        if e.name == SoraVideoCodecImplementation.AMD_AMF:
            intel_vpl_available = True

    assert intel_vpl_available is True

    for e in capability.engines:
        if e.name == SoraVideoCodecImplementation.AMD_AMF:
            # 対応コーデックは 5 種類
            assert len(e.codecs) == 5

            for c in e.codecs:
                match c.type:
                    case SoraVideoCodecType.VP8:
                        assert c.decoder is False
                        assert c.encoder is False
                    case SoraVideoCodecType.VP9:
                        assert c.decoder is True
                        assert c.encoder is False
                    case SoraVideoCodecType.AV1:
                        assert c.decoder is True
                        assert c.encoder is True
                    case SoraVideoCodecType.H264:
                        assert c.decoder is True
                        assert c.encoder is True
                    case SoraVideoCodecType.H265:
                        assert c.decoder is True
                        assert c.encoder is True
                    case _:
                        pytest.fail(f"未実装の codec_type: {c.type}")


@pytest.mark.skipif(os.environ.get("AMD_AMF") is None, reason="AMD AMF でのみ実行する")
@pytest.mark.parametrize(
    "video_codec_type",
    [
        # AV1 は decoder が正常に動作しない
        # "AV1",
        "H264",
        "H265",
    ],
)
def test_amd_amf_sendonly_recvonly(setup, video_codec_type):
    if not is_codec_supported(video_codec_type, SoraVideoCodecImplementation.AMD_AMF):
        pytest.skip(
            f"このチップでは {video_codec_type} のエンコード/デコードの両方がサポートされていません"
        )

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
        video_codec_type=video_codec_type,
        metadata=metadata,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=codec_type_string_to_codec_type(video_codec_type),
                    encoder=SoraVideoCodecImplementation.AMD_AMF,
                ),
            ]
        ),
    )
    sendonly.connect(fake_video=True)

    recvonly = SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        metadata=metadata,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=codec_type_string_to_codec_type(video_codec_type),
                    decoder=SoraVideoCodecImplementation.AMD_AMF,
                ),
            ]
        ),
    )
    recvonly.connect()

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    sendonly.disconnect()
    recvonly.disconnect()

    # offer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.offer_message is not None
    assert "sdp" in sendonly.offer_message
    assert video_codec_type in sendonly.offer_message["sdp"]

    # answer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert video_codec_type in sendonly.answer_message["sdp"]

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    # H.264/H.265 が採用されているかどうか確認する
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "AMF"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    # H.264/H.265 が採用されているかどうか確認する
    assert recvonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # inbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert inbound_rtp_stats["decoderImplementation"] == "AMF"
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0
