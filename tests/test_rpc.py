import time

from client import SoraClient, SoraRole


def test_messaging(settings):
    c1 = SoraClient(
        settings,
        SoraRole.RECVONLY,
    )
    c1.connect()

    c2 = SoraClient(
        settings,
        SoraRole.RECVONLY,
    )
    c2.connect()

    time.sleep(5)

    req_id = c1.send_rpc(
        "Sora_20201124.PutSignalingNotifyMetadataItem",
        {
            "key": "k1",
            "value": "v1",
            "push": True,
        },
    )
    assert req_id is not None

    response = c1.recv_rpc(timeout=5)

    assert response is not None
    # id が一致することを確認
    assert response["id"] == req_id

    """
    {
        "type": "push",
        "data": {
            "action": "PutMetadataItem",
            "connection_id": "0FQE5EA5YN3FS13P01QZ1JG8R0",
            "key": "abc",
            "value": "efg",
            "type": "signaling_notify_metadata_ext"
        }
    }
    """

    # c2 でメタデータ拡張の変更が Push で通知されていることを確認する
    push = c2.recv_push(timeout=5)
    assert push is not None
    assert "data" in push
    assert push["data"]["action"] == "PutMetadataItem"
    assert push["data"]["connection_id"] == c1.connection_id
    assert push["data"]["key"] == "k1"
    assert push["data"]["value"] == "v1"

    c1.disconnect()
    c2.disconnect()
