import json
import os
import time

from sora_sdk import Sora


class Recvonly:
    def __init__(self, signaling_urls, channel_id, metadata):
        self.sora = Sora()
        self.connection = self.sora.create_connection(
            signaling_urls=signaling_urls,
            role="sendrecv",
            channel_id=channel_id,
            metadata=metadata,
        )

        self.connected = False
        self.closed = False
        self.is_data_channel_ready = False

        self.connection.on_set_offer = self.on_set_offer
        self.connection.on_notify = self.on_notify
        self.connection.on_disconnect = self.on_disconnect

        self.connection_id = None

    def on_set_offer(self, raw_offer):
        offer = json.loads(raw_offer)
        if offer["type"] == "offer":
            self.connection_id = offer["connection_id"]

    def on_notify(self, raw_message):
        message = json.loads(raw_message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self.connection_id
        ):
            print(f"Sora に接続しました: connection_id={self.connection_id}")
            self.connected = True

    def on_disconnect(self, error_code, message):
        print(f"Sora から切断しました: error_code='{error_code}' message='{message}'")
        self.closed = True

    def connect(self):
        self.connection.connect()

    def disconnect(self):
        self.connection.disconnect()


def test_recvonly(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id = setup.get("channel_id")
    metadata = setup.get("metadata")

    recvonly = Recvonly(signaling_urls, channel_id, metadata)

    assert recvonly.connected is False

    recvonly.connect()

    time.sleep(3)

    assert recvonly.connected is True

    time.sleep(3)

    assert recvonly.closed is False

    recvonly.disconnect()

    time.sleep(3)

    assert recvonly.closed is True
