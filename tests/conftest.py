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

    if test_signaling_url is None and test_signaling_urls is None:
        raise ValueError("TEST_SIGNALING_URL or TEST_SIGNALING_URLS is required.")

    if test_signaling_urls is not None:
        # , で区切って ['wss://...', ...] に変換
        test_signaling_urls = test_signaling_urls.split(",")
    signaling_urls = random.choice([[test_signaling_url], test_signaling_urls])

    if test_channel_id_prefix := os.environ.get("TEST_CHANNEL_ID_PREFIX") is None:
        raise ValueError("TEST_CHANNEL_ID_PREFIX is required.")

    if test_secret_key := os.environ.get("TEST_SECRET_KEY") is None:
        raise ValueError("TEST_SECRET_KEY is required.")

    return {
        "signaling_urls": signaling_urls,
        "channel_id_prefix": test_channel_id_prefix,
        "secret": test_secret_key,
        "metadata": {"access_token": test_secret_key},
        # openh264_path は str | None でよい
        "openh264_path": os.environ.get("OPENH264_PATH"),
    }
