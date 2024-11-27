import sys
import time
import uuid

from client import SoraClient, SoraRole


def test_signaling_message(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
    )
    sendonly.connect(fake_audio=True, fake_video=True)

    time.sleep(5)

    sendonly.disconnect()

    assert sendonly.connect_message is not None
    assert sendonly.offer_message is not None
    assert sendonly.answer_message is not None

    assert sendonly.connect_message["role"] == "sendonly"
    assert sendonly.connect_message["channel_id"] == channel_id
    assert sendonly.connect_message["audio"] is True
    assert sendonly.connect_message["video"] is True
    assert sendonly.connect_message["metadata"] == metadata


def test_signaling_message_type_connect_forwarding_filter(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    forwarding_filter = {
        "name": "test",
        "priority": 128,
        "action": "block",
        "rules": [
            [
                {
                    "field": "connection_id",
                    "operator": "is_in",
                    "values": ["S8YEN0TSE13JDC2991NG4XZ150"],
                }
            ],
            [
                {"field": "client_id", "operator": "is_in", "values": ["screen-share"]},
                {"field": "kind", "operator": "is_in", "values": ["audio"]},
            ],
        ],
    }

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
        forwarding_filter=forwarding_filter,
    )
    sendonly.connect(fake_audio=True, fake_video=True)

    time.sleep(5)

    sendonly.disconnect()

    assert sendonly.connect_message is not None
    assert sendonly.connect_message["forwarding_filter"] == forwarding_filter


def test_signaling_message_type_connect_forwarding_filters(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    forwarding_filters = [
        {
            "name": "test",
            "priority": 128,
            "action": "block",
            "rules": [
                [
                    {
                        "field": "connection_id",
                        "operator": "is_in",
                        "values": ["S8YEN0TSE13JDC2991NG4XZ150"],
                    }
                ],
                [
                    {"field": "client_id", "operator": "is_in", "values": ["screen-share"]},
                    {"field": "kind", "operator": "is_in", "values": ["audio"]},
                ],
            ],
        },
        {
            "name": "test2",
            "priority": 129,
            "action": "block",
            "rules": [[{"field": "kind", "operator": "is_in", "values": ["audio", "video"]}]],
        },
    ]

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
        forwarding_filters=forwarding_filters,
    )
    sendonly.connect(fake_audio=True, fake_video=True)

    time.sleep(5)

    sendonly.disconnect()

    assert sendonly.connect_message is not None
    assert sendonly.connect_message["forwarding_filters"] == forwarding_filters
