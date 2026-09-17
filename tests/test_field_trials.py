"""
WebRTC-Video-PerSsrcKeyframes フィールドトライアルに関する検証をまとめる。

指定した文字列は sora-cpp-sdk の SoraClientContextConfig::field_trials を経由して
libwebrtc の Environment に設定される。不正な文字列 (例: Enabled の後に "/" が無いもの)
の場合は SoraClientContext::Create が nullptr を返すため RuntimeError になる。
"""

import time

import pytest
from api import request_key_frame_api
from client import SoraClient, SoraRole
from simulcast import default_video_bit_rate

from sora_sdk import Sora


def get_active_video_stats_by_rid(client: SoraClient) -> dict[str, dict]:
    """
    有効な映像レイヤの outbound-rtp 統計を rid ごとにまとめて返す。

    統計の値は型が一定しない JSON のオブジェクトのため、値の型は指定しない。
    bytesSent が 0 のレイヤは有効になっていないため対象外にする。
    """
    return {
        s["rid"]: s
        for s in client.get_stats()
        if s.get("type") == "outbound-rtp"
        and s.get("kind") == "video"
        and s.get("bytesSent", 0) > 0
    }


def get_key_frames_encoded(stats_by_rid: dict[str, dict]) -> dict[str, int]:
    """rid ごとの outbound-rtp 統計から keyFramesEncoded を取り出す。"""
    return {rid: stats["keyFramesEncoded"] for rid, stats in stats_by_rid.items()}


def connect_sendonly(settings, field_trials: str | None) -> SoraClient:
    """
    VP8 / サイマルキャストの SoraClient を生成して接続する。

    VP8 を指定し、3 レイヤが有効になるビットレートを明示する。レイヤの有効化には
    時間がかかるため、固定で 10 秒待ってから返す (条件待ちはしていない)。
    """
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
        field_trials=field_trials,
    )
    sendonly.connect(fake_video=True)

    # サイマルキャストの全レイヤが送信を開始するまで固定で 10 秒待つ
    time.sleep(10)

    return sendonly


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

    sendonly = connect_sendonly(settings, "WebRTC-Video-PerSsrcKeyframes/Enabled/")

    # connection_id は None になり得るため、API 呼び出しに使う前に絞り込む
    assert sendonly.connection_id is not None

    before = get_key_frames_encoded(get_active_video_stats_by_rid(sendonly))
    print("キーフレーム要求前のキーフレーム数:", before)

    response = request_key_frame_api(settings.api_url, sendonly.channel_id, sendonly.connection_id)

    time.sleep(5)

    after = get_key_frames_encoded(get_active_video_stats_by_rid(sendonly))
    print("キーフレーム要求後のキーフレーム数:", after)

    sendonly.disconnect()

    # 接続を閉じてから確認する。ここで失敗しても接続が残らない
    assert response.status_code == 200, response.text

    # サイマルキャストの全レイヤが有効になっていること
    assert len(after) == 3
    # キーフレーム要求により有効な全レイヤのキーフレーム数が増えていること
    for rid, count in before.items():
        assert after.get(rid, 0) > count, f"rid={rid} のキーフレーム数が増えていない"


@pytest.mark.parametrize(
    ("field_trials", "increased_rids"),
    [
        # フィールドトライアル有効時は PLI を受けた rid のレイヤだけがキーフレームを生成する
        ("WebRTC-Video-PerSsrcKeyframes/Enabled/", {"r2"}),
        # フィールドトライアル無効時はどの rid への PLI でも全レイヤがキーフレームを生成する
        (None, {"r0", "r1", "r2"}),
    ],
    ids=["field_trials_enabled", "field_trials_disabled"],
)
def test_per_ssrc_keyframes(settings, field_trials, increased_rids):
    """
    WebRTC-Video-PerSsrcKeyframes の有無で rid を指定したキーフレーム要求の結果が変わること。

    前提:
    - VP8 / 3 レイヤのサイマルキャストではレイヤごとに独立した libvpx エンコーダが使われる
      (encoderImplementation が "SimulcastEncoderAdapter (libvpx, libvpx, libvpx)" になる)
    - 単一の simulcast 対応エンコーダになる構成では、libvpx がどのレイヤへの要求でも
      全レイヤをキーフレームにするため、このテストの期待は成立しない
    - RequestKeyFrame API の rid 指定は Sora 2026.2.0-canary.15 以降で利用できる

    期待:
    - フィールドトライアル有効: rid=r2 のキーフレーム要求で r2 のみキーフレーム数が増える
    - フィールドトライアル無効: r0 / r1 / r2 すべてのキーフレーム数が増える

    前提が崩れた場合:
    - 要求前に 3 レイヤが有効でない場合は失敗させる
    - 品質制限がかかっている場合と、増加しないことを判定するレイヤがフレームを生成して
      いない場合は skip する
    """
    sendonly = connect_sendonly(settings, field_trials)

    # connection_id は None になり得るため、API 呼び出しに使う前に絞り込む
    assert sendonly.connection_id is not None

    stats_before = get_active_video_stats_by_rid(sendonly)
    key_frames_before = get_key_frames_encoded(stats_before)
    print("キーフレーム要求前のキーフレーム数:", key_frames_before)

    # rid を指定すると、その rid の SSRC にのみ PLI が送られる
    response = request_key_frame_api(
        settings.api_url, sendonly.channel_id, sendonly.connection_id, rid="r2"
    )

    # Sora はキーフレームを受け取るまで 1 秒間隔で PLI を再送するため、再送が終わるまで待つ
    time.sleep(5)

    stats_after = get_active_video_stats_by_rid(sendonly)
    key_frames_after = get_key_frames_encoded(stats_after)
    print("キーフレーム要求後のキーフレーム数:", key_frames_after)

    sendonly.disconnect()

    # 接続を閉じてから確認する。ここで失敗しても接続が残らない
    assert response.status_code == 200, response.text

    # 要求前に 3 レイヤすべてが有効になっていること。ここはテストの前提なので失敗させる
    assert len(stats_before) == 3, (
        f"有効な映像レイヤが 3 つではない: rids={sorted(stats_before)}, field_trials={field_trials!r}"
    )

    # 品質制限がかかっている場合もレイヤが無効化されうるので、安定したテストができないものとして
    # tests/test_simulcast.py と同じく skip する
    for stats in (*stats_before.values(), *stats_after.values()):
        if stats["qualityLimitationReason"] != "none":
            pytest.skip(
                f"rid={stats['rid']} の qualityLimitationReason: {stats['qualityLimitationReason']}"
            )

    # 増加しないことを判定するレイヤが実際にフレームを生成していることを確認する。
    # bytesSent と framesEncoded は累積値のため、止まっているレイヤも統計からは消えず、
    # キーフレーム数が変化しないことだけを見ると判定が空虚になる
    for rid in sorted(set(stats_before) - increased_rids):
        if stats_after[rid]["framesEncoded"] == stats_before[rid]["framesEncoded"]:
            pytest.skip(f"rid={rid} のレイヤがキーフレーム要求の間にフレームを生成していない")

    for rid, count in key_frames_before.items():
        if rid in increased_rids:
            assert key_frames_after[rid] > count, (
                f"rid={rid} のキーフレーム数が増えていない: "
                f"before={count}, after={key_frames_after[rid]}, field_trials={field_trials!r}"
            )
        else:
            assert key_frames_after[rid] == count, (
                f"rid={rid} のキーフレーム数が増えている: "
                f"before={count}, after={key_frames_after[rid]}, field_trials={field_trials!r}"
            )
