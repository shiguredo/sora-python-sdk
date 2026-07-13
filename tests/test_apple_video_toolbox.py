import os
import time

import pytest
from client import SoraClient, SoraRole
from simulcast import default_video_bit_rate, expect_target_bitrate

pytestmark = pytest.mark.skipif(
    os.environ.get("APPLE_VIDEO_TOOLBOX") is None, reason="Apple Video Toolbox でのみ実行する"
)


@pytest.mark.parametrize(
    "video_codec_type",
    ["H264", "H265"],
)
def test_apple_video_toolbox_sendonly(settings, video_codec_type):
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    assert sendonly.connect_message is not None
    assert sendonly.connect_message["channel_id"] == settings.channel_id
    assert "video" in sendonly.connect_message
    assert sendonly.connect_message["video"]["codec_type"] == video_codec_type

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    # H.264 が採用されているかどうか確認する
    assert codec_stats["mimeType"] == f"video/{video_codec_type}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "VideoToolbox"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0


@pytest.mark.parametrize(
    "video_codec_type",
    ["H264", "H265"],
)
def test_apple_video_toolbox_sendonly_recvonly(settings, video_codec_type):
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
    )
    sendonly.connect(fake_video=True)

    recvonly = SoraClient(
        settings,
        SoraRole.RECVONLY,
    )
    recvonly.connect()

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    sendonly.disconnect()
    recvonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    # 指定した video_codec_type が採用されているかどうか確認する
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "VideoToolbox"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    # 指定した video_codec_type が採用されているかどうか確認する
    assert recvonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert inbound_rtp_stats["decoderImplementation"] == "VideoToolbox"
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0


@pytest.mark.parametrize(
    (
        "video_codec_type",
        "expected_implementation",
        "video_width",
        "video_height",
        "simulcast_count",
    ),
    [
        # 1080p
        ("H264", "VideoToolbox", 1920, 1080, 3),
        ("H265", "VideoToolbox", 1920, 1080, 3),
        # 720p
        ("H264", "VideoToolbox", 1280, 720, 3),
        ("H265", "VideoToolbox", 1280, 720, 3),
        # 540p
        ("H264", "VideoToolbox", 960, 540, 3),
        ("H265", "VideoToolbox", 960, 540, 3),
        # 360p
        # ("H264", "VideoToolbox", 640, 360, 2),
        # ("H265", "VideoToolbox", 640, 360, 2),
        # 270p
        # ("H264", "VideoToolbox", 480, 270, 2),
        # ("H265", "VideoToolbox", 480, 270, 2),
        # 180p
        # ("H264", "VideoToolbox", 320, 180, 1),
        # ("H265", "VideoToolbox", 320, 180, 1),
        # 135p
        # ("H265", "VideoToolbox", 240, 135, 1),
    ],
)
def test_apple_video_toolbox_simulcast(
    settings,
    video_codec_type,
    expected_implementation,
    video_width,
    video_height,
    simulcast_count,
):
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
            # 1 本になると simulcastEncodingAdapter がなくなる
            if simulcast_count > 1:
                assert "SimulcastEncoderAdapter" in s["encoderImplementation"]
            assert expected_implementation in s["encoderImplementation"]

            assert s["bytesSent"] > 500
            assert s["packetsSent"] > 5

            assert s["targetBitrate"] >= expect_target_bitrate(
                video_codec_type, s["frameWidth"], s["frameHeight"]
            )

            print(
                s["rid"],
                video_codec_type,
                expected_implementation,
                video_bit_rate * 1000,
                s["targetBitrate"],
                s["frameWidth"],
                s["frameHeight"],
                s["bytesSent"],
                s["packetsSent"],
            )

        else:
            # 本来は 0 なのだが、simulcast_count が 1 の場合、
            # packetSent が 0 ではなく 1 や 2 になる場合がある
            # byteSent は 0
            assert s["bytesSent"] == 0
            assert s["packetsSent"] <= 2
            print(
                s["rid"],
                video_codec_type,
                s["bytesSent"],
                s["packetsSent"],
            )


