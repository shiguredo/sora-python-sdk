import os
import random

import pytest
from dotenv import load_dotenv


@pytest.fixture
def setup():
    # 環境変数読み込み
    load_dotenv()

    # signaling_url 単体か複数かをランダムで決めてテストする
    signaling_url = os.environ.get("TEST_SIGNALING_URL")
    if signaling_urls := os.environ.get("TEST_SIGNALING_URLS"):
        signaling_urls = signaling_urls.split(",")
    signaling_urls = random.choice([[signaling_url], signaling_urls])

    return {
        "signaling_urls": signaling_urls,
        "channel_id_prefix": os.environ.get("TEST_CHANNEL_ID_PREFIX"),
        "secret": os.environ.get("TEST_SECRET_KEY"),
        "metadata": {"access_token": os.environ.get("TEST_SECRET_KEY")},
        "openh264_path": os.environ.get("OPENH264_PATH"),
    }
