import json
import logging
import os
import queue
import resource
import threading
import time
from threading import Event
from typing import Any

import numpy

from sora_sdk import (
    Sora,
    SoraConnection,
    SoraSignalingErrorCode,
    SoraTrackInterface,
)

soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (4096, hard))


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

signaling_urls = os.environ.get("TEST_SIGNALING_URLS")
signaling_urls = signaling_urls.split(",")
video_codec_type = "H264"
openh264_path = os.getenv("OPENH264_PATH")
role_str = "sendrecv"
secret_key = os.environ.get("TEST_SECRET_KEY")
metadata = {"access_token": secret_key}
channel_id_prefix = os.environ.get("TEST_CHANNEL_ID_PREFIX")

data_channels = [
    {
        "compress": False,
        "direction": role_str,
        "label": "#abc",
        "ordered": True,
    }
]


class TestConnection:
    def __init__(
        self,
        signaling_urls: list[str],
        channel_id: str,
        role: str,
        metadata: dict[str, Any] | None = None,
        audio: bool | None = None,
        video: bool | None = None,
        video_codec_type: str | None = None,
        video_bit_rate: int | None = None,
        audio_bit_rate: int | None = None,
        data_channels: list[dict[str, Any]] | None = None,
        data_channel_signaling: bool | None = None,
        spotlight: bool | None = None,
        spotlight_number: int | None = None,
        openh264_path: str | None = None,
        audio_channels: int = 1,
        audio_sample_rate: int = 16000,
        insecure: bool = False,
        ca_cert: str | None = None,
        client_cert: str | None = None,
        client_key: str | None = None,
    ):
        """
        TestConnection インスタンスを初期化します。
        """
        self._signaling_urls: list[str] = signaling_urls
        self._channel_id: str = channel_id

        self._audio_channels: int = audio_channels
        self._audio_sample_rate: int = audio_sample_rate

        self._sora: Sora = Sora(
            openh264=openh264_path,
        )

        self._audio_thread: threading.Thread | None = None
        self._video_thread: threading.Thread | None = None

        self._audio_source = self._sora.create_audio_source(
            self._audio_channels, self._audio_sample_rate
        )
        self._video_source = self._sora.create_video_source()

        ca_cert_bytes = None
        if ca_cert is not None:
            with open(ca_cert) as f:
                readed_ca_cert = f.read()
            ca_cert_bytes = readed_ca_cert.encode("utf-8")

        client_cert_bytes = None
        if client_cert is not None:
            with open(client_cert) as f:
                readed_client_cert = f.read()
            client_cert_bytes = readed_client_cert.encode("utf-8")

        client_key_bytes = None
        if client_key is not None:
            with open(client_key) as f:
                readed_client_key = f.read()
            client_key_bytes = readed_client_key.encode("utf-8")

        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role=role,
            channel_id=channel_id,
            metadata=metadata,
            audio=audio,
            video=video,
            video_codec_type=video_codec_type,
            video_bit_rate=video_bit_rate,
            audio_bit_rate=audio_bit_rate,
            data_channels=data_channels,
            data_channel_signaling=data_channel_signaling,
            spotlight=spotlight,
            spotlight_number=spotlight_number,
            audio_source=self._audio_source,
            video_source=self._video_source,
            insecure=insecure,
            ca_cert=ca_cert_bytes,
            client_cert=client_cert_bytes,
            client_key=client_key_bytes,
        )
        self._connection_id: str | None = None

        self._connected: Event = Event()
        self._switched: bool = False
        self._closed: Event = Event()
        self._default_connection_timeout_s: float = 30.0

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_switched = self._on_switched
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect
        self._connection.on_track = self._on_track

    def connect(self, fake_audio=False, fake_video=False) -> "TestConnection":
        """
        Sora への接続を確立します。

        :raises AssertionError: タイムアウト期間内に接続が確立できなかった場合
        """
        self._connection.connect()

        if fake_audio:
            self._audio_thread = threading.Thread(target=self._fake_audio_loop, daemon=True)
            self._audio_thread.start()

        if fake_video:
            self._video_thread = threading.Thread(target=self._fake_video_loop, daemon=True)
            self._video_thread.start()

        return self

    def wait_connected(self) -> bool:
        assert self._connected.wait(self._default_connection_timeout_s), (
            "Could not connect to Sora."
        )
        return self.connected

    def wait_closed(self) -> bool:
        assert self._closed.wait(self._default_connection_timeout_s), (
            "Could not disconnect to Sora."
        )
        return self.closed

    def disconnect(self) -> None:
        """Sora から切断します。"""
        self._connection.disconnect()

    def get_stats(self):
        raw_stats = self._connection.get_stats()
        return json.loads(raw_stats)

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    @property
    def switched(self) -> bool:
        return self._switched

    def _fake_audio_loop(self):
        while not self.closed:
            time.sleep(0.02)
            self._audio_source.on_data(numpy.zeros((320, 1), dtype=numpy.int16))

    def _fake_video_loop(self):
        while not self.closed:
            time.sleep(1.0 / 30)
            self._video_source.on_captured(numpy.zeros((480, 640, 3), dtype=numpy.uint8))

    def _on_set_offer(self, raw_message: str) -> None:
        """
        オファー設定イベントを処理します。

        :param raw_message: オファーを含む生のメッセージ
        """
        message: dict[str, Any] = json.loads(raw_message)
        if message["type"] == "offer":
            self._connection_id = message["connection_id"]

    def _on_switched(self, raw_message: str) -> None:
        message = json.loads(raw_message)
        if message["type"] == "switched":
            logger.info(f"Switched to DataChannel Signaling: connection_id={self._connection_id}")
            self._switched = True

    def _on_notify(self, raw_message: str) -> None:
        """
        Sora からの通知イベントを処理します。

        :param raw_message: 生の通知メッセージ
        """
        message: dict[str, Any] = json.loads(raw_message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            logger.info(f"Connected Sora: connection_id={self._connection_id}")
            self._connected.set()

    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str) -> None:
        """
        切断イベントを処理します。

        :param error_code: 切断のエラーコード
        :param message: 切断メッセージ
        """
        logger.info(f"Disconnected Sora: error_code='{error_code}' message='{message}'")
        self._connected.clear()
        self._closed.set()

        if self._audio_thread is not None:
            self._audio_thread.join(timeout=10)

        if self._video_thread is not None:
            self._video_thread.join(timeout=10)

    def _on_track(self, track: SoraTrackInterface) -> None:
        """
        トラック受信時のコールバック

        :param track: 受信したトラック
        """
        if track.kind == "audio":
            logger.debug("audio")

        if track.kind == "video":
            logger.debug("video")


