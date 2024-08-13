import sys
import time
import uuid

from messaging import Messaging


def test_messaging_sendonly(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    messaging_label = "#test"

    print(signaling_urls)
    print(channel_id_prefix)
    print(messaging_label)

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    metadata = setup.get("metadata")

    data_channels = [{"label": messaging_label, "direction": "sendonly"}]
    messaging_sendonly = Messaging(signaling_urls, channel_id, data_channels, metadata)

    # Sora に接続する
    messaging_sendonly.connect()

    messaging_sendonly.send("spam".encode("utf-8"))
    messaging_sendonly.send("エッグ".encode("utf-8"))

    time.sleep(3)

    messaging_sendonly.disconnect()
