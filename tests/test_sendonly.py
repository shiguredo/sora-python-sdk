import json
import threading
import time
from threading import Event

import numpy as np

from sora_sdk import Sora


class Sendonly:
    def __init__(self, signaling_urls, channel_id, metadata):
        self.sora = Sora()
        self._connected = Event()
        self._disconnected = False

        self.connection = self.sora.create_connection(
            signaling_urls=signaling_urls,
            role="sendrecv",
            channel_id=channel_id,
            metadata=metadata,
        )

        self.is_data_channel_ready = False

        self.connection.on_set_offer = self.on_set_offer
        self.connection.on_notify = self.on_notify
        self.connection.on_disconnect = self.on_disconnect

        self.connection_id = None

        self._video_source = self.sora.create_video_source()
        self._video_height = 480
        self._video_width = 640

    def connect(self):
        self.connection.connect()

        self.thread = threading.Thread(target=self._video_input_loop, daemon=True)
        self.thread.start()

        assert self._connected.wait(30)

        return self

    def _video_input_loop(self):
        while not self._disconnected:
            time.sleep(1.0 / 30)
            self._video_source.on_captured(
                np.zeros((self._video_height, self._video_width, 3), dtype=np.uint8)
            )

    def on_set_offer(self, raw_offer):
        offer = json.loads(raw_offer)
        if offer["type"] == "offer":
            self.connection_id = offer["connection_id"]
            print(f"Offer を受信しました: connection_id={self.connection_id}")

    def on_notify(self, raw_message):
        message = json.loads(raw_message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self.connection_id
        ):
            print(f"Sora に接続しました: connection_id={self.connection_id}")
            self._connected.set()

    def on_disconnect(self, error_code, message):
        print(f"Sora から切断しました: error_code='{error_code}' message='{message}'")
        self._disconnected = True
        self._connected.set()

    def disconnect(self):
        self.connection.disconnect()
        self.thread.join()


def test_sendonly(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id = setup.get("channel_id")
    metadata = setup.get("metadata")

    sendonly = Sendonly(signaling_urls, channel_id, metadata)
    sendonly.connect()

    time.sleep(3)

    sendonly.disconnect()
