import os
import uuid

import pytest
from dotenv import load_dotenv


@pytest.fixture
def setup():
    # 環境変数読み込み
    load_dotenv()
    return {
        "signaling_urls": [os.environ.get("TEST_SIGNALING_URL")],
        "channel_id_prefix": os.environ.get("TEST_CHANNEL_ID_PREFIX"),
        # 乱数に使う場合にどうぞ
        "uuid": uuid.uuid4().hex,
        "secret": os.environ.get("TEST_SECRET_KEY"),
        "metadata": {"access_token": os.environ.get("TEST_SECRET_KEY")},
    }
