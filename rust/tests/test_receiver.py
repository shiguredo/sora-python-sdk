"""新 API での受信を確認する。"""

from __future__ import annotations

import json
import pickle
import threading
import time

import pytest
import sora_rust_sdk
from test_loopback import prepare_channel


def test_connect_disconnect_and_stats() -> None:
    """
    意図・前提・期待値をここに書く
    新 API の接続・切断・統計取得を確認する。
    前提は既存 E2E と同じ環境変数で接続先が指定されていること。
    例外なく接続・統計・切断できることを期待する。
    """
    signaling_urls, metadata, channel_id = prepare_channel()

    # 接続先の有無を確認する
    if not signaling_urls:
        pytest.fail("接続先が未設定のため確認できない")

    # 接続する
    print(f"接続開始: channel_id={channel_id}")
    connection = sora_rust_sdk.Sora().create_connection(
        signaling_urls, "recvonly", channel_id, metadata=metadata
    )
    connection.connect()
    try:
        # 統計情報を取得する
        stats = connection.get_stats()
        assert isinstance(stats, str)
        assert isinstance(json.loads(stats), list)
        print("統計取得を確認した")
    finally:
        # 切断する
        connection.disconnect()
    print("接続と切断を確認した")


def test_receive_audio_and_video_with_new_api() -> None:
    """
    意図・前提・期待値をここに書く
    新 API の Sink で音声・映像フレームを受け取れることを確認する。
    前提は既存 E2E と同じ環境変数で接続先が指定され、実マイクが使えること。
    送信側はプロトタイプのループバック送信を使い、同一チャネルで送受信する。
    音声 PCM と映像フレームを受信できることを期待する。
    """
    signaling_urls, metadata, channel_id = prepare_channel()

    # 接続先の有無を確認する
    if not signaling_urls:
        pytest.fail("接続先が未設定のため確認できない")

    # 送信側を別スレッドで動かす (黒映像と実マイク音声)
    video_result: dict = {}
    audio_result: dict = {}

    def publish_video() -> None:
        video_result.update(
            sora_rust_sdk.loopback_video_frames(
                signaling_urls, channel_id, metadata=metadata, duration_secs=30
            )
        )

    def publish_audio() -> None:
        audio_result.update(
            sora_rust_sdk.loopback_audio_frames(
                signaling_urls, channel_id, metadata=metadata, duration_secs=30, microphone=True
            )
        )

    video_thread = threading.Thread(target=publish_video)
    audio_thread = threading.Thread(target=publish_audio)
    video_thread.start()
    audio_thread.start()
    try:
        # 受信側を接続する。到着ごとに Sink を付ける (再 offer で作り直されるため)
        tracks: list = []
        audio_sinks: list = []
        video_frames: list = []
        notified = threading.Event()

        def on_track(track: object) -> None:
            tracks.append(track)
            if track.kind == "audio":
                audio_sinks.append(sora_rust_sdk.SoraAudioSink(track))
            elif track.kind == "video":

                def on_frame(frame: object) -> None:
                    video_frames.append(frame)

                sink = sora_rust_sdk.SoraVideoSink(track)
                sink.on_frame = on_frame
                audio_sinks.append(sink)
            notified.set()

        print(f"受信開始: channel_id={channel_id}")
        connection = sora_rust_sdk.Sora().create_connection(
            signaling_urls, "recvonly", channel_id, metadata=metadata
        )
        connection.on_track = on_track
        connection.connect()
        try:
            # 音声と映像の両トラック到来を待つ
            kinds: list[str] = []
            deadline = time.time() + 25
            while time.time() < deadline:
                kinds = sorted(str(track.kind) for track in tracks)
                if "audio" in kinds and "video" in kinds:
                    break
                time.sleep(0.5)
            print(f"受信トラック: {kinds}")
            assert "audio" in kinds
            assert "video" in kinds
            assert isinstance(tracks[0].id, str)
            assert tracks[0].id != ""
            assert isinstance(tracks[0].enabled, bool)

            # いずれかの音声 Sink で PCM を読む
            received: tuple = (False, None)
            deadline = time.time() + 15
            while time.time() < deadline:
                for sink in list(audio_sinks):
                    if not isinstance(sink, sora_rust_sdk.SoraAudioSink):
                        continue
                    received = sink.read(frames=480, timeout=1)
                    if received[0]:
                        break
                if received[0]:
                    break
            assert received[0]
            data = received[1]
            assert data.shape[1] >= 1
            assert data.shape[0] >= 480
            print(f"音声受信: shape={data.shape}")

            # 映像フレーム受信を待つ
            deadline = time.time() + 15
            while time.time() < deadline and not video_frames:
                time.sleep(0.5)
            assert video_frames, "映像フレームを受信できなかった"
            frame = video_frames[0]
            data = frame.data()
            assert data.shape == (data.shape[0], data.shape[1], 3)
            print(f"映像受信: shape={data.shape}")
        finally:
            connection.disconnect()
    finally:
        video_thread.join()
        audio_thread.join()

    # 送信側も流れたことを確認する
    assert video_result["received_frames"] > 0
    assert audio_result["frames"] > 0


