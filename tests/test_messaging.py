import json
import sys
import time
import uuid
from threading import Event
from typing import Any

from sora_sdk import Sora, SoraConnection


class Messaging:
    def __init__(
        self,
        signaling_urls: list[str],
        channel_id: str,
        label: str,
        direction: str,
        metadata: dict[str, Any],
    ):
        self._connection_id: str

        self._signaling_urls: list[str] = signaling_urls
        self._channel_id: str = channel_id

        self._connected: Event = Event()
        self._switched: bool = False
        self._closed: Event = Event()

        self._label: str = label

        self._sora: Sora = Sora()
        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=self._signaling_urls,
            role="sendrecv",
            channel_id=self._channel_id,
            metadata=metadata,
            audio=False,
            video=False,
            data_channels=[{"label": label, "direction": direction}],
            data_channel_signaling=True,
        )

        self._is_data_channel_ready: bool = False

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_switched = self._on_switched
        self._connection.on_notify = self._on_notify
        self._connection.on_data_channel = self._on_data_channel
        self._connection.on_message = self._on_message

        self._connection.on_disconnect = self._on_disconnect

    def connect(self):
        self._connection.connect()

        assert self._connected.wait(30), "Could not connect to Sora."

        return self

    def disconnect(self):
        self._connection.disconnect()

    def get_stats(self):
        raw_stats = self._connection.get_stats()
        return json.loads(raw_stats)

    def send(self, data: bytes):
        # on_data_channel() が呼ばれるまではデータチャネルの準備ができていないので待機
        while not self._is_data_channel_ready and not self._closed:
            time.sleep(0.01)

        self._connection.send_data_channel(self._label, data)
        print(f"Sent message: label={self._label}, data={data.decode()}")

    @property
    def connected(self):
        return self._connected.is_set()

    @property
    def switched(self):
        return self._switched

    @property
    def closed(self):
        return self._closed.is_set()

    def _on_set_offer(self, raw_offer):
        offer = json.loads(raw_offer)
        if offer["type"] == "offer":
            self._connection_id = offer["connection_id"]

    def _on_switched(self, raw_message):
        message = json.loads(raw_message)
        if message["type"] == "switched":
            print(f"Switched DataChannel Signaling: connection_id={self._connection_id}")
            self._switched = True

    def _on_notify(self, raw_message):
        message = json.loads(raw_message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            print(f"Connected Sora: connection_id={self._connection_id}")
            self._connected.set()

    def _on_disconnect(self, error_code, message):
        print(f"Disconnected Sora: error_code='{error_code}' message='{message}'")
        self._connected.clear()
        self._closed.set()

    def _on_message(self, label, data):
        print(f"Received message: label={label}, data={data}")

    def _on_data_channel(self, label: str):
        if self._label == label:
            self._is_data_channel_ready = True


def test_messaging_direction_recvonly(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    label = "#spam"

    msg_recvonly = Messaging(signaling_urls, channel_id, label, "recvonly", metadata)
    msg_sendonly = Messaging(signaling_urls, channel_id, label, "sendonly", metadata)

    msg_recvonly.connect()
    msg_sendonly.connect()

    time.sleep(3)

    assert msg_sendonly.switched
    assert msg_recvonly.switched

    msg = b"Hello, world!"
    msg_sendonly.send(msg)

    time.sleep(3)

    msg_sendonly_stats = msg_sendonly.get_stats()
    msg_recvonly_stats = msg_recvonly.get_stats()

    msg_recvonly.disconnect()
    msg_sendonly.disconnect()

    sendonly_data_channel_stats = next(
        s for s in msg_sendonly_stats if s.get("type") == "data-channel" and s.get("label") == label
    )
    assert sendonly_data_channel_stats["state"] == "open"
    assert sendonly_data_channel_stats["messagesSent"] == 1
    assert sendonly_data_channel_stats["bytesSent"] == len(msg)

    recvonly_data_channel_stats = next(
        s for s in msg_recvonly_stats if s.get("type") == "data-channel" and s.get("label") == label
    )
    assert recvonly_data_channel_stats["state"] == "open"
    assert recvonly_data_channel_stats["messagesReceived"] == 1
    assert recvonly_data_channel_stats["bytesReceived"] == len(msg)
