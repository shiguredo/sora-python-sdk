import json
import sys
import time
import uuid

from sora_sdk import Sora, SoraConnection, SoraVideoSource


class Sendonly:
    def __init__(
        self,
        signaling_urls: list[str],
        channel_id: str,
        metadata: dict,
    ):
        self._signaling_urls: list[str] = signaling_urls
        self._channel_id: str = channel_id

        self._connection_id: str | None = None

        # 接続した
        # self._connected = Event()

        self._sora: Sora = Sora()

        self._video_source: SoraVideoSource = self._sora.create_video_source()

        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="sendonly",
            channel_id=channel_id,
            metadata=metadata,
            audio=False,
            video=True,
            video_source=self._video_source,
        )

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_notify = self._on_notify

    def _on_set_offer(self, raw_offer: str):
        offer = json.loads(raw_offer)
        if offer["type"] == "offer":
            self._connection_id = offer["connection_id"]

    def _on_notify(self, raw_message: str):
        message = json.loads(raw_message)
        print(message)
        # if (
        #     message["type"] == "notify"
        #     and message["event_type"] == "connection.created"
        #     and message["connection_id"] == self._connection_id
        # ):
        # print(f"Sora に接続しました: connection_id={self._connection_id}")
        # self._connected.set()

    def connect(self):
        self._connection.connect()

        # _connected が set されるまで 30 秒待つ
        # assert self._connected.wait(30)

    def disconnect(self):
        self._connection.disconnect()


def test_sora(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = Sendonly(
        signaling_urls=signaling_urls,
        channel_id=channel_id,
        metadata=metadata,
    )

    sendonly.connect()

    time.sleep(5)

    sendonly.disconnect()
