"""
disconnect() 後に send_data_channel() / get_stats() を呼んだときの挙動を検証する。

Disconnect() は内部で conn_ を nullptr にする。ガードが無いと C++ 側で
nullptr dereference して SEGV するため、Connect() と同様に RuntimeError へ
変換されることを確認する。
"""

from __future__ import annotations

import time

import pytest
from client import SoraClient, SoraRole


def test_send_data_channel_after_disconnect_raises_runtime_error(settings):
    """
    disconnect() 後の send_data_channel() が SEGV ではなく RuntimeError になること。

    前提:
    - Sora に接続してから disconnect() する
    - disconnect() 後の SoraConnection インスタンスをそのまま使う

    期待:
    - RuntimeError が発生する（メッセージに Already disconnected を含む）
    - プロセスが SEGV で落ちない
    """
    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=False,
    ) as client:
        time.sleep(1)

        # SoraClient.disconnect() 経由で conn_ を nullptr にする
        connection = client._connection
        client.disconnect()

        with pytest.raises(RuntimeError, match="Already disconnected"):
            connection.send_data_channel("#test", b"hello")


def test_get_stats_after_disconnect_raises_runtime_error(settings):
    """
    disconnect() 後の get_stats() が SEGV ではなく RuntimeError になること。

    前提:
    - Sora に接続してから disconnect() する
    - disconnect() 後の SoraConnection インスタンスをそのまま使う

    期待:
    - RuntimeError が発生する（メッセージに Already disconnected を含む）
    - プロセスが SEGV で落ちない
    """
    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=False,
    ) as client:
        time.sleep(1)

        connection = client._connection
        client.disconnect()

        with pytest.raises(RuntimeError, match="Already disconnected"):
            connection.get_stats()
