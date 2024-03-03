import json
import time
from threading import Event
from typing import Any, Dict, List

from sora_sdk import Sora, SoraConnection, SoraMediaTrack


class Recvonly:
    def __init__(self, signaling_urls: List[str], channel_id: str, metadata: Dict[str, Any]):
        self._signaling_urls: List[str] = signaling_urls
        self._channel_id: str = channel_id

        self._connection_id: str

        # 接続した
        self._connected = Event()
        # 終了
        self._closed = False

        self._sora: Sora = Sora()
        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="sendrecv",
            channel_id=channel_id,
            metadata=metadata,
        )

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect

        self._connection.on_track = self._on_track

    def connect(self):
        self._connection.connect()

        # _connected が set されるまで 30 秒待つ
        assert self._connected.wait(30)

        return self

    def _on_track(self, track: SoraMediaTrack):
        if track.kind == "audio":
            pass
        if track.kind == "video":
            pass

    def _on_set_offer(self, raw_offer: str):
        offer = json.loads(raw_offer)
        if offer["type"] == "offer":
            self._connection_id = offer["connection_id"]

    def _on_notify(self, raw_message: str):
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

    def disconnect(self):
        self._connection.disconnect()


def test_recvonly(setup: Dict[str, Any]):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")
    channel_id = f"{channel_id_prefix}{__name__}"

    recvonly = Recvonly(signaling_urls, channel_id, metadata)

    recvonly.connect()

    time.sleep(3)

    recvonly.disconnect()
