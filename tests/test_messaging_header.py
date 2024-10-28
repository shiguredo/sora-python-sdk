import sys
import time
import uuid

from client import SoraClient, SoraRole


def test_messaging_header(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    messaging_label = "#test"

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    metadata = setup.get("metadata")

    messaging_sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        data_channel_signaling=True,
        data_channels=[{"label": messaging_label, "direction": "sendonly"}],
        metadata=metadata,
    )

    messaging_recvonly = SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        data_channel_signaling=True,
        data_channels=[
            {
                "label": messaging_label,
                "direction": "recvonly",
                "header": [{"type": "sender_connection_id"}],
            }
        ],
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

    messaging_sendonly.send_message(messaging_label, message1)
    messaging_sendonly.send_message(messaging_label, message2)

    time.sleep(3)

    # 26 は sender_connection_id の長さ
    assert messaging_recvonly.recv_message(messaging_label)[26:] == message1
    assert messaging_recvonly.recv_message(messaging_label)[26:] == message2

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
    # 26 は sender_connection_id の長さ x 2
    assert recvonly_data_channel_stats["bytesReceived"] == (26 + len(message1) + 26 + len(message2))
