import sys
import time
import uuid

from client import Messaging


def test_messaging(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    messaging_label = "#test"

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    metadata = setup.get("metadata")

    messaging_sendonly = Messaging(
        signaling_urls,
        channel_id,
        [{"label": messaging_label, "direction": "sendonly"}],
        metadata=metadata,
    )

    messaging_recvonly = Messaging(
        signaling_urls,
        channel_id,
        [{"label": messaging_label, "direction": "recvonly"}],
        metadata=metadata,
    )

    # Sora に接続する
    messaging_sendonly.connect()
    messaging_recvonly.connect()

    time.sleep(3)

    # data_channel_signaling: true だし
    # switched のテストはここでやる
    assert messaging_sendonly.switched
    assert messaging_recvonly.switched

    message1 = "spam".encode("utf-8")
    message2 = "はむ".encode("utf-8")

    messaging_sendonly.send(message1)
    messaging_sendonly.send(message2)

    time.sleep(3)

    messaging_sendonly_stats = messaging_sendonly.get_stats()
    messaging_recvonly_stats = messaging_recvonly.get_stats()

    messaging_sendonly.disconnect()
    messaging_recvonly.disconnect()

    sendonly_data_channel_stats = next(
        s
        for s in messaging_sendonly_stats
        if s.get("type") == "data-channel" and s.get("label") == messaging_label
    )
    print(sendonly_data_channel_stats)
    assert sendonly_data_channel_stats["state"] == "open"
    assert sendonly_data_channel_stats["messagesSent"] == 2
    assert sendonly_data_channel_stats["bytesSent"] == (len(message1) + len(message2))

    recvonly_data_channel_stats = next(
        s
        for s in messaging_recvonly_stats
        if s.get("type") == "data-channel" and s.get("label") == messaging_label
    )
    assert recvonly_data_channel_stats["state"] == "open"
    assert recvonly_data_channel_stats["messagesReceived"] == 2
    assert recvonly_data_channel_stats["bytesReceived"] == (len(message1) + len(message2))
