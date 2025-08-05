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

    time.sleep(3)

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
