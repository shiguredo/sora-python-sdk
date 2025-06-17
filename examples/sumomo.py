#!/usr/bin/env python3
import argparse
import json
import logging
import signal
import threading
import time
from typing import Any, Optional

import cv2
import numpy as np

from sora_sdk import (
    Sora,
    SoraConnection,
    SoraMediaTrack,
    SoraSignalingErrorCode,
    SoraTrackState,
    SoraVideoFrame,
    SoraVideoSinkImpl,
    SoraLoggingSeverity,
    enable_libwebrtc_log,
)


class OpenCVRenderer:
    def __init__(self, window_width: int = 640, window_height: int = 480, fullscreen: bool = False):
        self.window_width = window_width
        self.window_height = window_height
        self.fullscreen = fullscreen
        self.tracks: dict[str, SoraVideoSinkImpl] = {}
        self.track_refs: dict[str, SoraMediaTrack] = {}
        self.frames: dict[str, Optional[np.ndarray]] = {}
        self.last_frame_time: dict[str, float] = {}
        self.lock = threading.Lock()
        self.running = True
        self.window_name = "Sumomo (Python)"
        
    def start(self):
        # Initialize window on main thread
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        if self.fullscreen:
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        
    def stop(self):
        self.running = False
        cv2.destroyAllWindows()
        
    def add_track(self, track: SoraMediaTrack):
        with self.lock:
            if track.id not in self.tracks:
                logging.info(f"Adding track: {track.id}")
                sink = SoraVideoSinkImpl(track)
                self.tracks[track.id] = sink
                self.track_refs[track.id] = track
                self.frames[track.id] = None
                
                def on_frame(frame: SoraVideoFrame):
                    data = frame.data()
                    with self.lock:
                        self.frames[track.id] = np.array(data, copy=True)
                        self.last_frame_time[track.id] = time.time()
                        
                sink.on_frame = on_frame
                
    def remove_track(self, track_id: str):
        with self.lock:
            if track_id in self.tracks:
                del self.tracks[track_id]
                del self.track_refs[track_id]
                del self.frames[track_id]
                if track_id in self.last_frame_time:
                    del self.last_frame_time[track_id]
                
    def render_frame(self):
        """Called from main thread to render frames"""
        current_time = time.time()
        
        # Check for ended tracks or tracks that haven't received frames for a while
        with self.lock:
            ended_tracks = []
            for track_id, track in list(self.track_refs.items()):
                # Check if track ended
                if track.state == SoraTrackState.ENDED:
                    ended_tracks.append(track_id)
                # Check if no frames received for 5 seconds
                elif track_id in self.last_frame_time:
                    if current_time - self.last_frame_time[track_id] > 5.0:
                        logging.info(f"Track {track_id} timed out (no frames for 5 seconds)")
                        ended_tracks.append(track_id)
            
            # Remove ended tracks
            for track_id in ended_tracks:
                if track_id in self.tracks:
                    logging.info(f"Removing track: {track_id}")
                    del self.tracks[track_id]
                    del self.track_refs[track_id]
                    del self.frames[track_id]
                    if track_id in self.last_frame_time:
                        del self.last_frame_time[track_id]
                
            frames_to_render = [(track_id, frame.copy() if frame is not None else None) 
                                for track_id, frame in self.frames.items()]
                                
        if not frames_to_render:
            return
            
        # Calculate grid layout
        num_videos = len([f for _, f in frames_to_render if f is not None])
        if num_videos == 0:
            return
            
        # Determine optimal grid layout
        if num_videos == 1:
            cols, rows = 1, 1
        elif num_videos == 2:
            cols, rows = 2, 1
        elif num_videos <= 4:
            cols, rows = 2, 2
        elif num_videos <= 6:
            cols, rows = 3, 2
        elif num_videos <= 9:
            cols, rows = 3, 3
        elif num_videos <= 12:
            cols, rows = 4, 3
        else:
            cols = int(np.ceil(np.sqrt(num_videos)))
            rows = int(np.ceil(num_videos / cols))
        
        cell_width = self.window_width // cols
        cell_height = self.window_height // rows
        
        # Create canvas
        canvas = np.zeros((self.window_height, self.window_width, 3), dtype=np.uint8)
        
        valid_idx = 0
        for _, frame in frames_to_render:
            if frame is None:
                continue
                
            row = valid_idx // cols
            col = valid_idx % cols
            
            # Calculate cell position
            cell_x = col * cell_width
            cell_y = row * cell_height
            
            # Get frame dimensions
            frame_h, frame_w = frame.shape[:2]
            frame_aspect = frame_w / frame_h
            cell_aspect = cell_width / cell_height
            
            # Calculate scaled dimensions maintaining aspect ratio
            if frame_aspect > cell_aspect:
                # Frame is wider than cell
                scaled_width = cell_width
                scaled_height = int(cell_width / frame_aspect)
            else:
                # Frame is taller than cell
                scaled_height = cell_height
                scaled_width = int(cell_height * frame_aspect)
            
            # Center the frame in the cell
            x_offset = (cell_width - scaled_width) // 2
            y_offset = (cell_height - scaled_height) // 2
            
            # Resize frame maintaining aspect ratio
            resized = cv2.resize(frame, (scaled_width, scaled_height))
            
            # Place resized frame in the center of the cell
            x_start = cell_x + x_offset
            y_start = cell_y + y_offset
            x_end = x_start + scaled_width
            y_end = y_start + scaled_height
            
            canvas[y_start:y_end, x_start:x_end] = resized
            
            # Draw border around cell (optional)
            cv2.rectangle(canvas, (cell_x, cell_y), (cell_x + cell_width - 1, cell_y + cell_height - 1), (50, 50, 50), 1)
            
            valid_idx += 1
            
        # Display
        cv2.imshow(self.window_name, canvas)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            self.running = False
                

