import time

import numpy
import pytest
from client import SoraClient, SoraRole


def test_video_frame_planes(settings):
    """
    SoraVideoFrame.planes() が正しい形式の I420 プレーンを返すことをテストする。
    """
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type="VP8",
    )
    sendonly.connect(fake_video=True)

    time.sleep(3)

    recvonly = SoraClient(
        settings,
        SoraRole.RECVONLY,
    )
    recvonly.connect()

    # フレームを受信するまで待つ
    frame = recvonly._q_out.get(timeout=10)

    # planes() を呼び出す
    y, u, v = frame.planes()

    # data() を呼び出して width, height を取得
    bgr = frame.data()
    height, width = bgr.shape[0], bgr.shape[1]

    # Y プレーンの形状を確認
    assert y.shape == (height, width), f"Y plane shape mismatch: {y.shape} != ({height}, {width})"

    # U プレーンの形状を確認 (I420: height/2, width/2)
    assert u.shape == (
        height // 2,
        width // 2,
    ), f"U plane shape mismatch: {u.shape} != ({height // 2}, {width // 2})"

    # V プレーンの形状を確認 (I420: height/2, width/2)
    assert v.shape == (
        height // 2,
        width // 2,
    ), f"V plane shape mismatch: {v.shape} != ({height // 2}, {width // 2})"

    # データ型が uint8 であることを確認
    assert y.dtype == numpy.uint8, f"Y plane dtype mismatch: {y.dtype}"
    assert u.dtype == numpy.uint8, f"U plane dtype mismatch: {u.dtype}"
    assert v.dtype == numpy.uint8, f"V plane dtype mismatch: {v.dtype}"

    sendonly.disconnect()
    recvonly.disconnect()


def test_video_frame_data_and_planes_both_work(settings):
    """
    SoraVideoFrame.data() と SoraVideoFrame.planes() が両方とも正しく動作することをテストする。
    """
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type="VP8",
    )
    sendonly.connect(fake_video=True)

    time.sleep(3)

    recvonly = SoraClient(
        settings,
        SoraRole.RECVONLY,
    )
    recvonly.connect()

    # フレームを受信するまで待つ
    frame = recvonly._q_out.get(timeout=10)

    # planes() を先に呼び出す
    y1, u1, v1 = frame.planes()

    # data() を呼び出す
    bgr = frame.data()
    height, width = bgr.shape[0], bgr.shape[1]

    # planes() をもう一度呼び出す
    y2, u2, v2 = frame.planes()

    # BGR データが正しい形状であることを確認
    assert bgr.shape == (height, width, 3)
    assert bgr.dtype == numpy.uint8

    # planes() の結果が一貫していることを確認
    assert y1.shape == y2.shape
    assert u1.shape == u2.shape
    assert v1.shape == v2.shape

    sendonly.disconnect()
    recvonly.disconnect()
