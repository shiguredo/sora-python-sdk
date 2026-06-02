import threading
import time

from client import SoraClient, SoraRole


def _wait_audio_sink(client: SoraClient, timeout_s: float = 30.0):
    """on_track が発火して audio sink が生成されるまでポーリングして待つ"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        # _on_track の audio 分岐で _audio_sink に SoraAudioSink が格納される
        audio_sink = client._audio_sink
        if audio_sink is not None:
            return audio_sink
        time.sleep(0.1)
    raise AssertionError("audio sink が生成されなかった")


def test_audio_sink_read_does_not_block_other_threads(settings):
    """SoraAudioSink.read() の待機中に他スレッドの Python 実行が妨げられないことを検証する

    read() の待機中に GIL を保持し続けると、別スレッドで read() がブロックしている
    間、同一プロセスの他の Python スレッドが進めなくなる。本テストは、別スレッドで
    巨大なフレーム数を要求して read() を待機させ、その間メインスレッドが連続して
    進めているか (連続するハートビート間の最大停止時間) を計測する。

    修正前: read() が待機中ずっと GIL を保持するため、メインスレッドが read の待機
    時間ぶん停止し、最大停止時間が read_timeout_s 付近まで伸びる (fail)。
    修正後: 待機中に GIL が解放されるため、最大停止時間は heartbeat_interval_s 程度
    に収まる (pass)。

    なお read() が即座に返ってしまうと GIL 挙動を検証できないため、read() が想定
    どおり read_timeout_s 秒ブロックしたことも併せて確認し、再現テストとしての妥当
    性を担保する。
    """
    read_timeout_s = 3.0
    # read のブロックを十分に含む観測時間
    observe_duration_s = read_timeout_s + 2.0
    heartbeat_interval_s = 0.01
    # 許容する最大停止時間。GIL 保持の有無で「read_timeout_s 付近」対
    # 「heartbeat_interval_s 程度」と大きく分かれるため、その中間に閾値を置く。
    max_allowed_stall_s = 1.0

    # 音声を送る sendonly と、それを受ける recvonly の 2 接続を張る。
    # recvonly 単独では送信相手がいないため audio track が来ず、sink を得られない。
    sendonly = SoraClient(settings, SoraRole.SENDONLY, audio=True, video=False)
    sendonly.connect(fake_audio=True)

    recvonly = SoraClient(settings, SoraRole.RECVONLY)
    recvonly.connect()

    read_thread = None
    # read スレッドの結果を共有する
    state: dict = {"elapsed": None, "exc": None}
    try:
        # recvonly 側の on_track で生成される audio sink を取得する
        audio_sink = _wait_audio_sink(recvonly)

        # recvonly の出力サンプリングレートは既定 16000 Hz・1 ch。
        # 16000 サンプル/秒なので 16000 * 3600 は 1 時間分にあたり、
        # read_timeout_s 秒では到達せず read() は待機し続ける。
        huge_frames = 16000 * 3600

        def read_worker():
            t0 = time.monotonic()
            try:
                # 戻り値は使わない。read_timeout_s 秒待機してタイムアウトで返る
                audio_sink.read(frames=huge_frames, timeout=read_timeout_s)
            except BaseException as e:
                state["exc"] = e
            finally:
                state["elapsed"] = time.monotonic() - t0

        read_thread = threading.Thread(target=read_worker, daemon=True)
        read_thread.start()

        # observe_duration_s の間、メインスレッドのハートビートのタイムスタンプを
        # 記録する。read() が GIL を握っている間はメインスレッドが停止し、連続する
        # タイムスタンプの間隔 (stall) が read の待機時間ぶん大きくなる。
        timestamps = []
        start = time.monotonic()
        while time.monotonic() - start < observe_duration_s:
            timestamps.append(time.monotonic())
            time.sleep(heartbeat_interval_s)

        max_stall_s = max((t1 - t0 for t0, t1 in zip(timestamps, timestamps[1:])), default=0.0)

        # read スレッドの完了を待ち、ブロック時間を確定させる
        read_thread.join(timeout=read_timeout_s + 5.0)

        # 失敗時に原因を特定できるよう診断情報を出す (pytest は失敗時のみ表示する)
        print(
            f"max_stall_s={max_stall_s:.3f}, samples={len(timestamps)}, "
            f"read_elapsed={state['elapsed']}, read_exc={state['exc']!r}"
        )

        # read() が想定どおり read_timeout_s 秒ブロックしたことを担保する。
        # 即座に返っていれば GIL 挙動を検証できておらず、再現テストとして無効。
        assert state["elapsed"] is not None and state["elapsed"] >= read_timeout_s * 0.9, (
            f"read() が想定どおり待機しなかった (read_elapsed={state['elapsed']}, "
            f"read_exc={state['exc']!r})。再現テストとして無効"
        )

        # read() の待機中にメインスレッドが長時間停止していないこと。
        assert max_stall_s < max_allowed_stall_s, (
            f"read() の待機中にメインスレッドが {max_stall_s:.3f} 秒停止した。"
            "read() が待機中に GIL を解放していない"
        )
    finally:
        # read スレッドは read_timeout_s で自然に返る。sink 破棄と read スレッドの
        # 競合を避けるため、disconnect より先に join する。
        if read_thread is not None:
            read_thread.join(timeout=read_timeout_s + 5.0)
        sendonly.disconnect()
        recvonly.disconnect()
