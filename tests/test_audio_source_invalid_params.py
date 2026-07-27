"""
create_audio_source が不正な sample_rate / channels を ValueError で弾くことを検証する。

10 ms バッファは sample_rate / 100 で決まる。sample_rate < 100 や channels == 0 だと
バッファサイズが 0 になり、後続処理で未定義動作になり得る。
"""

from __future__ import annotations

import pytest

from sora_sdk import Sora


def test_create_audio_source_rejects_sample_rate_below_100():
    """
    sample_rate < 100 のとき ValueError になること。

    前提:
    - 10 ms バッファ長は sample_rate / 100

    期待:
    - 例外メッセージに sample_rate が含まれる
    """
    sora = Sora()
    with pytest.raises(ValueError, match="sample_rate"):
        sora.create_audio_source(1, 50)


def test_create_audio_source_rejects_zero_channels():
    """
    channels == 0 のとき ValueError になること。

    前提:
    - buffer_size は sample_rate / 100 * channels

    期待:
    - 例外メッセージに channels が含まれる
    """
    sora = Sora()
    with pytest.raises(ValueError, match="channels"):
        sora.create_audio_source(0, 16000)