class Sumomo:
    def __init__(self, sora: Sora, config: dict[str, Any]):
        self.sora = sora
        self.config = config
        self.conn: Optional[SoraConnection] = None
        self.renderer: Optional[OpenCVRenderer] = None
        self._shutting_down = False
        
    def run(self):
        # Setup renderer if requested
        if self.config.get("use_opencv", False):
            self.renderer = OpenCVRenderer(
                window_width=self.config.get("window_width", 640),
                window_height=self.config.get("window_height", 480),
                fullscreen=self.config.get("fullscreen", False)
            )
            self.renderer.start()
            
        # Create connection
        conn_config = {
            "signaling_urls": [self.config["signaling_url"]],
            "channel_id": self.config["channel_id"],
            "role": self.config["role"],
        }
        
        # Optional parameters
        if self.config.get("client_id"):
            conn_config["client_id"] = self.config["client_id"]
        if self.config.get("video") is not None:
            conn_config["video"] = self.config["video"]
        if self.config.get("audio") is not None:
            conn_config["audio"] = self.config["audio"]
        if self.config.get("video_codec_type"):
            conn_config["video_codec_type"] = self.config["video_codec_type"]
        if self.config.get("audio_codec_type"):
            conn_config["audio_codec_type"] = self.config["audio_codec_type"]
        if self.config.get("video_bit_rate"):
            conn_config["video_bit_rate"] = self.config["video_bit_rate"]
        if self.config.get("audio_bit_rate"):
            conn_config["audio_bit_rate"] = self.config["audio_bit_rate"]
        if self.config.get("video_h264_params"):
            conn_config["video_h264_params"] = self.config["video_h264_params"]
        if self.config.get("video_h265_params"):
            conn_config["video_h264_params"] = self.config["video_h265_params"]
        if self.config.get("metadata"):
            conn_config["metadata"] = self.config["metadata"]
        if self.config.get("multistream") is not None:
            conn_config["simulcast"] = self.config["multistream"]
        if self.config.get("spotlight") is not None:
            conn_config["spotlight"] = self.config["spotlight"]
        if self.config.get("spotlight_number"):
            conn_config["spotlight_number"] = self.config["spotlight_number"]
        if self.config.get("simulcast") is not None:
            conn_config["simulcast"] = self.config["simulcast"]
        if self.config.get("data_channel_signaling") is not None:
            conn_config["data_channel_signaling"] = self.config["data_channel_signaling"]
        if self.config.get("ignore_disconnect_websocket") is not None:
            conn_config["ignore_disconnect_websocket"] = self.config["ignore_disconnect_websocket"]
        if self.config.get("proxy_url"):
            conn_config["proxy_url"] = self.config["proxy_url"]
        if self.config.get("proxy_username"):
            conn_config["proxy_username"] = self.config["proxy_username"]
        if self.config.get("proxy_password"):
            conn_config["proxy_password"] = self.config["proxy_password"]
        if self.config.get("insecure"):
            conn_config["insecure"] = self.config["insecure"]
        if self.config.get("client_cert"):
            with open(self.config["client_cert"], "rb") as f:
                conn_config["client_cert"] = f.read()
        if self.config.get("client_key"):
            with open(self.config["client_key"], "rb") as f:
                conn_config["client_key"] = f.read()
        if self.config.get("ca_cert"):
            with open(self.config["ca_cert"], "rb") as f:
                conn_config["ca_cert"] = f.read()
        if self.config.get("degradation_preference"):
            conn_config["degradation_preference"] = self.config["degradation_preference"]
            
        # Create audio/video sources for sendonly/sendrecv
        if self.config["role"] != "recvonly":
            # Audio source
            audio_source = self.sora.create_audio_source(
                channels=1,
                sample_rate=48000
            )
            conn_config["audio_source"] = audio_source
            
            # Video source
            video_source = self.sora.create_video_source()
            conn_config["video_source"] = video_source
            
            # Start dummy video capture
            self._start_video_capture(video_source)
            
        self.conn = self.sora.create_connection(**conn_config)
        
        # Set callbacks
        self.conn.on_set_offer = self._on_set_offer
        self.conn.on_disconnect = self._on_disconnect
        self.conn.on_notify = self._on_notify
        self.conn.on_push = self._on_push
        self.conn.on_message = self._on_message
        self.conn.on_track = self._on_track
        self.conn.on_data_channel = self._on_data_channel
        
        # Connect
        self.conn.connect()
        
        # Wait for signal
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        try:
            while not self._shutting_down:
                if self.renderer:
                    self.renderer.render_frame()
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            pass
            
        # Cleanup
        if self.conn:
            self.conn.disconnect()
        if self.renderer:
            self.renderer.stop()
            
    def _signal_handler(self, _signum, _frame):
        self._shutting_down = True
        
    def _start_video_capture(self, video_source):
        """Generate dummy video frames"""
        def capture_loop():
            width, height = self._get_resolution()
            frame_count = 0
            
            while not self._shutting_down:
                # Generate test pattern
                frame = np.zeros((height, width, 3), dtype=np.uint8)
                
                # Simple color pattern
                frame[:, :] = [(frame_count % 255), 128, 128]
                
                # Add text
                text = f"Frame: {frame_count}"
                cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                
                video_source.on_captured(frame)
                
                frame_count += 1
                time.sleep(1.0 / 30.0)  # 30fps
                
        thread = threading.Thread(target=capture_loop)
        thread.daemon = True
        thread.start()
        
    def _get_resolution(self) -> tuple[int, int]:
        resolution = self.config.get("resolution", "VGA")
        
        if resolution == "QVGA":
            return (320, 240)
        elif resolution == "VGA":
            return (640, 480)
        elif resolution == "HD":
            return (1280, 720)
        elif resolution == "FHD":
            return (1920, 1080)
        elif resolution == "4K":
            return (3840, 2160)
        else:
            # Parse WIDTHxHEIGHT format
            if "x" in resolution:
                parts = resolution.split("x")
                try:
                    width = int(parts[0])
                    height = int(parts[1])
                    return (max(16, width), max(16, height))
                except ValueError:
                    pass
        
        return (640, 480)  # Default to VGA
        
    def _on_set_offer(self, _offer: str):
        logging.info("on_set_offer")
        
    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str):
        logging.info(f"on_disconnect: {error_code} {message}")
        self._shutting_down = True
        
    def _on_notify(self, message: str):
        logging.info(f"on_notify: {message}")
        
    def _on_push(self, message: str):
        logging.info(f"on_push: {message}")
        
    def _on_message(self, label: str, data: bytes):
        logging.info(f"on_message: label={label}, data_len={len(data)}")
        
    def _on_track(self, track: SoraMediaTrack):
        logging.info(f"on_track: {track.id}")
        if self.renderer and track.kind == "video":
            self.renderer.add_track(track)
            
    def _on_data_channel(self, label: str):
        logging.info(f"on_data_channel: {label}")


