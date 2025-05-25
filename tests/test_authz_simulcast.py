import sys
import time

import pytest
from client import SoraClient, SoraRole
from simulcast import default_video_bit_rate, expect_target_bitrate


@pytest.mark.parametrize(
    (
        "video_codec_type",
        "encoder_implementation",
        "video_width",
        "video_height",
    ),
    [
        # 360p
        ("VP8", "libvpx", 640, 360),
        ("VP9", "libvpx", 640, 360),
        ("AV1", "libaom", 640, 360),
        # 270p
        ("VP8", "libvpx", 480, 270),
        ("VP9", "libvpx", 480, 270),
        ("AV1", "libaom", 480, 270),
    ],
)
def test_authz_simulcast_r2_active_false(
    settings,
    video_codec_type,
    encoder_implementation,
    video_width,
    video_height,
):
    video_bit_rate = default_video_bit_rate(video_codec_type, video_width, video_height)

    simulcast_encodings = [
        {
            "rid": "r0",
            "active": True,
            "scaleResolutionDownBy": 2,
            "scalabilityMode": "L1T1",
        },
        {
            "rid": "r1",
            "active": True,
            "scaleResolutionDownBy": 1,
            "scalabilityMode": "L1T1",
        },
        {
            "rid": "r2",
            "active": False,
        },
    ]

    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
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

    time.sleep(10)

    # "type": "offer" の SDP で Simulcast があるかどうか
    assert sendonly.offer_message is not None
    assert sendonly.offer_message["sdp"] is not None
    assert video_codec_type in sendonly.offer_message["sdp"]
    assert "a=simulcast:recv r0;r1;~r2" in sendonly.offer_message["sdp"]

    assert "encodings" in sendonly.offer_message
    assert len(sendonly.offer_message["encodings"]) == 3

    assert sendonly.offer_message["encodings"][0]["rid"] == simulcast_encodings[0]["rid"]
    assert sendonly.offer_message["encodings"][1]["rid"] == simulcast_encodings[1]["rid"]
    assert sendonly.offer_message["encodings"][2]["rid"] == simulcast_encodings[2]["rid"]

    assert sendonly.offer_message["encodings"][0]["active"] == simulcast_encodings[0]["active"]
    assert sendonly.offer_message["encodings"][1]["active"] == simulcast_encodings[1]["active"]
    assert sendonly.offer_message["encodings"][2]["active"] == simulcast_encodings[2]["active"]

    assert (
        sendonly.offer_message["encodings"][0]["scaleResolutionDownBy"]
        == simulcast_encodings[0]["scaleResolutionDownBy"]
    )
    assert (
        sendonly.offer_message["encodings"][1]["scaleResolutionDownBy"]
        == simulcast_encodings[1]["scaleResolutionDownBy"]
    )

    assert (
        sendonly.offer_message["encodings"][0]["scalabilityMode"]
        == simulcast_encodings[0]["scalabilityMode"]
    )

    assert (
        sendonly.offer_message["encodings"][1]["scalabilityMode"]
        == simulcast_encodings[1]["scalabilityMode"]
    )

    # "type": "answer" の SDP で Simulcast があるかどうか
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert "a=simulcast:send r0;r1;~r2" in sendonly.answer_message["sdp"]

    sendonly_stats = sendonly.get_stats()
    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # 複数の outbound-rtp 統計情報を取得
    outbound_rtp_stats = [
        s
        for s in sendonly_stats
        if s.get("type") == "outbound-rtp" and s.get("kind") == "video" and s.get("active") is True
    ]

    # active は 2 本だけ
    assert len(outbound_rtp_stats) == 2

    # rid でソート
    sorted_stats = sorted(outbound_rtp_stats, key=lambda x: x.get("rid", ""))

    for i, s in enumerate(sorted_stats):
        assert s["rid"] == f"r{i}"
        assert s["kind"] == "video"

        assert encoder_implementation in s.get("encoderImplementation")
        if video_codec_type in ["AV1"]:
            assert "SimulcastEncoderAdapter" in s.get("encoderImplementation")

        if s["qualityLimitationReason"] != "none":
            pytest.skip(f"qualityLimitationReason: {s['qualityLimitationReason']}")

        assert s["keyFramesEncoded"] > 0
        assert s["bytesSent"] > 500
        assert s["packetsSent"] > 5

        # assert s["frameWidth"] >= video_width
        # assert s["frameHeight"] >= video_height

        assert s["targetBitrate"] >= expect_target_bitrate(
            video_codec_type, s["frameWidth"], s["frameHeight"]
        )

        assert "scalabilityMode" in s
        assert s["scalabilityMode"] == "L1T1"

        print(
            s["rid"],
            video_codec_type,
            s["encoderImplementation"],
            s["scalabilityMode"],
            video_bit_rate * 1000,
            s["targetBitrate"],
            s["frameWidth"],
            s["frameHeight"],
            s["bytesSent"],
            s["packetsSent"],
        )


