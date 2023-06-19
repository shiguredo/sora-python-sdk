import os
import time

from sora_sdk import Sora


def on_disconnect(error_code, message_abc: str):
    print(f'on_disconnect: error_code: {error_code}, message: {message_abc}')
    pass


# @pytest.mark.timeout(10)
def test_sendonly():
    sora = Sora()
    conn = sora.create_connection(
        signaling_url=os.environ.get("TEST_SIGNALING_URL"),
        role="recvonly",
        channel_id=os.environ.get("TEST_CHANNEL_ID_PREFIX") + "sora-python-sdk-test",
        metadata={"access_token": os.environ.get("TEST_SECREt_KEY")}
    )

    conn.on_disconnect = on_disconnect
    conn.connect()
    time.sleep(3)
    conn.disconnect()
