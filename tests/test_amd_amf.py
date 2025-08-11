import os
import time

import pytest
from api import request_key_frame_api
from client import (
    SoraClient,
    SoraRole,
    codec_type_string_to_codec_type,
    is_codec_supported,
)
from simulcast import default_video_bit_rate, expect_target_bitrate

from sora_sdk import (
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
    get_video_codec_capability,
)

pytestmark = pytest.mark.skipif(os.environ.get("AMD_AMF") is None, reason="AMD AMF でのみ実行する")


def test_amd_amf_available(settings):
    capability = get_video_codec_capability()

    amd_amf_available = False
    for e in capability.engines:
        if e.name == SoraVideoCodecImplementation.AMD_AMF:
            amd_amf_available = True

    assert amd_amf_available is True

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
                        # TODO: AV1 decoder は True だが色々課題あり
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


@pytest.mark.parametrize(
    "video_codec_type",
    [
        "AV1",
        "H264",
        "H265",
    ],
)
def test_amd_amf_key_frame_request(settings, video_codec_type):
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
                    encoder=SoraVideoCodecImplementation.AMD_AMF,
                ),
            ]
        ),
    )
    sendonly.connect(fake_video=True)

    time.sleep(3)

    assert sendonly.connection_id is not None

    # キーフレーム要求 API を 3 秒間隔で 3 回呼び出す
    api_count = 3
    for _ in range(api_count):
        response = request_key_frame_api(
            settings.api_url, sendonly.channel_id, sendonly.connection_id
        )
        assert response.status_code == 200
        time.sleep(3)

    # 統計を取得する
    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")

    print("video_codec_type:", video_codec_type)
    print("keyFramesEncoded:", outbound_rtp_stats["keyFramesEncoded"])
    print("pliCount:", outbound_rtp_stats["pliCount"])
    print(
        "keyFramesEncoded >= pliCount * 0.7:",
        outbound_rtp_stats["keyFramesEncoded"] >= outbound_rtp_stats["pliCount"] * 0.7,
    )

    assert outbound_rtp_stats["keyFramesEncoded"] > api_count
    assert outbound_rtp_stats["pliCount"] >= api_count

    # PLI カウントの 50% 以上がキーフレームとしてエンコードされることを確認
    assert outbound_rtp_stats["keyFramesEncoded"] >= outbound_rtp_stats["pliCount"] * 0.7


