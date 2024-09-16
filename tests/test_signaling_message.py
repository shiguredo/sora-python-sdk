import random
import sys
import time
import uuid

from client import Sendonly


def test_random_signaling_message(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    selected_audio = random.choice([True, False])
    selected_video = random.choice([True, False])

    sendonly = Sendonly(
        signaling_urls,
        channel_id,
        audio=selected_audio,
        video=selected_video,
        metadata=metadata,
    )
    sendonly.connect(fake_audio=selected_audio, fake_video=selected_video)

    time.sleep(5)

    sendonly.disconnect()

    assert sendonly.connect_message is not None
    assert sendonly.offer_message is not None
    assert sendonly.answer_message is not None

    assert sendonly.connect_message["role"] == "sendonly"
    assert sendonly.connect_message["channel_id"] is channel_id
    assert sendonly.connect_message["audio"] is selected_audio
    assert sendonly.connect_message["video"] is selected_video
    assert sendonly.connect_message["metadata"] == metadata
