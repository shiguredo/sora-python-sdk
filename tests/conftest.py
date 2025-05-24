import importlib.metadata
import os
import uuid
from typing import Annotated

import pytest
from dotenv import load_dotenv
from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix=".env", env_nested_delimiter="utf-8"
    )

    signaling_urls: Annotated[list[str], NoDecode] = Field(default=[], alias="TEST_SIGNALING_URLS")
    channel_id_prefix: str = Field(default="", alias="TEST_CHANNEL_ID_PREFIX")
    secret: str = Field(default="", alias="TEST_SECRET_KEY")
    api_url: str = Field(default="", alias="TEST_API_URL")
    openh264_path: str | None = Field(default=None, alias="OPENH264_PATH")

    @field_validator("signaling_urls", mode="before")
    @classmethod
    def decode_signaling_urls(cls, v: str) -> list[str]:
        return [x.strip() for x in v.split(",")]

    @computed_field
    def channel_id(self) -> str:
        return f"{self.channel_id_prefix}_{uuid.uuid4()}"

    @computed_field
    def metadata(self) -> dict[str, str]:
        return {"access_token": self.secret}


def pytest_report_header(config):
    """pytest の実行時に特定のライブラリのバージョンを追加表示"""
    try:
        version = importlib.metadata.version("sora_sdk")
        return f"sora_sdk: {version}"
    except importlib.metadata.PackageNotFoundError:
        return "sora_sdk: Not installed"


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def setup():
    # 環境変数読み込み
    load_dotenv()

    # signaling_url 単体か複数かをランダムで決めてテストする
    if (test_signaling_urls := os.environ.get("TEST_SIGNALING_URLS")) is None:
        raise ValueError("TEST_SIGNALING_URLS is required.")

    # , で区切って ['wss://...', ...] に変換
    test_signaling_urls = test_signaling_urls.split(",")

    if (test_channel_id_prefix := os.environ.get("TEST_CHANNEL_ID_PREFIX")) is None:
        raise ValueError("TEST_CHANNEL_ID_PREFIX is required.")

    if (test_secret_key := os.environ.get("TEST_SECRET_KEY")) is None:
        raise ValueError("TEST_SECRET_KEY is required.")

    if (test_api_url := os.environ.get("TEST_API_URL")) is None:
        raise ValueError("TEST_API_URL is required.")

    return {
        "signaling_urls": test_signaling_urls,
        "channel_id_prefix": test_channel_id_prefix,
        "secret": test_secret_key,
        "api_url": test_api_url,
        "metadata": {"access_token": test_secret_key},
        # openh264_path は str | None でよい
        "openh264_path": os.environ.get("OPENH264_PATH"),
    }
