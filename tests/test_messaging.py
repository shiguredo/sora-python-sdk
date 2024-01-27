import json
import os
import time

from dotenv import load_dotenv

from sora_sdk import Sora

load_dotenv()


class Messaging:
    connection_created = False

    def __init__(self, signaling_urls, channel_id, label, direction, metadata):
        self.sora = Sora()
        self.connection = self.sora.create_connection(
            signaling_urls=signaling_urls,
            role="sendrecv",
            channel_id=channel_id,
            metadata=metadata,
            audio=False,
            video=False,
            data_channels=[{"label": label, "direction": direction}],
            data_channel_signaling=True,
        )

        self.disconnected = False
        self.label = label
        self.is_data_channel_ready = False
        self.connection.on_set_offer = self.on_set_offer
        self.connection.on_notify = self.on_notify
        self.connection.on_data_channel = self.on_data_channel
        self.connection.on_message = self.on_message
        self.connection.on_disconnect = self.on_disconnect

    def on_set_offer(self, raw_offer):
        offer = json.loads(raw_offer)
        if offer["type"] == "offer":
            self.connection_id = offer["connection_id"]

    def on_notify(self, raw_message):
        message = json.loads(raw_message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self.connection_id
        ):
            print(f"Sora に接続しました: connection_id={self.connection_id}")
            self.connection_created = True

    def on_disconnect(self, error_code, message):
        print(f"Sora から切断しました: error_code='{error_code}' message='{message}'")
        self.disconnected = True

    def on_message(self, label, data):
        print(f"メッセージを受信しました: label={label}, data={data}")

    def on_data_channel(self, label):
        if self.label == label:
            self.is_data_channel_ready = True

    def connect(self):
        self.connection.connect()

    def send(self, data):
        # on_data_channel() が呼ばれるまではデータチャネルの準備ができていないので待機
        while not self.is_data_channel_ready and not self.disconnected:
            time.sleep(0.01)

        self.connection.send_data_channel(self.label, data)
        print(f"メッセージを送信しました: label={self.label}, data={data}")

    def disconnect(self):
        self.connection.disconnect()


def sendonly(signaling_urls, channel_id, label, metadata):
    msg_sendonly = Messaging(signaling_urls, channel_id, label, "sendonly", metadata)
    msg_sendonly.connect()

    time.sleep(3)

    assert msg_sendonly.connection_created is True

    msg_sendonly.connection.send_data_channel(label, b"Hello, world!")

    time.sleep(1)

    msg_sendonly.disconnect()


def recvonly(signaling_urls, channel_id, label, metadata):
    msg_recvonly = Messaging(signaling_urls, channel_id, label, "recvonly", metadata)
    msg_recvonly.connect()

    time.sleep(3)

    assert msg_recvonly.connection_created is True

    time.sleep(3)

    msg_recvonly.disconnect()


def test_messaging_direction_recvonly():
    signaling_urls = [os.environ.get("TEST_SIGNALING_URL")]
    channel_id = os.environ.get("TEST_CHANNEL_ID_PREFIX") + "sora-python-sdk-test"
    label = "#spam"
    metadata = {"access_token": os.environ.get("TEST_SECRET_KEY")}

    msg_recvonly = Messaging(signaling_urls, channel_id, label, "recvonly", metadata)
    msg_sendonly = Messaging(signaling_urls, channel_id, label, "sendonly", metadata)

    assert msg_recvonly.connection_created is False
    assert msg_sendonly.connection_created is False

    msg_recvonly.connect()
    msg_sendonly.connect()

    time.sleep(3)

    assert msg_recvonly.connection_created is True
    assert msg_sendonly.connection_created is True

    msg_sendonly.send(b"Hello, world!")

    time.sleep(3)

    msg_recvonly.disconnect()
    msg_sendonly.disconnect()
