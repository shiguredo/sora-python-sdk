"""
rtc_log() が PyFrame_GetCode の新参照をリークしないことを検証する。

PyFrame_GetCode は新参照を返す。Py_DECREF しないと呼び出しのたびに
呼び出し元の PyCodeObject の参照カウントが 1 ずつ増える。
"""

from __future__ import annotations

import sys

from sora_sdk import SoraLoggingSeverity, rtc_log


def test_rtc_log_does_not_leak_code_object_references():
    """
    rtc_log を多数回呼んでも、呼び出し元関数の code オブジェクトの
    参照カウントが増え続けないこと。

    前提:
    - rtc_log は Python フレームから PyFrame_GetCode で code を取得する

    期待:
    - 呼び出し前後で sys.getrefcount(caller.__code__) が増えない
    """

    def caller() -> None:
        rtc_log(SoraLoggingSeverity.INFO, "refcount leak check")

    code = caller.__code__
    # getrefcount は一時参照分 +1 を含む。呼び出し前後の差分だけを見る。
    before = sys.getrefcount(code)
    iterations = 1000
    for _ in range(iterations):
        caller()
    after = sys.getrefcount(code)

    assert after == before, (
        f"PyCodeObject の参照がリークしている: before={before}, after={after}, "
        f"delta={after - before}, iterations={iterations}"
    )
