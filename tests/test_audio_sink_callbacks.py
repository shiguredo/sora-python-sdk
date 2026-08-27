from __future__ import annotations

import threading
from threading import Event

import numpy
from client import SoraClient, SoraRole
from conftest import Settings
from numpy.typing import NDArray

from sora_sdk import SoraAudioSink, SoraMediaTrack


def test_audio_sink_callbacks(settings: Settings) -> None:
    """音声 sink の廃止予定 callback が実接続で呼び出されることを確認する

    音声 callback は libwebrtc の音声処理スレッドから呼び出される。callback 内で
    Python のリスト更新と NumPy 配列の属性参照を行い、Python を呼び出す経路が
    GIL を保持して安全に実行できることを、プロセスのクラッシュなしで確認する。
    """
    format_received = Event()
    data_received = Event()
    format_values: list[tuple[int, int]] = []
    data_values: list[tuple[tuple[int, ...], str]] = []
    callback_thread_ids: set[int] = set()
    main_thread_id = threading.get_ident()
    audio_sinks: list[SoraAudioSink] = []

    def on_format(sample_rate: int, number_of_channels: int) -> None:
        # callback の引数を Python オブジェクトへ保存し、GIL 保持下の処理を確認する
        format_values.append((sample_rate, number_of_channels))
        callback_thread_ids.add(threading.get_ident())
        format_received.set()

    def on_data(data: NDArray[numpy.int16]) -> None:
        # ndarray の shape と dtype を callback の中で参照して記録する
        data_values.append((tuple(int(value) for value in data.shape), str(data.dtype)))
        callback_thread_ids.add(threading.get_ident())
        data_received.set()

    def on_track(track: SoraMediaTrack) -> None:
        if track.kind != "audio":
            return

        # sink の生成直後に callback を設定し、音声データ到着後のポーリングで
        # 最初のフォーマット通知を取り逃がさないようにする
        audio_sink = SoraAudioSink(track, output_frequency=16000, output_channels=1)
        audio_sink.on_format = on_format
        audio_sink.on_data = on_data
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

    sendonly_started = False
    recvonly_started = False
    try:
        # 受信側に音声 track を届けるため、送信側で実音声を生成する
        sendonly_started = True
        sendonly.connect(fake_audio=True)
        recvonly_started = True
        recvonly.connect()

        assert format_received.wait(30), "on_format callback が発火しなかった"
        assert data_received.wait(30), "on_data callback が発火しなかった"

        assert format_values, "on_format callback の引数が記録されなかった"
        assert format_values[0][0] == 16000
        assert format_values[0][1] == 1
        assert data_values, "on_data callback の引数が記録されなかった"
        assert len(data_values[0][0]) == 2
        assert data_values[0][0][0] > 0
        assert data_values[0][0][1] == 1
        assert data_values[0][1] == "int16"
        assert callback_thread_ids
        assert all(thread_id != main_thread_id for thread_id in callback_thread_ids)
    finally:
        # callback の待機と検証を終えてから切断し、音声スレッドの終了処理と競合させない
        try:
            if recvonly_started:
                recvonly.disconnect()
        finally:
            try:
                # 受信側の sink を明示的に破棄してから送信側を切断する
                audio_sinks.clear()
            finally:
                if sendonly_started:
                    sendonly.disconnect()
