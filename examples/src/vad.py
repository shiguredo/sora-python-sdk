import json
import os
from threading import Event
from typing import Any, Optional

from dotenv import load_dotenv
from sora_sdk import (
    Sora,
    SoraAudioFrame,
    SoraAudioStreamSink,
    SoraMediaTrack,
    SoraVAD,
)


class VAD:
    def __init__(
        self, signaling_urls: list[str], channel_id: str, metadata: Optional[dict[str, Any]]
    ):
        self._signaling_urls: list[str] = signaling_urls
        self._channel_id: str = channel_id

        self._vad = SoraVAD()

        self._connection_id: str

        # 接続した
        self._connected: Event = Event()
        # 終了
        self._closed = Event()

        self._audio_output_frequency: int = 24000
        self._audio_output_channels: int = 1

        self._sora = Sora()

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

    def disconnect(self):
        self._connection.disconnect()

    def get_stats(self):
        raw_stats = self._connection.get_stats()
        stats = json.loads(raw_stats)
        return stats

    def _on_set_offer(self, raw_offer):
        offer = json.loads(raw_offer)
        if offer["type"] == "offer":
            self._connection_id = offer["connection_id"]
            print(f"Received 'Offer': connection_id={self._connection_id}")

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

    def run(self) -> None:
        """ビデオフレームの受信と表示、および音声の再生を行うメインループ。"""
        self.connect()
        try:
            while self._connected.is_set():
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self.disconnect()


def vad() -> None:
    """
    環境変数を使用して Sendonly インスタンスを設定し実行します。

    :raises ValueError: 必要な環境変数が設定されていない場合
    """
    load_dotenv()

    if not (raw_signaling_urls := os.getenv("SORA_SIGNALING_URLS")):
        raise ValueError("環境変数 SORA_SIGNALING_URLS が設定されていません")
    signaling_urls = raw_signaling_urls.split(",")

    if not (channel_id := os.getenv("SORA_CHANNEL_ID")):
        raise ValueError("環境変数 SORA_CHANNEL_ID が設定されていません")

    metadata = None
    if raw_metadata := os.getenv("SORA_METADATA"):
        metadata = json.loads(raw_metadata)

    vad = VAD(
        signaling_urls,
        channel_id,
        metadata=metadata,
    )
    vad.run()


if __name__ == "__main__":
    vad()
