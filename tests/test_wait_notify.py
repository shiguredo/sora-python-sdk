import gc

import pytest
from client import SoraClient, SoraRole


def test_wait_notify_timeout(settings):
    """
    wait_notify がタイムアウトしたとき、label ・ timeout ・受信済み event_type 一覧を
    含む AssertionError を raise すること。

    前提:
    - _notify_queue に述語にマッチしない notify が残っている

    期待:
    - タイムアウト時に「どの label で・何秒待って・何を受信したか」が
      エラーメッセージから読み取れる
    """
    client = SoraClient(settings, SoraRole.SENDRECV)

    # 述語にマッチしない notify を 2 件投入し、受信済み一覧に記録されることを検証する
    client._notify_queue.put({"event_type": "connection.created"})
    client._notify_queue.put({"event_type": "spotlight.changed"})

    with pytest.raises(AssertionError) as exc_info:
        client.wait_notify(
            lambda notify: False,
            timeout=0.2,
            label="テスト用の接続",
        )

    message = str(exc_info.value)
    assert "label=テスト用の接続" in message
    assert "timeout=0.2s" in message
    assert "['connection.created', 'spotlight.changed']" in message

    # 1 件も受信していない場合も、空の一覧がエラーメッセージに含まれること
    with pytest.raises(AssertionError) as exc_info_empty:
        client.wait_notify(
            lambda notify: False,
            timeout=0.2,
            label="テスト用の接続",
        )
    assert "received_event_types=[]" in str(exc_info_empty.value)

    # 未接続の SoraConnection は破棄時に OnDisconnect を最大 10 秒待つため、
    # 参照サイクルが残るとプロセス終了時に隠れて待ちが発生する。
    # 明示的に収集して破棄コストをこのテストに帰属させ、決定的にする
    del client, exc_info, exc_info_empty
    gc.collect()
