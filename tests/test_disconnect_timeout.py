"""
disconnect() が有限時間で完了することを検証する。

OnDisconnect が来ない異常時に永久ブロックしないことが本修正の主眼だが、
モック禁止のため異常経路はコード上の有限 wait で担保し、ここでは正常系で
disconnect() が妥当な時間内に戻ることを確認する。
"""

from __future__ import annotations

import time

from client import SoraClient, SoraRole


def test_disconnect_returns_within_timeout(settings):
    """
    正常系の disconnect() が短時間で完了すること。

    前提:
    - Sora に接続したあと disconnect() する

    期待:
    - disconnect() が数秒以内に戻る（永久ブロックしない）
    """
    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=False,
    ) as client:
        time.sleep(1)

        started = time.monotonic()
        client.disconnect()
        elapsed = time.monotonic() - started

        # OnDisconnect 待ちの上限は 10 秒。正常系はそれより十分短いこと。
        assert elapsed < 5.0, f"disconnect() が遅すぎる: {elapsed:.2f}s"
