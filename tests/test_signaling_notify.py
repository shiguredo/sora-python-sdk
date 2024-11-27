import sys
import uuid

from client import SoraClient, SoraRole


def test_signaling_notify(setup):
    """
    2 接続での connection.created と connection.destroyed の通知を確認する
    """
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    with SoraClient(
        signaling_urls,
        SoraRole.SENDRECV,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
    ) as c1:
        # c1 に自分の connection.created が通知される
        notify = c1.wait_notify(lambda notify: notify["event_type"] == "connection.created")
        assert notify["connection_id"] == c1.connection_id
        assert notify["channel_connections"] == 1

        with SoraClient(
            signaling_urls,
            SoraRole.SENDRECV,
            channel_id,
            audio=True,
            video=True,
            metadata=metadata,
        ) as c2:
            # c2 に自分の connection.created が通知される
            notify = c2.wait_notify(lambda notify: notify["event_type"] == "connection.created")
            assert notify["connection_id"] == c2.connection_id
            assert notify["channel_connections"] == 2
            # data に c1 の connection_id が入ってる
            assert notify["data"][0]["connection_id"] == c1.connection_id

            # c1 に c2 の connection.created が通知される
            notify = c1.wait_notify(lambda notify: notify["event_type"] == "connection.created")
            assert notify["connection_id"] == c2.connection_id
            assert notify["channel_connections"] == 2

        # c1 に c2 の connection.destroyed が通知される
        notify = c1.wait_notify(lambda notify: notify["event_type"] == "connection.destroyed")
        assert notify["connection_id"] == c2.connection_id
        assert notify["channel_connections"] == 1
