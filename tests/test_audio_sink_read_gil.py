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
    巨大なフレーム数を要求して read() を待機させている間、メインスレッドのハート
    ビートカウンタが伸びることを確認する。

    修正前: read() が待機中ずっと GIL を保持するため、メインスレッドが GIL 再取得
    待ちで飢餓し、カウンタがほぼ伸びない (fail)。
    修正後: 待機中に GIL が解放され、メインスレッドが進んでカウンタが伸びる (pass)。

    なお read() が即座に返ってしまうと「待機中の GIL 挙動」を検証できないため、
    測定区間を通して read() がブロックし続けていたこと (read スレッドが生存して
    いること) も併せて検証し、再現テストとしての妥当性を担保する。
    """
    read_timeout_s = 10.0
    measure_duration_s = 2.0
    heartbeat_interval_s = 0.01

    # 音声を送る sendonly と、それを受ける recvonly の 2 接続を張る。
    # recvonly 単独では送信相手がいないため audio track が来ず、sink を得られない。
    sendonly = SoraClient(settings, SoraRole.SENDONLY, audio=True, video=False)
    sendonly.connect(fake_audio=True)

    recvonly = SoraClient(settings, SoraRole.RECVONLY)
    recvonly.connect()

    read_thread = None
    # read スレッドの状態を共有する
    state: dict = {"started": False, "finished": False, "exc": None, "elapsed": None}
    try:
        # recvonly 側の on_track で生成される audio sink を取得する
        audio_sink = _wait_audio_sink(recvonly)

        # recvonly の出力サンプリングレートは既定 16000 Hz・1 ch。
        # 16000 サンプル/秒なので 16000 * 3600 は 1 時間分にあたり、
        # read_timeout_s 秒では到達せず read() は待機し続ける。
        huge_frames = 16000 * 3600

        def read_worker():
            state["started"] = True
            t0 = time.monotonic()
            try:
                # 戻り値は使わない。read_timeout_s 秒待機してタイムアウトで返る
                audio_sink.read(frames=huge_frames, timeout=read_timeout_s)
            except BaseException as e:
                state["exc"] = e
            finally:
                state["elapsed"] = time.monotonic() - t0
                state["finished"] = True

        read_thread = threading.Thread(target=read_worker, daemon=True)
        read_thread.start()

        # read_worker が read() の呼び出しに入るまで待つ
        while not state["started"]:
            time.sleep(0.001)

        # メインスレッドでハートビートを計測する。
        # read() が GIL を握っている間は time.sleep から復帰しても GIL 再取得待ちで
        # 進めず、カウンタが伸びない。
        counter = 0
        start = time.monotonic()
        while time.monotonic() - start < measure_duration_s:
            counter += 1
            time.sleep(heartbeat_interval_s)

        # 測定区間の終了時点で read スレッドがまだブロックしているか
        read_alive_at_end = read_thread.is_alive()

        # 失敗時に原因を特定できるよう診断情報を出す (pytest は失敗時のみ表示する)
        print(
            f"counter={counter}, read_alive_at_end={read_alive_at_end}, "
            f"read_finished={state['finished']}, read_elapsed={state['elapsed']}, "
            f"read_exc={state['exc']!r}"
        )

        # read() が測定区間を通してブロックし続けていたことを担保する。
        # 即座に返っていた場合は GIL 挙動を検証できておらず、再現テストとして無効。
        assert read_alive_at_end, (
            "read() が測定区間中にブロックし続けていない (即座に返った疑い)。"
            f"read_elapsed={state['elapsed']}, read_exc={state['exc']!r}"
        )

        # 理想は measure_duration_s / heartbeat_interval_s = 約 200 回。
        # GIL 保持の有無で「ほぼ 0」対「100 超」と明確に分かれるため、
        # 環境差で誤判定しにくい閾値として 50 回を採用する。
        assert counter > 50, (
            f"read() の待機中にメインスレッドが進めていない (counter={counter})。"
            "read() が待機中に GIL を解放していない疑いがある"
        )
    finally:
        # read スレッドは read_timeout_s で自然に返る。sink 破棄と read スレッドの
        # 競合を避けるため、disconnect より先に join する。
        if read_thread is not None:
            read_thread.join(timeout=read_timeout_s + 5.0)
        sendonly.disconnect()
        recvonly.disconnect()
