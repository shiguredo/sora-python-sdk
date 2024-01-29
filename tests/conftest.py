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
        # channel_id に利用する文字列をランダムにする
        "channel_id": f'${os.environ.get("TEST_CHANNEL_ID_PREFIX")}${uuid.uuid4().hex}',
        "secret": os.environ.get("TEST_SECRET_KEY"),
        "metadata": {"access_token": os.environ.get("TEST_SECRET_KEY")},
    }
