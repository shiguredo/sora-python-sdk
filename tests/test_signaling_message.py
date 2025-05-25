import time

from client import SoraClient, SoraRole


def test_signaling_message(settings):
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=True,
        video=True,
    )
    sendonly.connect(fake_audio=True, fake_video=True)

    time.sleep(5)

    sendonly.disconnect()

    assert sendonly.connect_message is not None
    assert sendonly.offer_message is not None
    assert sendonly.answer_message is not None

    assert sendonly.connect_message["role"] == "sendonly"
    assert sendonly.connect_message["channel_id"] == settings.channel_id
    assert sendonly.connect_message["audio"] is True
    assert sendonly.connect_message["video"] is True
    assert sendonly.connect_message["metadata"] == sendonly.metadata


def test_signaling_message_type_connect_forwarding_filter(settings):
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
        settings,
        SoraRole.SENDONLY,
        audio=True,
        video=True,
        forwarding_filter=forwarding_filter,
    )
    sendonly.connect(fake_audio=True, fake_video=True)

    time.sleep(5)

    sendonly.disconnect()

    assert sendonly.connect_message is not None
    assert sendonly.connect_message["forwarding_filter"] == forwarding_filter


def test_signaling_message_type_connect_forwarding_filters(settings):
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
        settings,
        SoraRole.SENDONLY,
        audio=True,
        video=True,
        forwarding_filters=forwarding_filters,
    )
    sendonly.connect(fake_audio=True, fake_video=True)

    time.sleep(5)

    sendonly.disconnect()

    assert sendonly.connect_message is not None
    assert sendonly.connect_message["forwarding_filters"] == forwarding_filters
