import sys
import threading
import time
import uuid

import numpy as np
from sora_sdk import Sora


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

    def _on_signaling_notify(message):
        print(message)

    connection.on_notify = _on_signaling_notify

    def _video_input_loop(self):
        while not self._closed:
            time.sleep(1.0 / 30)
            self._video_source.on_captured(
                np.zeros((self._video_height, self._video_width, 3), dtype=np.uint8)
            )

    video_input_thread = threading.Thread(target=_video_input_loop, daemon=True)
    video_input_thread.start()

    connection.connect()

    time.sleep(3)

    connection.disconnect()

    video_input_thread.join(timeout=10)
