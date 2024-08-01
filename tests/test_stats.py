import sys
import time
import uuid

from client import Sendonly


def test_get_stats(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = Sendonly(signaling_urls, channel_id, metadata)
    sendonly.connect()

    time.sleep(5)

    stats = sendonly.get_stats()
    assert len(stats) > 0

    sendonly.disconnect()
