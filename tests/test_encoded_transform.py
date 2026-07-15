from __future__ import annotations

import json
import threading
import time
from threading import Event
from typing import Any

import numpy
from conftest import Settings

from sora_sdk import (
    Sora,
    SoraAudioFrameTransformer,
    SoraAudioSource,
    SoraMediaTrack,
    SoraTransformableAudioFrame,
    SoraTransformableVideoFrame,
    SoraVideoFrameTransformer,
    SoraVideoSource,
)

# on_transform 発火待ちのタイムアウト（秒）
TRANSFORM_EVENT_TIMEOUT_S = 30.0


class SendonlyEncodedTransform:
    def __init__(
        self,
        settings: Settings,
        metadata: dict[str, Any] | None = None,
        jwt_private_claims: dict[str, Any] | None = None,
    ):
        self._signaling_urls: list[str] = settings.signaling_urls
        self._channel_id: str = settings.channel_id

        self._connection_id: str

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

        # 接続した
        self._connected: Event = Event()
        # 終了
        self._disconnected = Event()

        self._audio_channels: int = 1
        self._audio_sample_rate: int = 16000

        self._video_width: int = 960
        self._video_height: int = 540

        self._sora = Sora()

        self._fake_audio_thread: threading.Thread | None = None
        self._fake_video_thread: threading.Thread | None = None

        self._audio_source: SoraAudioSource | None = None
        self._audio_source = self._sora.create_audio_source(
            self._audio_channels, self._audio_sample_rate
        )

        self._video_source: SoraVideoSource | None = None
        self._video_source = self._sora.create_video_source()

        # Audio 向けの Encoded Transformer
        self._audio_transformer = SoraAudioFrameTransformer()
        # Audio のエンコードフレームを受け取るコールバック関数を on_transform に設定
        self._audio_transformer.on_transform = self._on_audio_transform

        # Video 向けの Encoded Transformer
        self._video_transformer = SoraVideoFrameTransformer()
        # Video のエンコードフレームを受け取るコールバック関数を on_transform に設定
        self._video_transformer.on_transform = self._on_video_transform

        self._connection = self._sora.create_connection(
            signaling_urls=self._signaling_urls,
            role="sendonly",
            channel_id=self._channel_id,
            metadata=metadata,
            audio=True,
            video=True,
            audio_source=self._audio_source,
            video_source=self._video_source,
            audio_frame_transformer=self._audio_transformer,
            video_frame_transformer=self._video_transformer,
        )

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect

        # callback 発火通知と結果保存（callback 内では assert しない）
        self._audio_transform_event = Event()
        self._video_transform_event = Event()
        self._audio_transform_error: BaseException | None = None
        self._video_transform_error: BaseException | None = None
        self._audio_transform_thread_id: int | None = None
        self._video_transform_thread_id: int | None = None

    def connect(self):
        self._connection.connect()

        self._fake_audio_thread = threading.Thread(target=self._fake_audio_loop, daemon=True)
        self._fake_audio_thread.start()

        self._fake_video_thread = threading.Thread(target=self._fake_video_loop, daemon=True)
        self._fake_video_thread.start()

        # _connected が set されるまで 30 秒待つ
        assert self._connected.wait(30)

        return self

    def disconnect(self):
        self._connection.disconnect()

    def get_stats(self):
        raw_stats = self._connection.get_stats()
        stats = json.loads(raw_stats)
        return stats

    def wait_transforms(self, timeout: float = TRANSFORM_EVENT_TIMEOUT_S) -> None:
        """送信側 Audio / Video の on_transform 発火を待つ"""
        assert self._audio_transform_event.wait(timeout), (
            "送信側 Audio on_transform が発火しなかった"
        )
        assert self._video_transform_event.wait(timeout), (
            "送信側 Video on_transform が発火しなかった"
        )

    def assert_transform_results(self, test_thread_id: int) -> None:
        """保存した callback 結果をテストスレッド側で検証する"""
        assert self._audio_transform_error is None, (
            f"送信側 Audio on_transform で例外: {self._audio_transform_error!r}"
        )
        assert self._video_transform_error is None, (
            f"送信側 Video on_transform で例外: {self._video_transform_error!r}"
        )
        assert self._audio_transform_thread_id is not None
        assert self._video_transform_thread_id is not None
        assert self._audio_transform_thread_id != test_thread_id
        assert self._video_transform_thread_id != test_thread_id

    def _fake_audio_loop(self):
        while not self._disconnected.is_set():
            time.sleep(0.02)
            if self._audio_source is not None:
                self._audio_source.on_data(numpy.zeros((320, 1), dtype=numpy.int16))

    def _fake_video_loop(self):
        while not self._disconnected.is_set():
            time.sleep(1.0 / 30)
            if self._video_source is not None:
                self._video_source.on_captured(
                    numpy.zeros((self._video_height, self._video_width, 3), dtype=numpy.uint8)
                )

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

        if self._fake_audio_thread is not None:
            self._fake_audio_thread.join(timeout=10)

        if self._fake_video_thread is not None:
            self._fake_video_thread.join(timeout=10)

    def _on_audio_transform(self, frame: SoraTransformableAudioFrame):
        # Encoded Transform の基本形。callback 内では assert せず結果を保存する
        try:
            self._audio_transform_thread_id = threading.get_ident()
            if not frame.mime_type.startswith("audio/"):
                raise AssertionError(f"想定外の audio mime_type: {frame.mime_type!r}")

            # frame からエンコードされたフレームデータを取得する
            new_data = frame.get_data()
            # "sora" を末尾に追加して受信側で検証できるようにする
            new_data = numpy.append(new_data, numpy.frombuffer(b"sora", dtype=numpy.uint8))
            frame.set_data(new_data)
            self._audio_transformer.enqueue(frame)
        except BaseException as exc:
            self._audio_transform_error = exc
        finally:
            self._audio_transform_event.set()

    def _on_video_transform(self, frame: SoraTransformableVideoFrame):
        # Encoded Transform の基本形。callback 内では assert せず結果を保存する
        try:
            self._video_transform_thread_id = threading.get_ident()
            if not frame.mime_type.startswith("video/"):
                raise AssertionError(f"想定外の video mime_type: {frame.mime_type!r}")

            new_data = frame.get_data()
            new_data = numpy.append(new_data, numpy.frombuffer(b"sora", dtype=numpy.uint8))
            frame.set_data(new_data)
            self._video_transformer.enqueue(frame)
        except BaseException as exc:
            self._video_transform_error = exc
        finally:
            self._video_transform_event.set()


