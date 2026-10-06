import time

import pytest
from api import request_key_frame_api
from client import (
    SoraClient,
    SoraRole,
    codec_type_string_to_codec_type,
)

from sora_sdk import (
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
)


@pytest.mark.parametrize(
    "video_codec_type",
    [
        "VP9",
        "VP8",
        "AV1",
    ],
)
def test_key_frame_request(settings, video_codec_type):
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type=video_codec_type,
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=codec_type_string_to_codec_type(video_codec_type),
                    encoder=SoraVideoCodecImplementation.INTERNAL,
                ),
            ]
        ),
    )
    sendonly.connect(fake_video=True)

    # RequestKeyFrame はキーフレームを受け取る相手がいる配信者にだけ PLI を送るため、
    # 同じチャンネルに視聴者 (recvonly) を 1 本用意する
    recvonly = SoraClient(settings, SoraRole.RECVONLY, audio=False, video=True)
    recvonly.connect()

    time.sleep(5)

    assert sendonly.connection_id is not None

    # キーフレーム要求 API を 3 秒間隔で 3 回呼び出す
    api_count = 3
    for _ in range(api_count):
        response = request_key_frame_api(
            settings.api_url, sendonly.channel_id, sendonly.connection_id
        )
        assert response.status_code == 200
        time.sleep(3)

    # 統計を取得する
    sendonly_stats = sendonly.get_stats()

    sendonly.disconnect()
    recvonly.disconnect()

    # outbound-rtp が無かったら StopIteration 例外が上がる
    outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")

    # 3 回以上
    assert outbound_rtp_stats["keyFramesEncoded"] > api_count
    assert outbound_rtp_stats["pliCount"] >= api_count
    print("keyFramesEncoded:", outbound_rtp_stats["keyFramesEncoded"])
    print("pliCount:", outbound_rtp_stats["pliCount"])

    # PLI カウントの 50% 以上がキーフレームとしてエンコードされることを確認
    assert outbound_rtp_stats["keyFramesEncoded"] >= outbound_rtp_stats["pliCount"] * 0.7
    print(
        "keyFramesEncoded >= pliCount * 0.7:",
        outbound_rtp_stats["keyFramesEncoded"] >= outbound_rtp_stats["pliCount"] * 0.7,
    )


def video_outbound_rtp(stats):
    """outbound-rtp の映像統計を取り出す。無ければ StopIteration 例外が上がる。"""
    return next(s for s in stats if s.get("type") == "outbound-rtp" and s.get("kind") == "video")


def test_key_frame_request_without_consumer(settings):
    """
    キーフレームを受け取る相手がいない配信者へのキーフレーム要求では PLI が送られないこと。

    前提:
    - RequestKeyFrame API はキーフレームを受け取る相手 (視聴者、クラスターのリレー、
      録画、 RTP 転送) がいない配信者には PLI を送らない
    - 送らない場合も API は成功を返す

    期待:
    - 視聴者がいない状態で API を呼ぶと 200 が返る
    - PLI が送られないため pliCount が増えない
    """
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type="VP8",
    )
    sendonly.connect(fake_video=True)

    # 視聴者を用意せず、録画と RTP 転送も使わない状態にする
    time.sleep(5)

    assert sendonly.connection_id is not None

    stats_before = video_outbound_rtp(sendonly.get_stats())

    response = request_key_frame_api(settings.api_url, sendonly.channel_id, sendonly.connection_id)

    # Sora はキーフレームを受け取るまで 1 秒間隔で最大 5 回 PLI を再送するため、その間待つ
    time.sleep(5)

    stats_after = video_outbound_rtp(sendonly.get_stats())

    sendonly.disconnect()

    # 相手がいない場合も API は成功を返す
    assert response.status_code == 200, response.text
    # キーフレームを受け取る相手がいないため PLI は送られない
    assert stats_after["pliCount"] == stats_before["pliCount"], (
        f"pliCount が増えている: before={stats_before['pliCount']}, after={stats_after['pliCount']}"
    )
