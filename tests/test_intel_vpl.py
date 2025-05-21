import os
import platform
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
from simulcast import default_video_bit_rate, expect_target_bitrate

from sora_sdk import (
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
    get_video_codec_capability,
)


@pytest.mark.skipif(os.environ.get("INTEL_VPL") is None, reason="Intel VPL でのみ実行する")
def test_intel_vpl_available(setup):
    capability = get_video_codec_capability()

    intel_vpl_available = False
    for e in capability.engines:
        if e.name == SoraVideoCodecImplementation.INTEL_VPL:
            intel_vpl_available = True

    assert intel_vpl_available is True

    for e in capability.engines:
        if e.name == SoraVideoCodecImplementation.INTEL_VPL:
            # 対応コーデックは 5 種類
            assert len(e.codecs) == 5

            for c in e.codecs:
                match c.type:
                    case SoraVideoCodecType.VP8:
                        assert c.decoder is False
                        assert c.encoder is False
                    case SoraVideoCodecType.VP9:
                        assert c.decoder is True
                        # VPL 的に VP9 は利用できるが、
                        # Sora Python SDK では VPL VP9 Encoder が正常に動作しないため無効
                        assert c.encoder is False
                    case SoraVideoCodecType.AV1:
                        # チップによって対応指定ないものがあるので判断しない
                        # assert c.decoder is True
                        # assert c.encoder is True
                        pass
                    case SoraVideoCodecType.H264:
                        assert c.decoder is True
                        assert c.encoder is True
                    case SoraVideoCodecType.H265:
                        assert c.decoder is True
                        assert c.encoder is True
                    case _:
                        pytest.fail(f"未実装の codec_type: {c.type}")


@pytest.mark.skipif(os.environ.get("INTEL_VPL") is None, reason="Intel VPL でのみ実行する")
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
        ("AV1", "libvpl", 1920, 1080, 3),
        ("H264", "libvpl", 1920, 1080, 3),
        ("H265", "libvpl", 1920, 1080, 3),
        # 720p
        ("AV1", "libvpl", 1280, 720, 3),
        ("H264", "libvpl", 1280, 720, 3),
        ("H265", "libvpl", 1280, 720, 3),
        # 540p
        ("AV1", "libvpl", 960, 540, 3),
        ("H264", "libvpl", 960, 540, 3),
        ("H265", "libvpl", 960, 540, 3),
        # 360p
        # ("AV1", "libvpl", 640, 360, 2),
        # ("H264", "libvpl", 640, 360, 2),
        # ("H265", "libvpl", 640, 360, 2),
        # 270p
        # ("AV1", "libvpl", 480, 270, 2),
        # ("H264", "libvpl", 480, 270, 2),
        # ("H265", "libvpl", 270, 480, 2),
        # 180p
        # ("AV1", "libvpl", 320, 200, 1),
        # ("H264", "libvpl", 320, 180, 1),
        # ("H265", "libvpl", 180, 320, 1),
        # 135p
        # ("H265", "libvpl", 240, 135, 1),
    ],
)
def test_intel_vpl_simulcast(
    setup,
    video_codec_type,
    expected_implementation,
    video_width,
    video_height,
    simulcast_count,
):
    if not is_codec_supported(video_codec_type, SoraVideoCodecImplementation.INTEL_VPL):
        pytest.skip(f"このチップでは {video_codec_type} のエンコードがサポートされていません")

    if platform.system() == "Windows" and simulcast_count == 1:
        pytest.skip(
            f"Windows では {video_codec_type} の simulcast_count が 1 の場合は失敗するので skip する"
        )

    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"
    video_bit_rate = default_video_bit_rate(video_codec_type, video_width, video_height)

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
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=codec_type_string_to_codec_type(video_codec_type),
                    encoder=SoraVideoCodecImplementation.INTEL_VPL,
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
            # 1 本になると simulcastEncodingAdapter がなくなる
            # if simulcast_count > 1:
            #     assert "SimulcastEncoderAdapter" in s["encoderImplementation"]
            assert expected_implementation in s["encoderImplementation"]

            assert s["bytesSent"] > 1000
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
            print(
                s["rid"],
                video_codec_type,
                s["bytesSent"],
                s["packetsSent"],
            )
            assert s["bytesSent"] == 0
            assert s["packetsSent"] <= 2


@pytest.mark.skipif(os.environ.get("INTEL_VPL") is None, reason="Intel VPL でのみ実行する")
@pytest.mark.parametrize(
    "video_codec_type",
    [
        "AV1",
        "H264",
        "H265",
    ],
)
def test_intel_vpl_sendonly_recvonly(setup, video_codec_type):
    if not is_codec_supported(video_codec_type, SoraVideoCodecImplementation.INTEL_VPL):
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
                    encoder=SoraVideoCodecImplementation.INTEL_VPL,
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
                    decoder=SoraVideoCodecImplementation.INTEL_VPL,
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
    assert outbound_rtp_stats["encoderImplementation"] == "libvpl"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    # H.264/H.265 が採用されているかどうか確認する
    assert recvonly_codec_stats["mimeType"] == f"video/{video_codec_type}"

    # inbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert inbound_rtp_stats["decoderImplementation"] == "libvpl"
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0