class RecvonlyEncodedTransform:
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
            video=True,
        )

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect

        self._connection.on_track = self._on_track

        # callback 発火通知と結果保存（callback 内では assert しない）
        self._audio_transform_event = Event()
        self._video_transform_event = Event()
        self._audio_transform_error: BaseException | None = None
        self._video_transform_error: BaseException | None = None
        self._audio_transform_thread_id: int | None = None
        self._video_transform_thread_id: int | None = None
        self._audio_payload_ok = False
        self._video_payload_ok = False

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

    def wait_transforms(self, timeout: float = TRANSFORM_EVENT_TIMEOUT_S) -> None:
        """受信側 Audio / Video の on_transform 発火を待つ"""
        assert self._audio_transform_event.wait(timeout), (
            "受信側 Audio on_transform が発火しなかった"
        )
        assert self._video_transform_event.wait(timeout), (
            "受信側 Video on_transform が発火しなかった"
        )

    def assert_transform_results(self, test_thread_id: int) -> None:
        """保存した callback 結果をテストスレッド側で検証する"""
        assert self._audio_transform_error is None, (
            f"受信側 Audio on_transform で例外: {self._audio_transform_error!r}"
        )
        assert self._video_transform_error is None, (
            f"受信側 Video on_transform で例外: {self._video_transform_error!r}"
        )
        assert self._audio_payload_ok is True
        assert self._video_payload_ok is True
        assert self._audio_transform_thread_id is not None
        assert self._video_transform_thread_id is not None
        assert self._audio_transform_thread_id != test_thread_id
        assert self._video_transform_thread_id != test_thread_id

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

    def _on_track(self, track: SoraMediaTrack) -> None:
        if track.kind == "audio":
            # Audio 向けの Encoded Transformer
            self._audio_transformer = SoraAudioFrameTransformer()
            # Audio のエンコードフレームを受け取るコールバック関数を on_transform に設定
            self._audio_transformer.on_transform = self._on_audio_transform
            # Encoded Transformer を RTPReceiver に設定する
            track.set_frame_transformer(self._audio_transformer)
        if track.kind == "video":
            # Video 向けの Encoded Transformer
            self._video_transformer = SoraVideoFrameTransformer()
            # Video のエンコードフレームを受け取るコールバック関数を on_transform に設定
            self._video_transformer.on_transform = self._on_video_transform
            # Encoded Transformer を SoraMediaTrack に設定する
            track.set_frame_transformer(self._video_transformer)

    def _on_audio_transform(self, frame: SoraTransformableAudioFrame):
        # Encoded Transform の基本形。callback 内では assert せず結果を保存する
        try:
            self._audio_transform_thread_id = threading.get_ident()
            if not frame.mime_type.startswith("audio/"):
                raise AssertionError(f"想定外の audio mime_type: {frame.mime_type!r}")

            new_data = numpy.asarray(frame.get_data(), dtype=numpy.uint8)
            removed_data = new_data[-4:]
            self._audio_payload_ok = removed_data.tobytes() == b"sora"
            if not self._audio_payload_ok:
                raise AssertionError(f"想定外の audio trailer: {removed_data.tobytes()!r}")

            # 後ろ 4 バイトを取り除いて enqueue する
            frame.set_data(new_data[:-4])
            self._audio_transformer.enqueue(frame)
        except BaseException as exc:
            self._audio_transform_error = exc
        finally:
            self._audio_transform_event.set()

    def _on_video_transform(self, frame: SoraTransformableVideoFrame):
        # Encoded Transform の基本形。callback 内では assert せず結果を保存する
        try:
            self._video_transform_thread_id = threading.get_ident()
            if not frame.mime_type.startswith("video/"):
                raise AssertionError(f"想定外の video mime_type: {frame.mime_type!r}")

            new_data = numpy.asarray(frame.get_data(), dtype=numpy.uint8)
            removed_data = new_data[-4:]
            self._video_payload_ok = removed_data.tobytes() == b"sora"
            if not self._video_payload_ok:
                raise AssertionError(f"想定外の video trailer: {removed_data.tobytes()!r}")

            frame.set_data(new_data[:-4])
            self._video_transformer.enqueue(frame)
        except BaseException as exc:
            self._video_transform_error = exc
        finally:
            self._video_transform_event.set()


