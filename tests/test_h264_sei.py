import json
import sys
import threading
import time
import uuid
from threading import Event
from typing import Any, Optional

import numpy

from sora_sdk import (
    Sora,
    SoraMediaTrack,
    SoraTransformableVideoFrame,
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
    SoraVideoFrameTransformer,
    SoraVideoSource,
)


class SendonlyEncodedTransform:
    def __init__(
        self,
        signaling_urls: list[str],
        channel_id: str,
        metadata: dict[str, Any],
        openh264_path: str,
    ):
        self._signaling_urls: list[str] = signaling_urls
        self._channel_id: str = channel_id

        self._connection_id: str

        # 接続した
        self._connected: Event = Event()
        # 終了
        self._disconnected = Event()

        self._video_width: int = 960
        self._video_height: int = 540

        self._sora = Sora(
            openh264=openh264_path,
            video_codec_preference=SoraVideoCodecPreference(
                codecs=[
                    SoraVideoCodecPreference.Codec(
                        type=SoraVideoCodecType.H264,
                        encoder=SoraVideoCodecImplementation.CISCO_OPENH264,
                    )
                ]
            ),
        )

        self._fake_video_thread: Optional[threading.Thread] = None

        self._video_source: Optional[SoraVideoSource] = None
        self._video_source = self._sora.create_video_source()

        # Video 向けの Encoded Transformer
        self._video_transformer = SoraVideoFrameTransformer()
        # Video のエンコードフレームを受け取るコールバック関数を on_transform に設定
        self._video_transformer.on_transform = self._on_video_transform

        self._connection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="sendonly",
            channel_id=channel_id,
            metadata=metadata,
            audio=False,
            video=True,
            video_codec_type="H264",
            video_source=self._video_source,
            video_frame_transformer=self._video_transformer,
        )

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect

        self._is_called_on_video_transform = False

    def connect(self):
        self._connection.connect()

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

    @property
    def is_called_on_video_transform(self):
        return self._is_called_on_video_transform

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

        if self._fake_video_thread is not None:
            self._fake_video_thread.join(timeout=10)

    def _on_video_transform(self, frame: SoraTransformableVideoFrame):
        # この実装が Encoded Transform を利用する上での基本形となる

        # frame からエンコードされたフレームデータを取得する
        # 戻り値は numpy.ndarray になっている
        new_data = frame.get_data()

        # SEI パケットのバイナリデータ
        # 06 ‐ NAL ヘッダ (F=0, NRI=0, type=6 → SEI)
        # 05 ‐ payload_type = 5 (user_data_unregistered)
        # 11 ‐ payload_size = 0x11 = 17 バイト
        # CF 0A 75 11 2E B7 43 3A 9D 2D 8D A1 55 9D A5 24
        #    ‐ 16 バイトの UUID
        # 81 ‐ ユーザーデータ 1 バイト
        # 80 ‐ rbsp_trailing_bits (stop bit + padding)
        data = bytes.fromhex("060511cf0a75112eb7433a9d2d8da1559da5248180")

        new_data = numpy.concatenate([numpy.frombuffer(data, dtype=numpy.uint8), new_data])

        self._is_called_on_video_transform = True

        # ここで new_data の末尾にデータをつける new_data を暗号化するなど任意の処理を実装する

        # 加工したフレームデータで frame の フレームデータを入れ替える
        frame.set_data(new_data)
        self._video_transformer.enqueue(frame)


class RecvonlyEncodedTransform:
    def __init__(
        self,
        signaling_urls: list[str],
        channel_id: str,
        metadata: dict[str, Any],
        openh264_path: str,
    ):
        self._signaling_urls: list[str] = signaling_urls
        self._channel_id: str = channel_id

        self._connection_id: str

        # 接続した
        self._connected: Event = Event()
        # 終了
        self._disconnected = Event()

        self._sora = Sora(
            openh264=openh264_path,
            video_codec_preference=SoraVideoCodecPreference(
                codecs=[
                    SoraVideoCodecPreference.Codec(
                        type=SoraVideoCodecType.H264,
                        decoder=SoraVideoCodecImplementation.CISCO_OPENH264,
                    )
                ]
            ),
        )

        self._connection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="recvonly",
            channel_id=channel_id,
            metadata=metadata,
            audio=False,
            video=True,
            video_codec_type="H264",
        )

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect

        self._connection.on_track = self._on_track

        self._is_called_on_video_transform = False

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

    @property
    def is_called_on_video_transform(self):
        return self._is_called_on_video_transform

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
        if track.kind == "video":
            # Video 向けの Encoded Transformer
            self._video_transformer = SoraVideoFrameTransformer()
            # Video のエンコードフレームを受け取るコールバック関数を on_transform に設定
            self._video_transformer.on_transform = self._on_video_transform
            # Encoded Transformer を SoraMediaTrack に設定する
            track.set_frame_transformer(self._video_transformer)

    def _on_video_transform(self, frame: SoraTransformableVideoFrame):
        # frame から復号され結合されたフレームデータを取得する
        # 戻り値は ArrayLike になっている
        new_data = frame.get_data()

        # ArrayLike を numpy.uint8 のバイト列に変換する
        new_data = numpy.asarray(new_data, dtype=numpy.uint8)

        self._is_called_on_video_transform = True

        # 加工したフレームデータで frame の フレームデータを入れ替える
        frame.set_data(new_data)
        self._video_transformer.enqueue(frame)


def test_h264_sei(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")
    openh264_path = setup.get("openh264_path")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = SendonlyEncodedTransform(
        signaling_urls,
        channel_id,
        metadata,
        openh264_path,
    )
    sendonly.connect()

    recvonly = RecvonlyEncodedTransform(
        signaling_urls,
        channel_id,
        metadata,
        openh264_path,
    )
    recvonly.connect()

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    sendonly.disconnect()
    recvonly.disconnect()

    # codec が無かったら StopIteration 例外が上がる
    sendonly_codec_stats = next(
        s for s in sendonly_stats if s.get("type") == "codec" and s.get("mimeType") == "video/H264"
    )
    assert sendonly_codec_stats["mimeType"] == "video/H264"

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(
        s for s in sendonly_stats if s.get("type") == "outbound-rtp" and s.get("kind") == "video"
    )
    # video には encoderImplementation が無い
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(
        s for s in recvonly_stats if s.get("type") == "codec" and s.get("mimeType") == "video/H264"
    )
    assert recvonly_codec_stats["mimeType"] == "video/H264"

    # inbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(
        s for s in recvonly_stats if s.get("type") == "inbound-rtp" and s.get("kind") == "video"
    )
    # video には encoderImplementation が無い
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0

    # on_transform が呼ばれていることを確認
    assert sendonly.is_called_on_video_transform is True

    assert recvonly.is_called_on_video_transform is True