class Test:
    def __init__(self):
        self.m_q = queue.Queue()

    def _one(self):
        try:
            channel_id = channel_id_prefix + "hogefugapiyo"
            tc = TestConnection(
                signaling_urls,
                channel_id,
                role_str,
                audio=True,
                video=True,
                video_codec_type=video_codec_type,
                video_bit_rate=330,
                audio_bit_rate=12,
                openh264_path=openh264_path,
                data_channels=data_channels,
                spotlight=True,
                spotlight_number=5,
                metadata=metadata,
            )
            conn = tc.connect(True, True)
            if not conn.wait_connected():
                raise Exception("Failed to wait connected")

            self.m_q.put(channel_id)
            time.sleep(1)
            if self.m_q.get(timeout=10) != "hoge":
                raise Exception("hoge")
            self.m_q.task_done()
            conn.disconnect()
            if not conn.wait_closed():
                raise Exception("Failed to wait disconnected")
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.exception(e)

    def _two(self):
        try:
            channel_id = self.m_q.get(timeout=10)
            self.m_q.task_done()
            tc = TestConnection(
                signaling_urls,
                channel_id,
                role_str,
                audio=True,
                video=True,
                video_codec_type=video_codec_type,
                video_bit_rate=330,
                audio_bit_rate=12,
                openh264_path=openh264_path,
                data_channels=data_channels,
                spotlight=True,
                spotlight_number=5,
                metadata=metadata,
            )
            conn = tc.connect(True, True)
            if not conn.wait_connected():
                raise Exception("Failed to wait connected")
            time.sleep(1)
            conn.disconnect()
            if not conn.wait_closed():
                raise Exception("Failed to wait disconnected")
            self.m_q.put("hoge")
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.exception(e)

    def scenario(self):
        one_thread = threading.Thread(target=self._one)
        two_thread = threading.Thread(target=self._two)

        one_thread.start()
        two_thread.start()

        one_thread.join()
        two_thread.join()


def run():
    t = Test()
    while True:
        t.scenario()
        time.sleep(5)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