def test_audio_stream_sink_receives_frames() -> None:
    """
    意図・前提・期待値をここに書く
    SoraAudioStreamSink の on_frame でフレームを受け取れることを確認する。
    前提は既存 E2E と同じ環境変数で接続先が指定され、実マイクが使えること。
    フレーム受信と pickle 往復ができることを期待する。
    """
    signaling_urls, metadata, channel_id = prepare_channel()

    # 接続先の有無を確認する
    if not signaling_urls:
        pytest.fail("接続先が未設定のため確認できない")

    # 送信側を別スレッドで動かす (実マイク音声)
    audio_result: dict = {}

    def publish_audio() -> None:
        audio_result.update(
            sora_rust_sdk.loopback_audio_frames(
                signaling_urls, channel_id, metadata=metadata, duration_secs=20, microphone=True
            )
        )

    audio_thread = threading.Thread(target=publish_audio)
    audio_thread.start()
    try:
        # 受信側を接続する
        tracks: list = []
        notified = threading.Event()

        def on_track(track: object) -> None:
            tracks.append(track)
            notified.set()

        connection = sora_rust_sdk.Sora().create_connection(
            signaling_urls, "recvonly", channel_id, metadata=metadata
        )
        connection.on_track = on_track
        connection.connect()
        try:
            # 音声トラック到来を待つ
            audio_tracks: list = []
            deadline = time.time() + 25
            while time.time() < deadline:
                audio_tracks = [track for track in tracks if track.kind == "audio"]
                if audio_tracks:
                    break
                time.sleep(0.5)
            assert audio_tracks, "音声トラックを受信できなかった"

            # ストリーム Sink でフレームを受ける
            received: list = []
            arrived = threading.Event()

            def on_frame(frame: object) -> None:
                received.append(frame)
                arrived.set()

            stream_sink = sora_rust_sdk.SoraAudioStreamSink(audio_tracks[0])
            stream_sink.on_frame = on_frame
            assert arrived.wait(timeout=15), "音声フレームを受信できなかった"
            frame = received[0]
            assert frame.samples_per_channel > 0
            assert frame.num_channels > 0
            assert frame.sample_rate_hz > 0
            data = frame.data()
            assert data.shape == (frame.samples_per_channel, frame.num_channels)
            print(f"音声フレーム受信: shape={data.shape}")

            # pickle 往復を確認する
            restored = pickle.loads(pickle.dumps(frame))
            assert restored.samples_per_channel == frame.samples_per_channel
            assert restored.num_channels == frame.num_channels
            assert restored.sample_rate_hz == frame.sample_rate_hz
            assert (restored.data() == data).all()
        finally:
            connection.disconnect()
    finally:
        audio_thread.join()

    assert audio_result["frames"] > 0
