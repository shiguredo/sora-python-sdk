"""
- サイマルキャストは期待しているビットレート以上が出ていれば良いと判断する
- 厳密なビットレートの計算はしない
"""

# 60% 以上のビットレートが出ていれば良いと判断する
MIN_TARGET_BITRATE_RATIO = 0.6


def default_video_bit_rate(video_codec_type, width, height) -> int:
    if video_codec_type in ["VP8", "H264"]:
        match (width, height):
            case (1920, 1080):
                return 4000 + 1200 + 350
            case (1280, 720):
                return 2500 + 500 + 150
            case (960, 540):
                return 1200 + 350
            case (640, 360):
                return 500 + 150
            case (480, 270):
                return 350 + 150
            case (320, 180):
                return 150

    if video_codec_type in ["VP9", "AV1", "H265"]:
        match (width, height):
            case (1920, 1080):
                return 3367 + 879 + 257
            case (1280, 720):
                return 1524 + 420 + 142
            case (960, 540):
                return 879 + 257 + 101
            case (640, 360):
                return 420 + 142
            case (480, 270):
                return 257 + 101
            case (320, 180):
                return 142
            case (240, 135):
                return 101

    raise ValueError(f"Invalid codec type: {video_codec_type}")


def expect_target_bitrate(video_codec_type, frameWidth, frameHeight):
    return (
        simulcast_format(video_codec_type, frameWidth, frameHeight)
        * 1000
        * MIN_TARGET_BITRATE_RATIO
    )


def simulcast_format(codec_type, width, height):
    if codec_type in ["VP8", "H264"]:
        return simulcast_format_vp8(width, height)
    elif codec_type in ["VP9", "AV1", "H265"]:
        return simulcast_format_vp9(width, height)
    else:
        raise ValueError(f"Invalid codec type: {codec_type}")


def simulcast_format_vp8(width, height):
    """
    // These tables describe from which resolution we can use how many
    // simulcast layers at what bitrates (maximum, target, and minimum).
    // Important!! Keep this table from high resolution to low resolution.
    constexpr const SimulcastFormat kSimulcastFormatsVP8[] = {
        {1920, 1080, 3, webrtc::DataRate::KilobitsPerSec(5000),
        webrtc::DataRate::KilobitsPerSec(4000),
        webrtc::DataRate::KilobitsPerSec(800)},
        {1280, 720, 3, webrtc::DataRate::KilobitsPerSec(2500),
        webrtc::DataRate::KilobitsPerSec(2500),
        webrtc::DataRate::KilobitsPerSec(600)},
        {960, 540, 3, webrtc::DataRate::KilobitsPerSec(1200),
        webrtc::DataRate::KilobitsPerSec(1200),
        webrtc::DataRate::KilobitsPerSec(350)},
        {640, 360, 2, webrtc::DataRate::KilobitsPerSec(700),
        webrtc::DataRate::KilobitsPerSec(500),
        webrtc::DataRate::KilobitsPerSec(150)},
        {480, 270, 2, webrtc::DataRate::KilobitsPerSec(450),
        webrtc::DataRate::KilobitsPerSec(350),
        webrtc::DataRate::KilobitsPerSec(150)},
        {320, 180, 1, webrtc::DataRate::KilobitsPerSec(200),
        webrtc::DataRate::KilobitsPerSec(150),
        webrtc::DataRate::KilobitsPerSec(30)},
        // As the resolution goes down, interpolate the target and max bitrates down
        // towards zero. The min bitrate is still limited at 30 kbps and the target
        // and the max will be capped from below accordingly.
        {0, 0, 1, webrtc::DataRate::KilobitsPerSec(0),
        webrtc::DataRate::KilobitsPerSec(0),
        webrtc::DataRate::KilobitsPerSec(30)}};
    """
    # vp8 では 240x135 は未定義なので 150 と仮定する
    if width * height <= 240 * 135:
        return 150
    elif width * height <= 320 * 180:
        return 200
    elif width * height <= 480 * 270:
        return 350
    elif width * height <= 640 * 360:
        return 500
    elif width * height <= 960 * 540:
        return 1200
    elif width * height <= 1280 * 720:
        return 2500
    elif width * height <= 1920 * 1080:
        return 4000
    else:
        raise ValueError(f"Invalid width: {width}, height: {height}")


def simulcast_format_vp9(width, height):
    """
    // These tables describe from which resolution we can use how many
    // simulcast layers at what bitrates (maximum, target, and minimum).
    // Important!! Keep this table from high resolution to low resolution.
    constexpr const SimulcastFormat kSimulcastFormatsVP9[] = {
        {1920, 1080, 3, webrtc::DataRate::KilobitsPerSec(3367),
        webrtc::DataRate::KilobitsPerSec(3367),
        webrtc::DataRate::KilobitsPerSec(769)},
        {1280, 720, 3, webrtc::DataRate::KilobitsPerSec(1524),
        webrtc::DataRate::KilobitsPerSec(1524),
        webrtc::DataRate::KilobitsPerSec(481)},
        {960, 540, 3, webrtc::DataRate::KilobitsPerSec(879),
        webrtc::DataRate::KilobitsPerSec(879),
        webrtc::DataRate::KilobitsPerSec(337)},
        {640, 360, 2, webrtc::DataRate::KilobitsPerSec(420),
        webrtc::DataRate::KilobitsPerSec(420),
        webrtc::DataRate::KilobitsPerSec(193)},
        {480, 270, 2, webrtc::DataRate::KilobitsPerSec(257),
        webrtc::DataRate::KilobitsPerSec(257),
        webrtc::DataRate::KilobitsPerSec(121)},
        {320, 180, 1, webrtc::DataRate::KilobitsPerSec(142),
        webrtc::DataRate::KilobitsPerSec(142),
        webrtc::DataRate::KilobitsPerSec(30)},
        {240, 135, 1, webrtc::DataRate::KilobitsPerSec(101),
        webrtc::DataRate::KilobitsPerSec(101),
        webrtc::DataRate::KilobitsPerSec(30)},
        // As the resolution goes down, interpolate the target and max bitrates down
        // towards zero. The min bitrate is still limited at 30 kbps and the target
        // and the max will be capped from below accordingly.
        {0, 0, 1, webrtc::DataRate::KilobitsPerSec(0),
        webrtc::DataRate::KilobitsPerSec(0),
        webrtc::DataRate::KilobitsPerSec(30)}};
    """
    if width * height <= 240 * 135:
        return 101
    elif width * height <= 320 * 180:
        return 142
    elif width * height <= 480 * 270:
        return 257
    elif width * height <= 640 * 360:
        return 420
    elif width * height <= 960 * 540:
        return 879
    elif width * height <= 1280 * 720:
        return 1524
    elif width * height <= 1920 * 1080:
        return 3367
    else:
        raise ValueError(f"Invalid width: {width}, height: {height}")
