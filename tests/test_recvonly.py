import os
import time

from sora_sdk import Sora


def on_disconnect(error_code, message: str):
    print(f"on_disconnect: error_code: {error_code}, message: {message}")


def test_sendonly():
    sora = Sora()

    conn = sora.create_connection(
        signaling_urls=[os.environ.get("TEST_SIGNALING_URL")],
        role="recvonly",
        channel_id=os.environ.get("TEST_CHANNEL_ID_PREFIX") + "sora-python-sdk-test",
        metadata={"access_token": os.environ.get("TEST_SECRET_KEY")},
    )

    conn.on_disconnect = on_disconnect
    conn.connect()
    time.sleep(3)
    conn.disconnect()
