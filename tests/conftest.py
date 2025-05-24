import importlib.metadata
import uuid
from typing import Annotated

import pytest
from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix=".env", env_nested_delimiter="utf-8"
    )

    signaling_urls: Annotated[list[str], NoDecode] = Field(default=[], alias="TEST_SIGNALING_URLS")
    channel_id_prefix: str = Field(default="", alias="TEST_CHANNEL_ID_PREFIX")
    channel_id_suffix: str = Field(default=str(uuid.uuid4()))
    secret: str = Field(default="", alias="TEST_SECRET_KEY")
    api_url: str = Field(default="", alias="TEST_API_URL")
    openh264_path: str | None = Field(default=None, alias="OPENH264_PATH")

    @field_validator("signaling_urls", mode="before")
    @classmethod
    def decode_signaling_urls(cls, v: str) -> list[str]:
        """
        TEST_SIGNALING_URLS が , で区切られている場合、それぞれの URL をリストに変換する
        """
        return [x.strip() for x in v.split(",")]

    @computed_field
    def channel_id(self) -> str:
        """
        TEST_CHANNEL_ID_PREFIX と TEST_CHANNEL_ID_SUFFIX を組み合わせて channel_id を生成する
        """
        return f"{self.channel_id_prefix}_{self.channel_id_suffix}"

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
