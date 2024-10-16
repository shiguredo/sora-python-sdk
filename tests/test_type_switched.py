import sys
import uuid

import pytest
from client import SoraClient, SoraRole


@pytest.mark.skip(reason="Sora がまだ対応していない")
def test_type_switched_ignore_disconnect_websocket_true(setup):
    # switched 前に type: disconnect を送りつける
    # ignore_disconnect_websocket は true
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    with SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
        data_channel_signaling=True,
        ignore_disconnect_websocket=True,
    ) as conn:
        conn.disconnect()

        assert conn.switched is False
        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "TYPE-DISCONNECT"
