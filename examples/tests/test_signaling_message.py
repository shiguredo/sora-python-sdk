import sys
import time
import uuid

from media import Sendonly


def test_signaling_message(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = Sendonly(
        signaling_urls,
        channel_id,
        audio=False,
        video=True,
        metadata=metadata,
    )
    sendonly.connect(fake_audio=True)

    time.sleep(5)

    assert sendonly.connect_message is not None
    assert sendonly.offer_message is not None
    assert sendonly.answer_message is not None

    sendonly.disconnect()
