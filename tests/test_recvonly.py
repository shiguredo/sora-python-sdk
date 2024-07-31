import time
from typing import Any

from client import Recvonly


def test_recvonly(setup: dict[str, Any]):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")
    channel_id = f"{channel_id_prefix}{__name__}"

    recvonly = Recvonly(signaling_urls, channel_id, metadata)

    recvonly.connect()

    time.sleep(3)

    recvonly.disconnect()