@pytest.mark.parametrize(
    "video_codec_type",
    [
        "AV1",
        "H264",
        "H265",
    ],
)
def test_amd_amf_sendonly_recvonly(settings, video_codec_type):
    if not is_codec_supported(video_codec_type, SoraVideoCodecImplementation.AMD_AMF):
        pytest.skip(
            f"このチップでは {video_codec_type} のエンコード/デコードの両方がサポートされていません"
        )

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
                    encoder=SoraVideoCodecImplementation.AMD_AMF,
                ),
            ]
        ),
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    recvonly = SoraClient(
        settings,
        SoraRole.RECVONLY,
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
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "AMF"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0
    assert outbound_rtp_stats["keyFramesEncoded"] > 0
    assert outbound_rtp_stats["pliCount"] > 0
    # PLI カウントの 50% 以上がキーフレームとしてエンコードされることを確認
    assert outbound_rtp_stats["keyFramesEncoded"] >= outbound_rtp_stats["pliCount"] * 0.5

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    assert recvonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # inbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert inbound_rtp_stats["decoderImplementation"] == "AMF"
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0
    assert inbound_rtp_stats["keyFramesDecoded"] > 0


@pytest.mark.parametrize(
    (
        "video_codec_type",
        "expected_implementation",
        "video_width",
        "video_height",
        "simulcast_count",
    ),
    # FIXME: H.265 では、本数が 2 本 や 1 本の場合、エラーになるのでコメントアウトしている
    # FIXME: AV1 では、解像度が一定数より低くなる場合、エラーになるのでコメントアウトしている
    [
        # 1080p
        ("AV1", "AMF", 1920, 1080, 3),
        ("H264", "AMF", 1920, 1080, 3),
        ("H265", "AMF", 1920, 1080, 3),
        # 720p
        ("AV1", "AMF", 1280, 720, 3),
        ("H264", "AMF", 1280, 720, 3),
        ("H265", "AMF", 1280, 720, 3),
        # 540p
        ("AV1", "AMF", 960, 540, 3),
        ("H264", "AMF", 960, 540, 3),
        ("H265", "AMF", 960, 540, 3),
        # 360p
        # ("AV1", "AMF", 700, 640, 360, 2),
        # ("H264", "AMF", 700, 640, 360, 2),
        # ("H265", "AMF", 700, 640, 360, 2),
        # 270p
        # ("AV1", "AMF", 450, 480, 270, 2),
        # ("H264", "AMF", 450, 480, 270, 2),
        # ("H265", "AMF", 257, 480, 270, 2),
        # 180p
        # ("AV1", "AMF", 200, 320, 180, 1),
        # ("H264", "AMF", 200, 320, 180, 1),
        # ("H265", "AMF", 142, 320, 180, 1),
        # 135p
        # ("H265", "AMF", 101, 240, 135, 1),
    ],
)
def test_amd_amf_simulcast(
    settings,
    video_codec_type,
    expected_implementation,
    video_width,
    video_height,
    simulcast_count,
):
    if not is_codec_supported(video_codec_type, SoraVideoCodecImplementation.AMD_AMF):
        pytest.skip(f"このチップでは {video_codec_type} のエンコードがサポートされていません")

    video_bit_rate = default_video_bit_rate(video_codec_type, video_width, video_height)

    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        simulcast=True,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        video_bit_rate=video_bit_rate,
        video_width=video_width,
        video_height=video_height,
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

    time.sleep(10)

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # "type": "answer" の SDP で Simulcast があるかどうか
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert "a=simulcast:send r0;r1;r2" in sendonly.answer_message["sdp"]

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # 複数の outbound-rtp 統計情報を取得
    outbound_rtp_stats = [
        s for s in sendonly_stats if s.get("type") == "outbound-rtp" and s.get("kind") == "video"
    ]
    # simulcast_count に関係なく統計情報はかならず 3 本出力される
    # これは SDP で rid で ~r0 とかやる減るはず
    assert len(outbound_rtp_stats) == 3

    # rid でソート
    sorted_stats = sorted(outbound_rtp_stats, key=lambda x: x.get("rid", ""))

    for i, s in enumerate(sorted_stats):
        assert "qualityLimitationReason" in s
        assert "qualityLimitationDurations" in s

        # qualityLimitationReason が none で無い場合は安定したテストができない
        if s["qualityLimitationReason"] != "none":
            pytest.skip(f"qualityLimitationReason: {s['qualityLimitationReason']}")

        assert s["rid"] == f"r{i}"
        # simulcast_count が 2 の場合、rid r2 の bytesSent/packetsSent は 0 or 1 になる
        # simulcast_count が 1 の場合、rid r2 と r1 の bytesSent/packetsSent は 0 or 1 になる
        if i < simulcast_count:
            assert s["bytesSent"] > 1000
            assert s["packetsSent"] > 5

            assert s["targetBitrate"] >= expect_target_bitrate(
                video_codec_type, s["frameWidth"], s["frameHeight"]
            )

            encoder_implementation = s.get("encoderImplementation")

            print(
                s["rid"],
                video_codec_type,
                video_bit_rate * 1000,
                s["targetBitrate"],
                expected_implementation,
                encoder_implementation,
                s["frameWidth"],
                s["frameHeight"],
                s["bytesSent"],
                s["packetsSent"],
            )
        else:
            # 本来は 0 なのだが、simulcast_count が 1 の場合、
            # packetSent が 0 ではなく 1 や 2 になる場合がある
            # byteSent は 0
            print(
                s["rid"],
                video_codec_type,
                s["bytesSent"],
                s["packetsSent"],
            )
            assert s["bytesSent"] == 0
            assert s["packetsSent"] <= 2
