import sys
import time
import uuid

from media import Sendonly


def test_switched(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = Sendonly(signaling_urls, channel_id, metadata=metadata, data_channel_signaling=True)
    sendonly.connect()

    time.sleep(3)

    assert sendonly.switched

    sendonly.disconnect()
