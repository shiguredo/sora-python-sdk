import time

from client import Sendonly


def test_sendonly(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")
    openh264_path = setup.get("openh264_path")

    channel_id = f"{channel_id_prefix}_{__name__}"

    sendonly = Sendonly(
        signaling_urls,
        channel_id,
        metadata,
        openh264_path=openh264_path,
    )
    sendonly.connect()

    time.sleep(5)

    sendonly.disconnect()
