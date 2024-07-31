import time

from client import Sendonly


def test_get_stats(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}"

    client = Sendonly(signaling_urls, channel_id, metadata, "VP8")
    client.connect()

    time.sleep(5)

    stats = client.get_stats()
    assert len(stats) > 0

    client.disconnect()