@pytest.mark.parametrize(
    (
        "video_codec_type",
        "encoder_implementation",
        "video_bit_rate",
        "video_width",
        "video_height",
    ),
    [
        # どうやら scaleResolutionDownTo を指定すると規定されたテーブルのビットレートでは足りない
        # なので少しかさまししている
        ("H264", "VideoToolbox", 200 * 3, 320, 180),
        ("H265", "VideoToolbox", 142 * 3, 320, 180),
    ],
)
def test_apple_video_toolbox_simulcast_authz_scale_resolution_to(
    settings,
    video_codec_type,
    encoder_implementation,
    video_bit_rate,
    video_width,
    video_height,
):
    simulcast_encodings = [
        {
            "rid": "r0",
            "active": True,
            "scaleResolutionDownTo": {"maxWidth": video_width, "maxHeight": video_height},
            "scalabilityMode": "L1T1",
        },
        {
            "rid": "r1",
            "active": True,
            "scaleResolutionDownTo": {"maxWidth": video_width, "maxHeight": video_height},
            "scalabilityMode": "L1T1",
        },
        {
            "rid": "r2",
            "active": True,
            "scaleResolutionDownTo": {"maxWidth": video_width, "maxHeight": video_height},
            "scalabilityMode": "L1T1",
        },
    ]

    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        video_bit_rate=video_bit_rate,
        jwt_private_claims={
            "video": True,
            "video_codec_type": video_codec_type,
            "video_bit_rate": video_bit_rate,
            "simulcast": True,
            "simulcast_encodings": simulcast_encodings,
        },
        video_width=video_width,
        video_height=video_height,
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    # "type": "offer" の SDP で Simulcast があるかどうか
    assert sendonly.offer_message is not None
    assert sendonly.offer_message["sdp"] is not None
    assert video_codec_type in sendonly.offer_message["sdp"]
    assert "a=simulcast:recv r0;r1;r2" in sendonly.offer_message["sdp"]

    assert "encodings" in sendonly.offer_message
    assert len(sendonly.offer_message["encodings"]) == 3

    assert sendonly.offer_message["encodings"][0]["rid"] == simulcast_encodings[0]["rid"]
    assert sendonly.offer_message["encodings"][1]["rid"] == simulcast_encodings[1]["rid"]
    assert sendonly.offer_message["encodings"][2]["rid"] == simulcast_encodings[2]["rid"]

    assert sendonly.offer_message["encodings"][0]["active"] == simulcast_encodings[0]["active"]
    assert sendonly.offer_message["encodings"][1]["active"] == simulcast_encodings[1]["active"]
    assert sendonly.offer_message["encodings"][2]["active"] == simulcast_encodings[2]["active"]

    assert (
        sendonly.offer_message["encodings"][0]["scaleResolutionDownTo"]["maxWidth"]
        == simulcast_encodings[0]["scaleResolutionDownTo"]["maxWidth"]
    )
    assert (
        sendonly.offer_message["encodings"][1]["scaleResolutionDownTo"]["maxWidth"]
        == simulcast_encodings[1]["scaleResolutionDownTo"]["maxWidth"]
    )
    assert (
        sendonly.offer_message["encodings"][2]["scaleResolutionDownTo"]["maxWidth"]
        == simulcast_encodings[2]["scaleResolutionDownTo"]["maxWidth"]
    )

    assert (
        sendonly.offer_message["encodings"][0]["scalabilityMode"]
        == simulcast_encodings[0]["scalabilityMode"]
    )

    assert (
        sendonly.offer_message["encodings"][1]["scalabilityMode"]
        == simulcast_encodings[1]["scalabilityMode"]
    )

    assert (
        sendonly.offer_message["encodings"][2]["scalabilityMode"]
        == simulcast_encodings[2]["scalabilityMode"]
    )

    # "type": "answer" の SDP で Simulcast があるかどうか
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert "a=simulcast:send r0;r1;r2" in sendonly.answer_message["sdp"]

    sendonly_stats = sendonly.get_stats()
    sendonly.disconnect()

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
        # qualityLimitationReason と qualityLimitationDurations がないことはあり得ない
        assert "qualityLimitationReason" in s
        assert "qualityLimitationDurations" in s

        # qualityLimitationReason が "none" ではない場合は正常なテストができないのでテストをスキップする
        if s["qualityLimitationReason"] != "none":
            pytest.skip(f"qualityLimitationReason: {s['qualityLimitationReason']}")

        assert s["rid"] == f"r{i}"
        assert s["kind"] == "video"

        # VP8 の場合は scaleResolutionDownTo を指定すると SimulcastEncoderAdapter が無くなる
        # TODO: 念のため他の挙動も確認すること
        if video_codec_type == "VP9":
            assert "SimulcastEncoderAdapter" in s["encoderImplementation"]
        assert encoder_implementation in s["encoderImplementation"]

        assert s["keyFramesEncoded"] > 0
        assert s["bytesSent"] > 500
        assert s["packetsSent"] > 5

        assert s["frameWidth"] == 320
        assert s["frameHeight"] == 176

        assert s["targetBitrate"] >= expect_target_bitrate(
            video_codec_type, s["frameWidth"], s["frameHeight"]
        )

        # Apple Video Toolbox の場合は scalabilityMode がない
        assert "scalabilityMode" not in s

        # targetBitrate が指定したビットレートの 90% 以上、100% 以下に収まることを確認
        print(
            s["rid"],
            video_codec_type,
            s["encoderImplementation"],
            s["targetBitrate"],
            s["frameWidth"],
            s["frameHeight"],
            s["bytesSent"],
            s["packetsSent"],
        )
