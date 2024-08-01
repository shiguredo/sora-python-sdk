import os
import random

import pytest
from dotenv import load_dotenv


@pytest.fixture
def setup():
    # 環境変数読み込み
    load_dotenv()

    # signaling_url 単体か複数かをランダムで決めてテストする
    test_signaling_url = os.environ.get("TEST_SIGNALING_URL")
    test_signaling_urls = os.environ.get("TEST_SIGNALING_URLS")

    if test_signaling_urls is not None:
        # , で区切って ['wss://...', ...] に変換
        test_signaling_urls = test_signaling_urls.split(",")
    signaling_urls = random.choice([[test_signaling_url], test_signaling_urls])
    print(signaling_urls)

    return {
        "signaling_urls": signaling_urls,
        "channel_id_prefix": os.environ.get("TEST_CHANNEL_ID_PREFIX"),
        "secret": os.environ.get("TEST_SECRET_KEY"),
        "metadata": {"access_token": os.environ.get("TEST_SECRET_KEY")},
        "openh264_path": os.environ.get("OPENH264_PATH"),
    }
