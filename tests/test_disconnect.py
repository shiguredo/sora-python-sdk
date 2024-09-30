import sys
import uuid

from client import Sendonly


def test_sendonly_disconnect(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    with Sendonly(
        signaling_urls,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
    ) as sendonly1:
        with Sendonly(
            signaling_urls,
            channel_id,
            audio=True,
            video=True,
            metadata=metadata,
        ) as sendonly2:
            with Sendonly(
                signaling_urls,
                channel_id,
                audio=True,
                video=True,
                metadata=metadata,
            ) as sendonly3:
                with Sendonly(
                    signaling_urls,
                    channel_id,
                    audio=True,
                    video=True,
                    metadata=metadata,
                ) as sendonly4:
                    pass
