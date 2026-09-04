"""新 API での送信を確認する。"""

from __future__ import annotations

import threading
import time

import numpy
import pytest
import sora_rust_sdk
from test_loopback import prepare_channel


def test_create_audio_source_rejects_invalid_params() -> None:
    """
    新 API の音声送信元が不正な形式を拒否することを確認する。
    前提は特にない。
    channels と sample_rate の下限違反で ValueError になることを期待する。
    """
    sora = sora_rust_sdk.Sora()

    # チャネル数と標本周波数の下限を確認する
    with pytest.raises(ValueError, match="channels"):
        sora.create_audio_source(0, 16000)
    with pytest.raises(ValueError, match="sample_rate"):
        sora.create_audio_source(1, 50)


def test_audio_source_rejects_mismatched_array() -> None:
    """
    新 API の音声投入が形式違いの配列を拒否することを確認する。
    前提は特にない。
    宣言と異なるチャネル数の配列で ValueError になることを期待する。
    """
    sora = sora_rust_sdk.Sora()
    source = sora.create_audio_source(1, 16000)

    # 属性参照を確認する
    assert source.kind == "audio"
    assert isinstance(source.id, str)
    assert source.id != ""
    assert isinstance(source.enabled, bool)

    # チャネル数違いを拒否することを確認する
    with pytest.raises(ValueError, match="channels"):
        source.on_data(numpy.zeros((320, 2), dtype=numpy.int16))


def test_video_source_rejects_invalid_array() -> None:
    """
    新 API の映像投入が形式違いの配列を拒否することを確認する。
    前提は特にない。
    (height, width, 3) でない配列で例外になることを期待する。
    """
    sora = sora_rust_sdk.Sora()
    source = sora.create_video_source()

    # 属性参照を確認する
    assert source.kind == "video"
    assert isinstance(source.id, str)
    assert source.id != ""
    assert isinstance(source.enabled, bool)

    # チャネル数違いを拒否することを確認する
    with pytest.raises(ValueError, match="shape"):
        source.on_captured(numpy.zeros((240, 320, 4), dtype=numpy.uint8))


def test_audio_source_accepts_raw_address() -> None:
    """
    新 API の音声投入が番地指定を受け付けることを確認する。
    前提は特にない。
    番地と標本数で投入でき、不正な番地を拒否することを期待する。
    """
    sora = sora_rust_sdk.Sora()
    source = sora.create_audio_source(1, 16000)

    # 番地指定で投入できることを確認する
    array = numpy.zeros((320, 1), dtype=numpy.int16)
    source.on_data(array.ctypes.data, 320)
    source.on_data(array.ctypes.data, 320, 1.5)

    # 不正な番地と不足引数を拒否することを確認する
    with pytest.raises(ValueError, match="address"):
        source.on_data(0, 320)
    with pytest.raises(ValueError, match="samples_per_channel"):
        source.on_data(array.ctypes.data)


def test_create_connection_rejects_invalid_settings() -> None:
    """
    新 API の接続設定が不正値を拒否することを確認する。
    前提は特にない。
    未対応符号化方式や型違い項目で ValueError になることを期待する。
    """
    sora = sora_rust_sdk.Sora()
    urls = ["wss://127.0.0.1:1/signaling"]

    # 未対応の符号化方式を確認する
    with pytest.raises(ValueError, match="audio_codec_type"):
        sora.create_connection(urls, "sendonly", "x", audio_codec_type="G711")
    with pytest.raises(ValueError, match="video_codec_type"):
        sora.create_connection(urls, "sendonly", "x", video_codec_type="H266")

    # 型違いの項目を確認する
    with pytest.raises(ValueError, match="profile_id"):
        sora.create_connection(
            urls, "sendonly", "x", video_codec_type="VP9", video_vp9_params={"profile_id": "x"}
        )
    with pytest.raises(ValueError, match="label"):
        sora.create_connection(urls, "sendonly", "x", data_channels=[{"direction": "sendrecv"}])

    # 証明書の非 UTF-8 を確認する
    with pytest.raises(ValueError, match="client_cert"):
        sora.create_connection(urls, "sendonly", "x", client_cert=b"\xff\xfe")


