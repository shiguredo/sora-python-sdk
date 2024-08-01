import sys
import time
import uuid

from sora_sdk import Sora


def _on_signaling_notify(message):
    print(message)


def test_sora(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sora = Sora()

    video_source = sora.create_video_source()

    connection = sora.create_connection(
        signaling_urls=signaling_urls,
        role="sendonly",
        channel_id=channel_id,
        metadata=metadata,
        audio=False,
        video=True,
        video_source=video_source,
    )

    # connection.on_notify = _on_signaling_notify

    connection.connect()

    time.sleep(5)

    connection.disconnect()
