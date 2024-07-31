import json
import time
from threading import Event
from typing import Any

from sora_sdk import (
    Sora,
    SoraAudioFrame,
    SoraAudioStreamSink,
    SoraMediaTrack,
    SoraVAD,
)


class VAD:
    def __init__(self, signaling_urls: list[str], channel_id: str, metadata: dict[str, Any]):
        self._signaling_urls: list[str] = signaling_urls
        self._channel_id: str = channel_id

        self._vad = SoraVAD()

        self._connection_id: str

        # 接続した
        self._connected: Event = Event()
        # 終了
        self._closed: bool = False

        self._audio_output_frequency: int = 24000
        self._audio_output_channels: int = 1

        self._sora = Sora()
        self._connected = Event()

        self._connection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="recvonly",
            channel_id=channel_id,
            metadata=metadata,
            audio=True,
            video=False,
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

    def _on_set_offer(self, raw_offer):
        offer = json.loads(raw_offer)
        if offer["type"] == "offer":
            self._connection_id = offer["connection_id"]
            print(f"Offer を受信しました: connection_id={self._connection_id}")

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

    def _on_frame(self, frame: SoraAudioFrame):
        # frame が音声である確率を求める
        voice_probability = self._vad.analyze(frame)
        if voice_probability > 0.95:  # 0.95 は libwebrtc の判定値
            print(f"Voice! voice_probability={voice_probability}")
        else:
            pass

    def _on_track(self, track: SoraMediaTrack):
        if track.kind == "audio":
            # SoraAudioStreamSink
            self._audio_stream_sink = SoraAudioStreamSink(
                track, self._audio_output_frequency, self._audio_output_channels
            )
            self._audio_stream_sink.on_frame = self._on_frame

    def disconnect(self):
        self._connection.disconnect()


def test_vad(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}"

    sendonly = VAD(signaling_urls, channel_id, metadata)
    sendonly.connect()

    time.sleep(5)

    sendonly.disconnect()
