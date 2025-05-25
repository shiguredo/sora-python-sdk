from client import SoraClient, SoraRole


def test_signaling_notify(settings):
    """
    2 接続での connection.created と connection.destroyed の通知を確認する
    """
    with SoraClient(
        settings,
        SoraRole.SENDRECV,
        audio=True,
        video=True,
    ) as c1:
        # c1 に自分の connection.created が通知される
        notify = c1.wait_notify(lambda notify: notify["event_type"] == "connection.created")
        assert notify["connection_id"] == c1.connection_id
        assert notify["channel_connections"] == 1

        with SoraClient(
            settings,
            SoraRole.SENDRECV,
            audio=True,
            video=True,
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
