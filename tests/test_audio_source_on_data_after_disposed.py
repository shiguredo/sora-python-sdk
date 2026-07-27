"""
SoraAudioSource.on_data が track_ 破棄後に安全に no-op することを検証する。

Sora (publisher) 破棄で track_ が nullptr になる。null チェックが無いオーバーロードだと
source_->OnData を呼んで未定義動作になり得る。
"""

from __future__ import annotations

import gc

import numpy

from sora_sdk import Sora


def test_audio_source_on_data_is_noop_after_publisher_disposed():
    """
    publisher 破棄後の on_data 呼び出しが SEGV せず no-op になること。

    前提:
    - SoraAudioSource は Sora の子として作られ、Sora 破棄で PublisherDisposed される
    - PublisherDisposed は track_ を nullptr にする

    期待:
    - ndarray オーバーロード (timestamp 有無) を呼んでも例外も SEGV も起きない
    """
    sora = Sora()
    source = sora.create_audio_source(1, 16000)

    # publisher を破棄して track_ = nullptr にする
    del sora
    gc.collect()

    samples = numpy.zeros((160, 1), dtype=numpy.int16)

    # timestamp 無し / 有りの ndarray オーバーロードを両方叩く
    source.on_data(samples)
    source.on_data(samples, 0.0)
