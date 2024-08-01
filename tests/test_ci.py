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

    closed = threading.Event()
    connected = threading.Event()

    def _on_signaling_notify(message):
        print(message)

    def _on_disconnect(error_code, message):
        print(f"Sora から切断しました: error_code='{error_code}' message='{message}'")
        closed.set()
        print(10)
        connected.clear()
        print(20)

    connection.on_notify = _on_signaling_notify
    connection.on_disconnect = _on_disconnect

    def _video_input_loop():
        while not closed.is_set():
            time.sleep(1.0 / 30)
            video_source.on_captured(np.zeros((480, 640, 3), dtype=np.uint8))

    connection.connect()

    video_input_thread = threading.Thread(target=_video_input_loop, daemon=True)
    video_input_thread.start()

    time.sleep(3)

    print(30)
    connection.disconnect()

    print(40)
    # video_input_thread.join(timeout=5)
