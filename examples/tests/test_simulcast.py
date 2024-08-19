import sys
import time
import uuid

from media import Sendonly


def test_simulcast(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    simulcast = Sendonly(
        signaling_urls,
        channel_id,
        simulcast=True,
        audio=False,
        video=True,
        video_codec_type="VP8",
        metadata=metadata,
    )
    simulcast.connect(fake_video=True)

    time.sleep(5)

    stats_report = simulcast.get_stats()

    simulcast.disconnect()

    codec_stats = next(
        s for s in stats_report if s.get("type") == "codec" and s.get("mimeType") == "video/VP8"
    )
    assert codec_stats["mimeType"] == "video/VP8"

    outbound_rtp_stats = sorted(
        filter(
            lambda s: s.get("type") == "outbound-rtp" and s.get("kind") == "video",
            stats_report,
        ),
        key=lambda s: s["rid"],  # 直接 s["rid"] を使用し、存在しない場合は KeyError を発生させる
    )
    assert len(outbound_rtp_stats) == 3

    print(outbound_rtp_stats)

    assert outbound_rtp_stats[0]["rid"] == "r0"
    assert outbound_rtp_stats[0]["active"] is True
    assert outbound_rtp_stats[0]["frameWidth"] == 240
    assert outbound_rtp_stats[0]["frameHeight"] == 128
    assert outbound_rtp_stats[0]["bytesSent"] > 0
    assert outbound_rtp_stats[0]["packetsSent"] > 0
    assert outbound_rtp_stats[0]["framesSent"] > 0
    assert outbound_rtp_stats[0]["scalabilityMode"] == "L1T1"
    assert (
        outbound_rtp_stats[0]["encoderImplementation"]
        == "SimulcastEncoderAdapter (libvpx, libvpx, libvpx)"
    )

    assert outbound_rtp_stats[1]["rid"] == "r1"
    assert outbound_rtp_stats[1]["active"] is True
    assert outbound_rtp_stats[1]["frameWidth"] == 480
    assert outbound_rtp_stats[1]["frameHeight"] == 256
    assert outbound_rtp_stats[1]["bytesSent"] > 0
    assert outbound_rtp_stats[1]["packetsSent"] > 0
    assert outbound_rtp_stats[1]["framesSent"] > 0
    assert outbound_rtp_stats[1]["scalabilityMode"] == "L1T1"
    assert (
        outbound_rtp_stats[1]["encoderImplementation"]
        == "SimulcastEncoderAdapter (libvpx, libvpx, libvpx)"
    )

    assert outbound_rtp_stats[2]["rid"] == "r2"
    assert outbound_rtp_stats[2]["active"] is True
    assert outbound_rtp_stats[2]["frameWidth"] == 960
    assert outbound_rtp_stats[2]["frameHeight"] == 528
    assert outbound_rtp_stats[2]["bytesSent"] > 0
    assert outbound_rtp_stats[2]["packetsSent"] > 0
    assert outbound_rtp_stats[2]["framesSent"] > 0
    assert outbound_rtp_stats[2]["scalabilityMode"] == "L1T1"
    assert (
        outbound_rtp_stats[2]["encoderImplementation"]
        == "SimulcastEncoderAdapter (libvpx, libvpx, libvpx)"
    )
