import json
import time
from threading import Event
from typing import Any

from client import SoraClient, SoraRole
from conftest import Settings

from sora_sdk import (
    Sora,
    SoraAudioFrame,
    SoraAudioStreamSink,
    SoraMediaTrack,
    SoraVAD,
)


class VAD:
    def __init__(
        self,
        settings: Settings,
        metadata: dict[str, Any] | None = None,
        jwt_private_claims: dict[str, Any] | None = None,
    ):
        self._signaling_urls: list[str] = settings.signaling_urls
        self._channel_id: str = settings.channel_id

        if jwt_private_claims is not None:
            access_token = settings.access_token(**jwt_private_claims)
        else:
            access_token = settings.access_token()

        # secret が設定されていない場合は access_token が存在しない
        if access_token is not None:
            if metadata is not None:
                # metadata が設定されている場合は access_token を追加する
                metadata.update({"access_token": access_token})
            else:
                # metadata が設定されていない場合は access_token のみを metadata に設定する
                metadata = {"access_token": access_token}

        self._vad = SoraVAD()

        self._connection_id: str

        # 接続した
        self._connected: Event = Event()
        # 終了
        self._disconnected = Event()

        self._audio_output_frequency: int = 24000
        self._audio_output_channels: int = 1

        self._sora = Sora()

        self._connection = self._sora.create_connection(
            signaling_urls=self._signaling_urls,
            role="recvonly",
            channel_id=self._channel_id,
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
        self._disconnected.set()
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


def test_vad(settings):
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=True,
        video=False,
    )
    sendonly.connect(fake_audio=True)

    vad = VAD(settings)
    vad.connect()

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()
    vad_stats = vad.get_stats()

    sendonly.disconnect()
    vad.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
    assert sendonly_codec_stats["mimeType"] == "audio/opus"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
    # audio には encoderImplementation が無い
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    vad_codec_stats = next(s for s in vad_stats if s.get("type") == "codec")
    assert vad_codec_stats["mimeType"] == "audio/opus"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(s for s in vad_stats if s.get("type") == "inbound-rtp")
    # audio には decoderImplementation が無い
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0
