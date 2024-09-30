import sys
import uuid

from client import SoraClient, SoraRole


def test_sendonly_disconnect(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    with SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
        data_channel_signaling=True,
    ):
        pass
    #     with SoraClient(
    #         signaling_urls,
    #         SoraRole.SENDONLY,
    #         channel_id,
    #         audio=True,
    #         video=True,
    #         metadata=metadata,
    #         data_channel_signaling=True,
    #     ):
    #         with SoraClient(
    #             signaling_urls,
    #             SoraRole.SENDONLY,
    #             channel_id,
    #             audio=True,
    #             video=True,
    #             metadata=metadata,
    #             data_channel_signaling=True,
    #         ):
    #             with SoraClient(
    #                 signaling_urls,
    #                 SoraRole.SENDONLY,
    #                 channel_id,
    #                 audio=True,
    #                 video=True,
    #                 metadata=metadata,
    #                 data_channel_signaling=True,
    #             ):
    #                 pass