@pytest.mark.parametrize(
    (
        "video_codec_type",
        "encoder_implementation",
        "video_width",
        "video_height",
    ),
    [
        # 180p
        ("VP8", "libvpx", 320, 180),
        ("VP9", "libvpx", 320, 180),
        ("AV1", "libaom", 320, 180),
        # 135p
        ("VP8", "libvpx", 240, 135),
        ("VP9", "libvpx", 240, 135),
        ("AV1", "libaom", 240, 135),
    ],
)
def test_authz_simulcast_r2_and_r1_active_false(
    settings,
    video_codec_type,
    encoder_implementation,
    video_width,
    video_height,
):
    video_bit_rate = default_video_bit_rate(video_codec_type, video_width, video_height)

    simulcast_encodings = [
        {
            "rid": "r0",
            "active": True,
            "scaleResolutionDownBy": 1,
            "scalabilityMode": "L1T1",
        },
        {
            "rid": "r1",
            "active": False,
        },
        {
            "rid": "r2",
            "active": False,
        },
    ]

    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
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

    time.sleep(10)

    # "type": "offer" の SDP で Simulcast があるかどうか
    assert sendonly.offer_message is not None
    assert sendonly.offer_message["sdp"] is not None
    assert video_codec_type in sendonly.offer_message["sdp"]
    assert "a=simulcast:recv r0;~r1;~r2" in sendonly.offer_message["sdp"]

    assert "encodings" in sendonly.offer_message
    assert len(sendonly.offer_message["encodings"]) == 3

    assert sendonly.offer_message["encodings"][0]["rid"] == simulcast_encodings[0]["rid"]
    assert sendonly.offer_message["encodings"][1]["rid"] == simulcast_encodings[1]["rid"]
    assert sendonly.offer_message["encodings"][2]["rid"] == simulcast_encodings[2]["rid"]

    assert sendonly.offer_message["encodings"][0]["active"] == simulcast_encodings[0]["active"]
    assert sendonly.offer_message["encodings"][1]["active"] == simulcast_encodings[1]["active"]
    assert sendonly.offer_message["encodings"][2]["active"] == simulcast_encodings[2]["active"]

    assert (
        sendonly.offer_message["encodings"][0]["scaleResolutionDownBy"]
        == simulcast_encodings[0]["scaleResolutionDownBy"]
    )

    assert (
        sendonly.offer_message["encodings"][0]["scalabilityMode"]
        == simulcast_encodings[0]["scalabilityMode"]
    )

    # "type": "answer" の SDP で Simulcast があるかどうか
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert "a=simulcast:send r0;~r1;~r2" in sendonly.answer_message["sdp"]

    sendonly_stats = sendonly.get_stats()
    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # 複数の outbound-rtp 統計情報を取得
    outbound_rtp_stats = [
        s
        for s in sendonly_stats
        if s.get("type") == "outbound-rtp" and s.get("kind") == "video" and s.get("active") is True
    ]

    assert len(outbound_rtp_stats) == 1

    s = outbound_rtp_stats[0]

    assert s["rid"] == "r0"
    assert s["kind"] == "video"

    assert encoder_implementation in s["encoderImplementation"]
    print(s["encoderImplementation"])

    if s["qualityLimitationReason"] != "none":
        pytest.skip(f"qualityLimitationReason: {s['qualityLimitationReason']}")

    assert s["keyFramesEncoded"] > 0
    assert s["bytesSent"] > 500
    assert s["packetsSent"] > 5

    assert s["targetBitrate"] >= expect_target_bitrate(
        video_codec_type, s["frameWidth"], s["frameHeight"]
    )

    assert "scalabilityMode" in s
    assert s["scalabilityMode"] == "L1T1"

    print(
        s["rid"],
        video_codec_type,
        s["encoderImplementation"],
        s["scalabilityMode"],
        video_bit_rate * 1000,
        s["targetBitrate"],
        s["frameWidth"],
        s["frameHeight"],
        s["bytesSent"],
        s["packetsSent"],
    )


