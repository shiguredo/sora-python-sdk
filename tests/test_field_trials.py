"""
WebRTC-Video-PerSsrcKeyframes フィールドトライアルを指定できることを検証する。

sora-cpp-sdk の SoraClientContextConfig::field_trials に指定した文字列は
libwebrtc の Environment に設定される。不正な文字列の場合は
SoraClientContext::Create が nullptr を返すため RuntimeError になる。
"""

import time

import pytest
from api import request_key_frame_api
from client import SoraClient, SoraRole
from simulcast import default_video_bit_rate

from sora_sdk import Sora


def test_field_trials(settings):
    """
    WebRTC-Video-PerSsrcKeyframes を指定した Sora でキーフレーム要求が動作すること。

    前提:
    - 不正なフィールドトライアル文字列では SoraClientContext の生成に失敗する
    - サイマルキャストの全レイヤを有効にするためビットレートを明示する

    期待:
    - 不正な文字列では RuntimeError になる
    - キーフレーム要求 API の呼び出しで有効な全レイヤのキーフレーム数が増える
    """
    # 文字列の末尾に "/" が無い場合は不正なフィールドトライアル文字列として扱われる
    with pytest.raises(RuntimeError):
        Sora(
            openh264=settings.openh264_path,
            field_trials="WebRTC-Video-PerSsrcKeyframes/Enabled",
        )

    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        simulcast=True,
        audio=False,
        video=True,
        video_codec_type="VP8",
        video_bit_rate=default_video_bit_rate("VP8", 1280, 720),
        video_width=1280,
        video_height=720,
        field_trials="WebRTC-Video-PerSsrcKeyframes/Enabled/",
    )
    sendonly.connect(fake_video=True)

    # サイマルキャストの全レイヤが送信を開始するまで待つ
    time.sleep(10)

    assert sendonly.connection_id is not None

    def get_key_frames_encoded() -> dict[str, int]:
        # bytesSent が 0 のレイヤは有効になっていないため対象外にする
        return {
            s["rid"]: s["keyFramesEncoded"]
            for s in sendonly.get_stats()
            if s.get("type") == "outbound-rtp"
            and s.get("kind") == "video"
            and s.get("bytesSent", 0) > 0
        }

    before = get_key_frames_encoded()
    print("キーフレーム要求前のキーフレーム数:", before)

    response = request_key_frame_api(settings.api_url, sendonly.channel_id, sendonly.connection_id)
    assert response.status_code == 200

    time.sleep(5)

    after = get_key_frames_encoded()
    print("キーフレーム要求後のキーフレーム数:", after)

    sendonly.disconnect()

    # サイマルキャストの全レイヤが有効になっていること
    assert len(after) == 3
    # キーフレーム要求により有効な全レイヤのキーフレーム数が増えていること
    for rid, count in before.items():
        assert after.get(rid, 0) > count, f"rid={rid} のキーフレーム数が増えていない"