@pytest.mark.xfail(
    strict=True, reason="AV1 は解像度が 120x90 以下の場合に正常に処理ができない問題がある"
)
@pytest.mark.parametrize(
    (
        "video_codec_type",
        "expected_implementation",
        "video_bit_rate",
        "video_width",
        "video_height",
    ),
    [
        # 数値は 4:3 または 16:9 の比率にして
        # ("AV1", "libvpl", 700, 128, 96),
        # ("AV1", "libvpl", 700, 124, 93),
        # ここで失敗する
        ("AV1", "libvpl", 700, 120, 90),
    ],
)
def test_intel_vpl_av1_mini_resolution(
    setup, video_codec_type, expected_implementation, video_bit_rate, video_width, video_height
):
    if not is_codec_supported(video_codec_type, SoraVideoCodecImplementation.INTEL_VPL):
        pytest.skip(f"このチップでは {video_codec_type} がサポートされていません")

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
        video_bit_rate=video_bit_rate,
        video_width=video_width,
        video_height=video_height,
        metadata=metadata,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.AV1,
                    encoder=SoraVideoCodecImplementation.INTEL_VPL,
                ),
            ]
        ),
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    assert sendonly.connect_message is not None
    assert sendonly.connect_message["channel_id"] == channel_id
    assert "video" in sendonly.connect_message
    assert sendonly.connect_message["video"]["codec_type"] == video_codec_type

    # offer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.offer_message is not None
    assert "sdp" in sendonly.offer_message
    assert video_codec_type in sendonly.offer_message["sdp"]

    # answer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert video_codec_type in sendonly.answer_message["sdp"]

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    # VP9 が採用されているかどうか確認する
    assert codec_stats["mimeType"] == f"video/{video_codec_type}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")

    assert "frameWidth" in outbound_rtp_stats
    assert "frameHeight" in outbound_rtp_stats

    # ここで libvpx になって失敗する
    assert outbound_rtp_stats["encoderImplementation"] == expected_implementation
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0


@pytest.mark.skipif(os.environ.get("INTEL_VPL") is None, reason="Intel VPL でのみ実行する")
def test_intel_vpl_decoding_av1(setup):
    """
    N100 などは AV1 のデコーディングに対応している
    """
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
        video_codec_type="AV1",
        metadata=metadata,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.AV1,
                    encoder=SoraVideoCodecImplementation.INTERNAL,
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
                    type=SoraVideoCodecType.AV1,
                    decoder=SoraVideoCodecImplementation.INTEL_VPL,
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
    assert "AV1" in sendonly.offer_message["sdp"]

    # answer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert "AV1" in sendonly.answer_message["sdp"]

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == "video/AV1"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "libaom"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    assert recvonly_codec_stats["mimeType"] == "video/AV1"

    # inbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert inbound_rtp_stats["decoderImplementation"] == "libvpl"
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0


## VP9


@pytest.mark.skipif(os.environ.get("INTEL_VPL") is None, reason="Intel VPL でのみ実行する")
@pytest.mark.xfail(
    strict=True, reason="VP9 は C++ SDK の Intel VPL で対応できていないのでテストが失敗する"
)
@pytest.mark.parametrize(
    (
        "video_codec_type",
        "expected_implementation",
    ),
    [
        ("VP9", "libvpl"),
    ],
)
def test_intel_vpl_vp9_failed(setup, video_codec_type, expected_implementation):
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
                    type=SoraVideoCodecType.VP9,
                    encoder=SoraVideoCodecImplementation.INTEL_VPL,
                ),
            ]
        ),
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    assert sendonly.connect_message is not None
    assert sendonly.connect_message["channel_id"] == channel_id
    assert "video" in sendonly.connect_message
    assert sendonly.connect_message["video"]["codec_type"] == video_codec_type

    # offer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.offer_message is not None
    assert "sdp" in sendonly.offer_message
    assert video_codec_type in sendonly.offer_message["sdp"]

    # answer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert video_codec_type in sendonly.answer_message["sdp"]

    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    # VP9 が採用されているかどうか確認する
    assert codec_stats["mimeType"] == f"video/{video_codec_type}"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    # ここで libvpx になって失敗する
    assert outbound_rtp_stats["encoderImplementation"] == expected_implementation
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0


@pytest.mark.skipif(os.environ.get("INTEL_VPL") is None, reason="Intel VPL でのみ実行する")
def test_intel_vpl_decoding_vp9(setup):
    """
    VPL VP9 はデコーダーは利用できるので、そのテスト
    """
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
        video_codec_type="VP9",
        metadata=metadata,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.VP9,
                    # VPL で VP9 Encoder は正常に動作しないので無効化しているので INTERNAL を指定
                    encoder=SoraVideoCodecImplementation.INTERNAL,
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
                    type=SoraVideoCodecType.VP9,
                    decoder=SoraVideoCodecImplementation.INTEL_VPL,
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
    assert "VP9" in sendonly.offer_message["sdp"]

    # answer の sdp に video_codec_type が含まれているかどうかを確認している
    assert sendonly.answer_message is not None
    assert "sdp" in sendonly.answer_message
    assert "VP9" in sendonly.answer_message["sdp"]

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    # VP9 が採用されているかどうか確認する
    assert sendonly_codec_stats["mimeType"] == "video/VP9"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    assert outbound_rtp_stats["encoderImplementation"] == "libvpx"
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(s for s in recvonly_stats if s.get("type") == "codec")
    # VP9 が採用されているかどうか確認する
    assert recvonly_codec_stats["mimeType"] == "video/VP9"

    # inbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in recvonly_stats if s.get("type") == "inbound-rtp")
    assert inbound_rtp_stats["decoderImplementation"] == "libvpl"
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0