def test_encoded_transform(settings):
    """Encoded Transform の 4 経路が GIL 保持下で安全に動くことを実接続で確認する

    Audio / Video の送受信で on_transform を発火させ、get_data / set_data / enqueue
    と NumPy 操作を通過したうえで、切断前に結果を検証する。
    """
    test_thread_id = threading.get_ident()
    sendonly = SendonlyEncodedTransform(settings)
    recvonly = RecvonlyEncodedTransform(settings)

    sendonly.connect()
    recvonly.connect()

    # 固定 sleep ではなく、4 経路の callback 発火をイベントで待つ
    sendonly.wait_transforms()
    recvonly.wait_transforms()
    sendonly.assert_transform_results(test_thread_id)
    recvonly.assert_transform_results(test_thread_id)

    # codec / RTP stats は callback 確認後に取得する
    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    sendonly.disconnect()
    recvonly.disconnect()

    # 切断完了を待ち、その後も callback 例外が増えないこと（継続呼び出しの副作用）を確認する
    assert sendonly._disconnected.wait(10)
    assert recvonly._disconnected.wait(10)
    time.sleep(0.5)
    assert sendonly._audio_transform_error is None
    assert sendonly._video_transform_error is None
    assert recvonly._audio_transform_error is None
    assert recvonly._video_transform_error is None

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(
        s for s in sendonly_stats if s.get("type") == "codec" and s.get("mimeType") == "audio/opus"
    )
    assert sendonly_codec_stats["mimeType"] == "audio/opus"

    sendonly_codec_stats = next(
        s for s in sendonly_stats if s.get("type") == "codec" and s.get("mimeType") == "video/VP9"
    )
    assert sendonly_codec_stats["mimeType"] == "video/VP9"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(
        s for s in sendonly_stats if s.get("type") == "outbound-rtp" and s.get("kind") == "audio"
    )
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    outbound_rtp_stats = next(
        s for s in sendonly_stats if s.get("type") == "outbound-rtp" and s.get("kind") == "video"
    )
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    recvonly_codec_stats = next(
        s for s in recvonly_stats if s.get("type") == "codec" and s.get("mimeType") == "audio/opus"
    )
    assert recvonly_codec_stats["mimeType"] == "audio/opus"

    recvonly_codec_stats = next(
        s for s in recvonly_stats if s.get("type") == "codec" and s.get("mimeType") == "video/VP9"
    )
    assert recvonly_codec_stats["mimeType"] == "video/VP9"

    inbound_rtp_stats = next(
        s for s in recvonly_stats if s.get("type") == "inbound-rtp" and s.get("kind") == "audio"
    )
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0

    inbound_rtp_stats = next(
        s for s in recvonly_stats if s.get("type") == "inbound-rtp" and s.get("kind") == "video"
    )
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0
