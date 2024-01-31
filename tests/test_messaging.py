import json
import time
from threading import Event

from sora_sdk import Sora, SoraConnection


class Messaging:
    _sora: Sora
    _connection: SoraConnection

    _connection_id: str

    _connected: Event = Event()
    _closed: bool = False

    _label: str
    _is_data_channel_ready: bool = False

    def __init__(
        self, signaling_urls: list, channel_id: str, label: str, direction: str, metadata: dict
    ):
        self._sora = Sora()
        self._connection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="sendrecv",
            channel_id=channel_id,
            metadata=metadata,
            audio=False,
            video=False,
            data_channels=[{"label": label, "direction": direction}],
            data_channel_signaling=True,
        )

        self._label = label

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_notify = self._on_notify

        self._connection.on_data_channel = self._on_data_channel
        self._connection.on_message = self._on_message

        self._connection.on_disconnect = self._on_disconnect

    def _on_set_offer(self, raw_offer):
        offer = json.loads(raw_offer)
        if offer["type"] == "offer":
            self._connection_id = offer["connection_id"]

    def _on_notify(self, raw_message):
        message = json.loads(raw_message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            print(f"Sora に接続しました: connection_id={self._connection_id}")
            self._connected.set()

    def _on_disconnect(self, error_code, message):
        print(f"Sora から切断しました: error_code='{error_code}' message='{message}'")
        self._closed = True
        self._connected.clear()

    def _on_message(self, label, data):
        print(f"メッセージを受信しました: label={label}, data={data}")

    def _on_data_channel(self, label: str):
        if self._label == label:
            self._is_data_channel_ready = True

    def connect(self):
        self._connection.connect()

        assert self._connected.wait(30)

        return self

    def send(self, data: bytes):
        # on_data_channel() が呼ばれるまではデータチャネルの準備ができていないので待機
        while not self._is_data_channel_ready and not self._closed:
            time.sleep(0.01)

        self._connection.send_data_channel(self._label, data)
        print(f"メッセージを送信しました: label={self._label}, data={data}")

    def disconnect(self):
        self._connection.disconnect()


def test_messaging_direction_recvonly(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}{__name__}"

    label = "#spam"

    msg_recvonly = Messaging(signaling_urls, channel_id, label, "recvonly", metadata)
    msg_sendonly = Messaging(signaling_urls, channel_id, label, "sendonly", metadata)

    msg_recvonly.connect()
    msg_sendonly.connect()

    time.sleep(3)

    msg_sendonly.send(b"Hello, world!")

    time.sleep(3)

    msg_recvonly.disconnect()
    msg_sendonly.disconnect()
