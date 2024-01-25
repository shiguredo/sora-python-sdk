import json
import os
import time

import sora_sdk


def on_data_channel(label):
    print("on_data_channel", label)


def on_message(label, data):
    print("on_message", label, data)


def send_message():
    sora = sora_sdk.Sora()
    connection = sora.create_connection(
        signaling_urls=[os.environ.get("TEST_SIGNALING_URL")],
        role="recvonly",
        channel_id=os.environ.get("TEST_CHANNEL_ID_PREFIX") + "sora-python-sdk-test",
        data_channel_signaling=True,
        data_channels=[{"label": "#spam", "direction": "sendrecv"}],
        metadata={"access_token": os.environ.get("TEST_SECRET_KEY")},
        audio=False,
        video=False,
    )

    connection.connect()

    time.sleep(1)

    connection.send_data_channel("#spam", b"Hello, world!")

    time.sleep(1)

    connection.disconnect()


def test_messaging_direction_recvonly():
    sora = sora_sdk.Sora()
    connection = sora.create_connection(
        signaling_urls=[os.environ.get("TEST_SIGNALING_URL")],
        role="recvonly",
        channel_id=os.environ.get("TEST_CHANNEL_ID_PREFIX") + "sora-python-sdk-test",
        data_channel_signaling=True,
        data_channels=[{"label": "#spam", "direction": "sendrecv"}],
        metadata={"access_token": os.environ.get("TEST_SECRET_KEY")},
        audio=False,
        video=False,
    )

    connection.on_data_channel = on_data_channel

    # 次の行をコメントアウトすると SIGSEGV は発生しない
    connection.on_message = on_message

    connection.connect()

    send_message()

    connection.disconnect()
