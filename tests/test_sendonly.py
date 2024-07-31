import sys
import time

from client import Sendonly


def test_sendonly_vp8(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}"

    sendonly = Sendonly(signaling_urls, channel_id, metadata, video_codec_type="VP8")
    sendonly.connect()

    time.sleep(5)

    sendonly.disconnect()


def test_sendonly_vp9(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}"

    sendonly = Sendonly(signaling_urls, channel_id, metadata, video_codec_type="VP9")
    sendonly.connect()

    time.sleep(5)

    sendonly.disconnect()


def test_sendonly_av1(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}"

    sendonly = Sendonly(signaling_urls, channel_id, metadata, video_codec_type="AV1")
    sendonly.connect()

    time.sleep(5)

    sendonly.disconnect()
