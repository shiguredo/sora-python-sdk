from __future__ import annotations

import argparse
import time

from client import SoraClient, SoraRole
from conftest import Settings


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run SoraClient quickly from CLI")

    p.add_argument(
        "--role",
        required=True,
        choices=[r.value for r in SoraRole],
        help="Connection role",
    )

    # メディア設定
    p.add_argument("--audio", action="store_true", help="Enable audio")
    p.add_argument("--video", action="store_true", help="Enable video")
    p.add_argument(
        "--video-codec-type", choices=["VP8", "VP9", "H264", "H265", "AV1"], help="Video codec type"
    )
    p.add_argument("--video-bit-rate", type=int, help="Video bitrate (bps)")
    p.add_argument("--video-width", type=int, default=960, help="Video width (default 960)")
    p.add_argument("--video-height", type=int, default=540, help="Video height (default 540)")

    # フェイクメディア
    p.add_argument("--fake-audio", action="store_true", help="Send fake audio")
    p.add_argument("--fake-video", action="store_true", help="Send fake video")
    p.add_argument(
        "--fake-video-type",
        choices=["random", "blend2d"],
        help="Fake video generator type. Default(None)=black frame",
    )

    # その他
    p.add_argument(
        "--signaling-url",
        action="append",
        help="Signaling URL (repeatable or comma-separated)",
    )
    p.add_argument("--channel-id", help="Override channel_id (settings)")
    p.add_argument(
        "--framerate",
        "--fps",
        dest="framerate",
        type=int,
        help="Fake video framerate (fps)",
    )
    p.add_argument(
        "--precise-timing",
        action="store_true",
        help="Use tighter frame pacing (may increase CPU)",
    )
    p.add_argument(
        "--duration",
        type=float,
        help="Run duration in seconds; omit for unlimited (CTRL-C to stop)",
    )

    return p.parse_args()


def main() -> int:
    args = parse_args()

    # signaling-url は複数指定またはカンマ区切り両対応
    signaling_urls: list[str] | None = None
    if args.signaling_url:
        signaling_urls = []
        for ent in args.signaling_url:
            signaling_urls.extend([x.strip() for x in ent.split(",") if x.strip()])

    settings = Settings(channel_id=args.channel_id, signaling_urls=signaling_urls)

    client = SoraClient(
        settings,
        role=SoraRole(args.role),
        audio=True if args.audio else False,
        video=True if args.video else False,
        video_codec_type=args.video_codec_type,
        video_bit_rate=args.video_bit_rate,
        video_width=args.video_width,
        video_height=args.video_height,
        fake_video_type=args.fake_video_type,  # None の場合は黒フレーム
        video_fps=args.framerate,
        precise_timing=args.precise_timing,
    )

    print(
        f"Connecting: role={args.role} channel_id={settings.channel_id} "
        f"signaling_urls={settings.signaling_urls} audio={args.audio} video={args.video} "
        f"fake_audio={args.fake_audio} fake_video={args.fake_video} fake_video_type={args.fake_video_type}"
    )
    client.connect(fake_audio=args.fake_audio, fake_video=args.fake_video)
    print(f"Connected: connection_id={client.connection_id}")

    start = time.perf_counter()
    try:
        while True:
            if (
                args.duration is not None
                and args.duration > 0
                and (time.perf_counter() - start) >= args.duration
            ):
                break
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
        print("Disconnected")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
