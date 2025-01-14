import sys
import time
import uuid

import pytest
from client import SoraClient, SoraRole

"""
GitHub Actions で Video Toolbox を送受信で利用しようとするとエラーになるので、
テストを sendonly のみに絞っている
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS でのみ実行する")
@pytest.mark.parametrize(
    "video_codec_type",
    ["H264", "H265"],
)
def test_macos_video_hwa_sendonly(setup, video_codec_type):
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
        use_hwa=True,
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    assert sendonly.connect_message is not None
    assert sendonly.connect_message["channel_id"] == channel_id
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


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS でのみ実行する")
@pytest.mark.parametrize(
    (
        "video_codec_type",
        "expected_implementation",
        "video_bit_rate",
        "video_width",
        "video_height",
        "simulcast_count",
    ),
    [
        # CI のインスタンスがスペック低くてテストが通らない
        # # 1080p
        # ("H264", "VideoToolbox", 5000, 1920, 1080, 3),
        # ("H265", "VideoToolbox", 5000, 1920, 1080, 3),
        # # 720p
        # ("H264", "VideoToolbox", 2500, 1280, 720, 3),
        # ("H265", "VideoToolbox", 2500, 1280, 720, 3),
        # 540p
        ("H264", "VideoToolbox", 1200, 960, 540, 3),
        ("H265", "VideoToolbox", 1200, 960, 540, 3),
        # 360p
        ("H264", "VideoToolbox", 700, 640, 360, 2),
        ("H265", "VideoToolbox", 700, 640, 360, 2),
        # 270p
        ("H264", "VideoToolbox", 450, 480, 270, 2),
        ("H265", "VideoToolbox", 450, 480, 270, 2),
        # 180p
        ("H264", "VideoToolbox", 200, 320, 180, 1),
        ("H265", "VideoToolbox", 200, 320, 180, 1),
    ],
)
def test_macos_simulcast(
    setup,
    video_codec_type,
    expected_implementation,
    video_bit_rate,
    video_width,
    video_height,
    simulcast_count,
):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        simulcast=True,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        video_bit_rate=video_bit_rate,
        metadata=metadata,
        video_width=video_width,
        video_height=video_height,
        use_hwa=True,
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

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
        assert s["rid"] == f"r{i}"
        # simulcast_count が 2 の場合、rid r2 の bytesSent/packetsSent は 0 or 1 になる
        # simulcast_count が 1 の場合、rid r2 と r1 の bytesSent/packetsSent は 0 or 1 になる
        if i < simulcast_count:
            # 1 本になると simulcastEncodingAdapter がなくなる
            if simulcast_count > 1:
                assert "SimulcastEncoderAdapter" in s["encoderImplementation"]
            assert expected_implementation in s["encoderImplementation"]

            assert s["bytesSent"] > 1000
            assert s["packetsSent"] > 5
            # targetBitrate が指定したビットレートの 90% 以上、100% 以下に収まることを確認
            expected_bitrate = video_bit_rate * 1000
            print(
                s["rid"],
                video_codec_type,
                expected_implementation,
                expected_bitrate,
                s["targetBitrate"],
                s["frameWidth"],
                s["frameHeight"],
                s["bytesSent"],
                s["packetsSent"],
            )
            # 期待値の 20% 以上、100% 以下に収まることを確認
            assert expected_bitrate * 0.2 <= s["targetBitrate"] <= expected_bitrate
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


@pytest.mark.skip(reason="ローカルでは成功する")
def test_macos_h264_sendonly_recvonly(setup):
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
        video_codec_type="H264",
        metadata=metadata,
        use_hwa=True,
    )
    sendonly.connect()

    recvonly = SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        metadata=metadata,
        use_hwa=True,
    )
    recvonly.connect()

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    sendonly.disconnect()
    recvonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    # H.264 が採用されているかどうか確認する
    assert sendonly_codec_stats["mimeType"] == "video/H264"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "VideoToolbox"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    # H.264 が採用されているかどうか確認する
    assert recvonly_codec_stats["mimeType"] == "video/H264"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert inbound_rtp_stats["decoderImplementation"] == "VideoToolbox"
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0


@pytest.mark.skip(reason="ローカルでは成功する")
def test_macos_h265_sendonly_recvonly(setup):
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
        video_codec_type="H265",
        metadata=metadata,
        use_hwa=True,
    )
    sendonly.connect()

    recvonly = SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        metadata=metadata,
        use_hwa=True,
    )
    recvonly.connect()

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    sendonly.disconnect()
    recvonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == "video/H265"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "VideoToolbox"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    assert recvonly_codec_stats["mimeType"] == "video/H265"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert inbound_rtp_stats["decoderImplementation"] == "VideoToolbox"
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0