def test_send_audio_and_video_with_new_api() -> None:
    """
    新 API の送信元で音声・映像フレームを送れることを確認する。
    前提は既存 E2E と同じ環境変数で接続先が指定されていること。
    送信側は新 API の送信元を使い、受信側は新 API の Sink で受ける。
    音声 PCM と映像フレームを受信できることを期待する。
    """
    signaling_urls, metadata, channel_id = prepare_channel()

    # 接続先の有無を確認する
    if not signaling_urls:
        pytest.fail("接続先が未設定のため確認できない")

    # 受信側を先に接続する。到着ごとに Sink を付ける
    tracks: list = []
    audio_sinks: list = []
    video_frames: list = []

    def on_track(track: object) -> None:
        tracks.append(track)
        if track.kind == "audio":  # type: ignore[attr-defined]
            audio_sinks.append(sora_rust_sdk.SoraAudioSink(track))  # type: ignore[arg-type]
        elif track.kind == "video":  # type: ignore[attr-defined]

            def on_frame(frame: object) -> None:
                video_frames.append(frame)

            sink = sora_rust_sdk.SoraVideoSink(track)  # type: ignore[arg-type]
            sink.on_frame = on_frame
            audio_sinks.append(sink)

    print(f"受信開始: channel_id={channel_id}")
    receiver = sora_rust_sdk.Sora().create_connection(
        signaling_urls, "recvonly", channel_id, metadata=metadata
    )
    receiver.on_track = on_track
    receiver.connect()
    try:
        # 送信側を接続する
        sender_sora = sora_rust_sdk.Sora()
        audio_source = sender_sora.create_audio_source(1, 16000)
        video_source = sender_sora.create_video_source()
        sender = sender_sora.create_connection(
            signaling_urls,
            "sendonly",
            channel_id,
            metadata=metadata,
            audio_source=audio_source,
            video_source=video_source,
        )
        sender.connect()
        print("送信開始", flush=True)
        try:
            stop = threading.Event()

            # 無音 PCM を投入し続ける
            def push_audio() -> None:
                while not stop.is_set():
                    time.sleep(0.02)
                    audio_source.on_data(numpy.zeros((320, 1), dtype=numpy.int16))

            # 黒フレームを投入し続ける
            def push_video() -> None:
                while not stop.is_set():
                    time.sleep(1.0 / 30)
                    video_source.on_captured(numpy.zeros((240, 320, 3), dtype=numpy.uint8))

            audio_thread = threading.Thread(target=push_audio, daemon=True)
            video_thread = threading.Thread(target=push_video, daemon=True)
            audio_thread.start()
            video_thread.start()
            try:
                # 音声と映像の両トラック到来を待つ
                kinds: list = []
                deadline = time.time() + 25
                while time.time() < deadline:
                    kinds = sorted(str(track.kind) for track in tracks)  # type: ignore[attr-defined]
                    if "audio" in kinds and "video" in kinds:
                        break
                    time.sleep(0.5)
                print(f"受信トラック: {kinds}")
                assert "audio" in kinds
                assert "video" in kinds

                # いずれかの音声 Sink で PCM を読む
                received: tuple = (False, None)
                deadline = time.time() + 15
                while time.time() < deadline:
                    for sink in list(audio_sinks):
                        if not isinstance(sink, sora_rust_sdk.SoraAudioSink):
                            continue
                        received = sink.read(frames=160, timeout=1)
                        if received[0]:
                            break
                    if received[0]:
                        break
                assert received[0]
                print(f"音声受信: shape={received[1].shape}")

                # 映像フレーム受信を待つ
                deadline = time.time() + 15
                while time.time() < deadline and not video_frames:
                    time.sleep(0.5)
                assert video_frames, "映像フレームを受信できなかった"
                data = video_frames[0].data()
                assert data.shape == (data.shape[0], data.shape[1], 3)
                print(f"映像受信: shape={data.shape}")
            finally:
                stop.set()
                audio_thread.join()
                video_thread.join()
        finally:
            sender.disconnect()
    finally:
        receiver.disconnect()
    print("送受信を確認した")
