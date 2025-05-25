import json
import threading
import time
from threading import Event
from typing import Any, Optional

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

        self._fake_audio_thread: Optional[threading.Thread] = None
        self._fake_video_thread: Optional[threading.Thread] = None

        self._audio_source: Optional[SoraAudioSource] = None
        self._audio_source = self._sora.create_audio_source(
            self._audio_channels, self._audio_sample_rate
        )

        self._video_source: Optional[SoraVideoSource] = None
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

        self._is_called_on_audio_transform = False
        self._is_called_on_video_transform = False

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

    @property
    def is_called_on_audio_transform(self):
        return self._is_called_on_audio_transform

    @property
    def is_called_on_video_transform(self):
        return self._is_called_on_video_transform

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
        # この実装が Encoded Transform を利用する上での基本形となる

        # frame からエンコードされたフレームデータを取得する
        # 戻り値は numpy.ndarray になっている
        new_data = frame.get_data()

        # "sora" という文字列を new_data の後ろに追加
        new_data = numpy.append(new_data, numpy.frombuffer(b"sora", dtype=numpy.uint8))

        self._is_called_on_audio_transform = True

        # ここで new_data の末尾にデータをつける new_data を暗号化するなど任意の処理を実装する

        # 加工したフレームデータで frame の フレームデータを入れ替える
        frame.set_data(new_data)
        self._audio_transformer.enqueue(frame)

    def _on_video_transform(self, frame: SoraTransformableVideoFrame):
        # この実装が Encoded Transform を利用する上での基本形となる

        # frame からエンコードされたフレームデータを取得する
        # 戻り値は numpy.ndarray になっている
        new_data = frame.get_data()

        # "sora" という文字列を new_data の後ろに追加
        new_data = numpy.append(new_data, numpy.frombuffer(b"sora", dtype=numpy.uint8))

        self._is_called_on_video_transform = True

        # ここで new_data の末尾にデータをつける new_data を暗号化するなど任意の処理を実装する

        # 加工したフレームデータで frame の フレームデータを入れ替える
        frame.set_data(new_data)
        self._video_transformer.enqueue(frame)


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

        self._is_called_on_audio_transform = False
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
    def is_called_on_audio_transform(self):
        return self._is_called_on_audio_transform

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
        # この実装が Encoded Transform を利用する上での基本形となる

        # frame からエンコードされたフレームデータを取得する
        # 戻り値は ArrayLike になっている
        new_data = frame.get_data()

        # ここで new_data の末尾にデータをつける new_data を暗号化するなど任意の処理を実装する

        # ArrayLike を numpy.uint8 のバイト列に変換する
        new_data = numpy.asarray(new_data, dtype=numpy.uint8)

        # 後ろ4バイトを取得する
        removed_data = new_data[-4:]

        assert b"sora" == removed_data.tobytes()

        # 後ろ4バイトを取り除く
        new_data = new_data[:-4]

        self._is_called_on_audio_transform = True

        # 加工したフレームデータで frame の フレームデータを入れ替える
        frame.set_data(new_data)
        self._audio_transformer.enqueue(frame)

    def _on_video_transform(self, frame: SoraTransformableVideoFrame):
        # この実装が Encoded Transform を利用する上での基本形となる
        # frame からエンコードされたフレームデータを取得する
        # 戻り値は ArrayLike になっている
        new_data = frame.get_data()

        # ここで new_data の末尾にデータをつける new_data を暗号化するなど任意の処理を実装する

        # ArrayLike を numpy.uint8 のバイト列に変換する
        new_data = numpy.asarray(new_data, dtype=numpy.uint8)

        # 後ろ4バイトを取得する
        removed_data = new_data[-4:]

        assert b"sora" == removed_data.tobytes()

        # 後ろ4バイトを取り除く
        new_data = new_data[:-4]

        self._is_called_on_video_transform = True

        # 加工したフレームデータで frame の フレームデータを入れ替える
        frame.set_data(new_data)
        self._video_transformer.enqueue(frame)


def test_encoded_transform(settings):
    sendonly = SendonlyEncodedTransform(settings)
    sendonly.connect()

    recvonly = RecvonlyEncodedTransform(settings)
    recvonly.connect()

    time.sleep(5)

    sendonly_stats = sendonly.get_stats()
    recvonly_stats = recvonly.get_stats()

    sendonly.disconnect()
    recvonly.disconnect()

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
    # audio には encoderImplementation が無い
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(
        s for s in sendonly_stats if s.get("type") == "outbound-rtp" and s.get("kind") == "video"
    )
    # video には encoderImplementation が無い
    assert outbound_rtp_stats["bytesSent"] > 0
    assert outbound_rtp_stats["packetsSent"] > 0

    # codec が無かったら StopIteration 例外が上がる
    recvonly_codec_stats = next(
        s for s in recvonly_stats if s.get("type") == "codec" and s.get("mimeType") == "audio/opus"
    )
    assert recvonly_codec_stats["mimeType"] == "audio/opus"

    recvonly_codec_stats = next(
        s for s in recvonly_stats if s.get("type") == "codec" and s.get("mimeType") == "video/VP9"
    )
    assert recvonly_codec_stats["mimeType"] == "video/VP9"

    # inbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(
        s for s in recvonly_stats if s.get("type") == "inbound-rtp" and s.get("kind") == "audio"
    )
    # audio には encoderImplementation が無い
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0

    # inbound-rtp が無かったら StopIteration 例外が上がる
    inbound_rtp_stats = next(
        s for s in recvonly_stats if s.get("type") == "inbound-rtp" and s.get("kind") == "video"
    )
    # video には encoderImplementation が無い
    assert inbound_rtp_stats["bytesReceived"] > 0
    assert inbound_rtp_stats["packetsReceived"] > 0

    # on_transform が呼ばれていることを確認
    assert sendonly.is_called_on_audio_transform is True
    assert sendonly.is_called_on_video_transform is True

    assert recvonly.is_called_on_audio_transform is True
    assert recvonly.is_called_on_video_transform is True
