import sys
import time
import uuid

from sora_sdk import Sora


def test_sora(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sora = Sora()
    connection = sora.create_connection(
        signaling_urls=signaling_urls,
        role="sendonly",
        channel_id=channel_id,
        metadata=metadata,
        audio=False,
        video=True,
    )

    connection.connect()

    time.sleep(5)

    connection.disconnect()