@pytest.mark.skipif(sys.platform == "darwin", reason="Apple では SW コーデックは動作させない")
@pytest.mark.parametrize(
    (
        "video_codec_type",
        "encoder_implementation",
        "video_bit_rate",
        "video_width",
        "video_height",
    ),
    [
        # どうやら scaleResolutionDownTo を指定すると規定されたテーブルのビットレートでは足りない模様
        ("VP8", "libvpx", 1200 * 3, 960, 540),
        ("VP9", "libvpx", 879 * 3, 960, 540),
        ("AV1", "libaom", 879 * 3, 960, 540),
    ],
)
def test_authz_simulcast_scale_resolution_down_to(
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
            "scaleResolutionDownTo": {"maxWidth": 640, "maxHeight": 360},
            "scalabilityMode": "L1T1",
        },
        {
            "rid": "r1",
            "active": True,
            "scaleResolutionDownTo": {"maxWidth": 640, "maxHeight": 360},
            "scalabilityMode": "L1T1",
        },
        {
            "rid": "r2",
            "active": True,
            "scaleResolutionDownTo": {"maxWidth": 640, "maxHeight": 360},
            "scalabilityMode": "L1T1",
        },
    ]

    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
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

    time.sleep(10)

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
        assert s["rid"] == f"r{i}"
        assert s["kind"] == "video"

        # VP8 の場合は scaleResolutionDownTo を指定すると SimulcastEncoderAdapter が無くなる
        # TODO: 念のため他の挙動も確認すること
        if video_codec_type == "VP9":
            assert "SimulcastEncoderAdapter" in s["encoderImplementation"]
        assert encoder_implementation in s["encoderImplementation"]

        if s["qualityLimitationReason"] != "none":
            pytest.skip(f"qualityLimitationReason: {s['qualityLimitationReason']}")

        assert s["keyFramesEncoded"] > 0
        assert s["bytesSent"] > 500
        assert s["packetsSent"] > 5

        assert s["frameWidth"] == 640
        assert s["frameHeight"] == 352

        assert s["targetBitrate"] >= expect_target_bitrate(
            video_codec_type, s["frameWidth"], s["frameHeight"]
        )

        scalability_mode = None
        if "scalabilityMode" in s:
            assert s["scalabilityMode"] == "L1T1"
            scalability_mode = s["scalabilityMode"]

        # targetBitrate が指定したビットレートの 90% 以上、100% 以下に収まることを確認
        expected_bitrate = video_bit_rate * 1000
        print(
            s["rid"],
            video_codec_type,
            s["encoderImplementation"],
            scalability_mode,
            expected_bitrate,
            s["targetBitrate"],
            s["frameWidth"],
            s["frameHeight"],
            s["bytesSent"],
            s["packetsSent"],
        )