def add_optional_bool(parser: argparse.ArgumentParser, name: str, help_text: str):
    """Add optional boolean argument that accepts true/false/none"""
    def parse_optional_bool(value: str) -> Optional[bool]:
        if value.lower() == "true":
            return True
        elif value.lower() == "false":
            return False
        elif value.lower() == "none":
            return None
        else:
            raise argparse.ArgumentTypeError(f"Invalid value for optional bool: {value}")
            
    parser.add_argument(name, type=parse_optional_bool, help=help_text, 
                        choices=["true", "false", "none"])


def main():
    parser = argparse.ArgumentParser(description="Sumomo Sample for Sora Python SDK")
    
    # Logging
    parser.add_argument("--log-level", type=str, default="error",
                        choices=["verbose", "info", "warning", "error", "none"],
                        help="Log severity level threshold")
    
    # Video settings
    parser.add_argument("--resolution", type=str, default="VGA",
                        help="Video resolution (QVGA, VGA, HD, FHD, 4K, or WIDTHxHEIGHT)")
    
    # Sora settings
    parser.add_argument("--signaling-url", type=str, required=True,
                        help="Signaling URL")
    parser.add_argument("--channel-id", type=str, required=True,
                        help="Channel ID")
    parser.add_argument("--role", type=str, required=True,
                        choices=["sendonly", "recvonly", "sendrecv"],
                        help="Role")
    parser.add_argument("--client-id", type=str, help="Client ID")
    parser.add_argument("--video", type=bool, default=True, help="Send video to sora")
    parser.add_argument("--audio", type=bool, default=True, help="Send audio to sora")
    parser.add_argument("--video-codec-type", type=str,
                        choices=["", "VP8", "VP9", "AV1", "H264", "H265"],
                        help="Video codec for send")
    parser.add_argument("--audio-codec-type", type=str,
                        choices=["", "OPUS"],
                        help="Audio codec for send")
    parser.add_argument("--video-bit-rate", type=int, help="Video bit rate")
    parser.add_argument("--audio-bit-rate", type=int, help="Audio bit rate")
    parser.add_argument("--video-h264-params", type=str, help="H.264 parameters (JSON)")
    parser.add_argument("--video-h265-params", type=str, help="H.265 parameters (JSON)")
    parser.add_argument("--metadata", type=str, help="Signaling metadata (JSON)")
    
    add_optional_bool(parser, "--multistream", "Use multistream")
    add_optional_bool(parser, "--spotlight", "Use spotlight")
    parser.add_argument("--spotlight-number", type=int, help="Spotlight number")
    add_optional_bool(parser, "--simulcast", "Use simulcast")
    add_optional_bool(parser, "--data-channel-signaling", "Use DataChannel signaling")
    add_optional_bool(parser, "--ignore-disconnect-websocket", 
                       "Ignore WebSocket disconnection")
    
    # Proxy settings
    parser.add_argument("--proxy-url", type=str, help="Proxy URL")
    parser.add_argument("--proxy-username", type=str, help="Proxy username")
    parser.add_argument("--proxy-password", type=str, help="Proxy password")
    
    # OpenCV settings (replacing SDL)
    parser.add_argument("--use-opencv", action="store_true", 
                        help="Show video using OpenCV")
    parser.add_argument("--window-width", type=int, default=640,
                        help="Window width")
    parser.add_argument("--window-height", type=int, default=480,
                        help="Window height")
    parser.add_argument("--fullscreen", action="store_true",
                        help="Use fullscreen window")
    parser.add_argument("--show-me", action="store_true",
                        help="Show self video (not implemented)")
    
    # Certificate settings
    parser.add_argument("--insecure", action="store_true",
                        help="Allow insecure connection")
    parser.add_argument("--client-cert", type=str, help="Client certificate file")
    parser.add_argument("--client-key", type=str, help="Client key file")
    parser.add_argument("--ca-cert", type=str, help="CA certificate file")
    
    args = parser.parse_args()
    
    # Setup logging
    log_levels = {
        "verbose": SoraLoggingSeverity.VERBOSE,
        "info": SoraLoggingSeverity.INFO,
        "warning": SoraLoggingSeverity.WARNING,
        "error": SoraLoggingSeverity.ERROR,
        "none": SoraLoggingSeverity.NONE,
    }
    
    if args.log_level != "none":
        enable_libwebrtc_log(log_levels[args.log_level])
        logging.basicConfig(
            level=getattr(logging, args.log_level.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    else:
        # Disable WebRTC logs completely when log level is none
        enable_libwebrtc_log(SoraLoggingSeverity.NONE)
    
    # Build config
    config = vars(args)
    
    # Parse JSON parameters
    if args.video_h264_params:
        config["video_h264_params"] = json.loads(args.video_h264_params)
    if args.video_h265_params:
        config["video_h265_params"] = json.loads(args.video_h265_params)
    if args.metadata:
        config["metadata"] = json.loads(args.metadata)
        
    # Create Sora instance
    sora = Sora()
    
    # Run sumomo
    sumomo = Sumomo(sora, config)
    sumomo.run()


if __name__ == "__main__":
    main()