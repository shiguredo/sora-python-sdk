"""
フレームの data() が返す ndarray が親フレームより長生きしても安全であることを検証する。

ndarray の owner が空だと、Python 側でフレームを解放したあとにバッファが
ダングリングポインタになり、アクセス時に SEGV しうる。
"""

from __future__ import annotations

import gc
import time
from threading import Event

from client import SoraClient, SoraRole

from sora_sdk import SoraAudioFrame, SoraAudioStreamSink, SoraMediaTrack


def test_video_frame_data_survives_after_frame_deleted(settings):
    """
    SoraVideoFrame.data() の戻り ndarray を保持したままフレームを破棄しても SEGV しないこと。

    前提:
    - sendonly / recvonly で映像を送受信し、SoraClient の video sink 経由でフレームを得る

    期待:
    - del frame と gc.collect() の後でも ndarray の shape / 要素アクセスが成功する
    """
    with (
        SoraClient(settings, SoraRole.SENDONLY, audio=False, video=True) as sendonly,
        SoraClient(settings, SoraRole.RECVONLY, audio=False, video=True) as recvonly,
    ):
        # __enter__ で接続済み。受信キューに映像フレームが来るまで待つ
        _ = sendonly
        frame = recvonly._q_out.get(timeout=30)
        data = frame.data()
        shape = tuple(int(value) for value in data.shape)

        # 親フレームだけを解放し、ndarray 側のバッファ参照が生き残るかを見る
        del frame
        gc.collect()

        assert data.shape == shape
        assert data.size > 0
        # 要素アクセスで解放済みメモリを踏まないことを確認する
        _ = int(data.flat[0])


def test_audio_frame_data_survives_after_frame_deleted(settings):
    """
    SoraAudioFrame.data() の戻り ndarray を保持したままフレームを破棄しても SEGV しないこと。

    前提:
    - SoraAudioStreamSink.on_frame で SoraAudioFrame を受け取る

    期待:
    - del frame と gc.collect() の後でも ndarray の shape / 要素アクセスが成功する
    """
    frames: list[SoraAudioFrame] = []
    frame_received = Event()
    audio_sinks: list[SoraAudioStreamSink] = []

    def on_frame(frame: SoraAudioFrame) -> None:
        # 最初の 1 フレームだけ保持する（以降のコールバックで上書きしない）
        if not frames:
            frames.append(frame)
            frame_received.set()

    def on_track(track: SoraMediaTrack) -> None:
        if track.kind != "audio":
            return
        audio_sink = SoraAudioStreamSink(track, output_frequency=16000, output_channels=1)
        audio_sink.on_frame = on_frame
        audio_sinks.append(audio_sink)

    sendonly = SoraClient(settings, SoraRole.SENDONLY, audio=True, video=False)
    recvonly = SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=False,
        audio_output_frequency=16000,
        audio_output_channels=1,
    )
    recvonly._connection.on_track = on_track

    try:
        sendonly.connect(fake_audio=True)
        recvonly.connect()

        assert frame_received.wait(30), "on_frame が発火しなかった"
        frame = frames[0]
        data = frame.data()
        shape = tuple(int(value) for value in data.shape)

        del frame
        frames.clear()
        gc.collect()

        assert data.shape == shape
        assert data.size > 0
        _ = int(data.flat[0])
    finally:
        sendonly.disconnect()
        recvonly.disconnect()
        # sink を明示的に解放し、接続切断後のコールバックを止める
        audio_sinks.clear()
        time.sleep(0.1)
