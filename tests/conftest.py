import importlib.metadata
import time
import uuid
from typing import Annotated

import jwt
import pytest
from pydantic import Field, HttpUrl, WebsocketUrl, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix=".env", env_nested_delimiter="utf-8"
    )

    signaling_urls: Annotated[list[WebsocketUrl], NoDecode] = Field(
        default=[], alias="TEST_SIGNALING_URLS"
    )
    channel_id_prefix: str = Field(default="", alias="TEST_CHANNEL_ID_PREFIX")
    secret: str | None = Field(default=None, alias="TEST_SECRET_KEY")
    api_url: HttpUrl | None = Field(default=None, alias="TEST_API_URL")
    openh264_path: str | None = Field(default=None, alias="OPENH264_PATH")

    channel_id_suffix: str = Field(default=str(uuid.uuid4()))

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

    def metadata(self, **kwargs) -> dict[str, str] | None:
        if self.secret is None:
            return None

        payload = {
            "channel_id": self.channel_id,
            # 現在時刻 + 300 秒 (5分)
            "exp": int(time.time()) + 300,
        }
        payload.update(kwargs)

        access_token = jwt.encode(
            payload,
            self.secret,
            algorithm="HS256",
        )

        return {"access_token": access_token}


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
