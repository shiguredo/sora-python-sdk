import sys
import time
import uuid

from messaging import Messaging


def test_messaging_sendonly(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    messaging_label = "#test"

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    metadata = setup.get("metadata")

    data_channels = [{"label": messaging_label, "direction": "sendonly"}]
    messaging_sendonly = Messaging(signaling_urls, channel_id, data_channels, metadata)

    # Sora に接続する
    messaging_sendonly.connect()

    message1 = "spam".encode("utf-8")
    message2 = "エッグ".encode("utf-8")

    messaging_sendonly.send(message1)
    messaging_sendonly.send(message2)

    time.sleep(3)

    messaging_sendonly_stats = messaging_sendonly.get_stats()
    data_channel_stats = next(
        s
        for s in messaging_sendonly_stats
        if s.get("type") == "data-channel" and s.get("label") == messaging_label
    )
    assert data_channel_stats["state"] == "open"
    assert data_channel_stats["messagesSent"] == 2
    assert data_channel_stats["bytesSent"] == (len(message1) + len(message2))

    messaging_sendonly.disconnect()
