//! 実 Sora を使ったメディアループバック検証。
//!
//! 送信側と受信側の 2 接続を同一チャネルに張り、Sink と Transformer の
//! 経路にフレームが実際に流れることを確認する。

use std::sync::{
    atomic::{AtomicI32, AtomicU64, AtomicUsize, Ordering},
    Arc, Mutex,
};
use std::time::Duration;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use shiguredo_webrtc::{
    convert_from_i420, AdaptedVideoTrackSource, AudioTrackSink, AudioTrackSinkHandler,
    FrameTransformerHandler, I420Buffer, LibyuvFourcc, RtpTransceiver, TransformableFrame,
    VideoFrame, VideoFrameRef, VideoSink, VideoSinkHandler, VideoSinkWants,
};
use sora_sdk::{
    AdmConfig, JsonString, Role, SoraConnection, SoraConnectionContext,
    SoraConnectionContextConfig, SoraConnectionEventHandler,
};

// 入力値の上限。Python 側からの不正な入力で過剰な確保や長時間実行が起きないようにする。
// シグナリング URL の最大件数。
const MAX_SIGNALING_URLS: usize = 16;
// シグナリング URL 1 件の最大文字数。
const MAX_SIGNALING_URL_LEN: usize = 2048;
// チャネル ID の最大文字数。
const MAX_CHANNEL_ID_LEN: usize = 1024;
// メタデータ JSON 文字列の最大文字数。
const MAX_METADATA_LEN: usize = 16384;
// 接続維持時間の最大秒数。
const MAX_DURATION_SECS: f64 = 3600.0;
// 検証用映像の寸法。
const VIDEO_WIDTH: i32 = 320;
const VIDEO_HEIGHT: i32 = 240;
// 検証用映像の投入間隔。
const VIDEO_PUSH_INTERVAL: Duration = Duration::from_millis(33);

/// 検証済みの引数一式。
pub(crate) struct ValidatedArgs {
    /// シグナリング URL 群。
    pub signaling_urls: Vec<String>,
    /// チャネル ID。
    pub channel_id: String,
    /// メタデータ JSON。
    pub metadata: Option<JsonString>,
    /// 接続維持秒数。
    pub duration_secs: f64,
}

/// ロール以外の引数を検証する。ロールは呼び出し側で固定するため含めない。
pub(crate) fn validate_base_args(
    signaling_urls: Vec<String>,
    channel_id: String,
    metadata: Option<String>,
    duration_secs: f64,
) -> PyResult<ValidatedArgs> {
    if signaling_urls.is_empty() {
        return Err(PyValueError::new_err(
            "signaling_urls must contain at least 1 URL, got 0",
        ));
    }
    if signaling_urls.len() > MAX_SIGNALING_URLS {
        return Err(PyValueError::new_err(format!(
            "signaling_urls must contain at least 1 URL and at most {MAX_SIGNALING_URLS} URLs, got {}",
            signaling_urls.len()
        )));
    }
    for url in &signaling_urls {
        if url.len() > MAX_SIGNALING_URL_LEN {
            return Err(PyValueError::new_err(format!(
                "signaling URL must be at most {MAX_SIGNALING_URL_LEN} characters, got {}",
                url.len()
            )));
        }
    }
    if channel_id.is_empty() {
        return Err(PyValueError::new_err("channel_id must not be empty"));
    }
    if channel_id.len() > MAX_CHANNEL_ID_LEN {
        return Err(PyValueError::new_err(format!(
            "channel_id must be at most {MAX_CHANNEL_ID_LEN} characters, got {}",
            channel_id.len()
        )));
    }
    let metadata = metadata
        .map(|metadata| {
            if metadata.len() > MAX_METADATA_LEN {
                return Err(PyValueError::new_err(format!(
                    "metadata must be at most {MAX_METADATA_LEN} characters, got {}",
                    metadata.len()
                )));
            }
            metadata
                .parse()
                .map_err(|e| PyValueError::new_err(format!("invalid metadata JSON: {e}")))
        })
        .transpose()?;
    if !duration_secs.is_finite() || duration_secs <= 0.0 || duration_secs > MAX_DURATION_SECS {
        return Err(PyValueError::new_err(format!(
            "duration_secs must be within (0, {MAX_DURATION_SECS}], got {duration_secs}"
        )));
    }
    Ok(ValidatedArgs {
        signaling_urls,
        channel_id,
        metadata,
        duration_secs,
    })
}

/// イベントを破棄する空のハンドラ。
///
/// プロトタイプではコールバックを Python に中継しないため、
/// トレイトのデフォルト空実装をそのまま使う。
pub(crate) struct DiscardingEventHandler;

impl SoraConnectionEventHandler for DiscardingEventHandler {}

/// 音声受信の計数器。
#[derive(Debug, Default)]
struct AudioCounter {
    /// on_data 呼び出し回数。
    frames: AtomicU64,
    /// 受信バイト数合計。
    bytes: AtomicU64,
    /// 最後に観測したサンプルレート。
    sample_rate: AtomicI32,
    /// 最後に観測したチャンネル数。
    channels: AtomicUsize,
}

/// Sink に渡す共有所有版。
struct SharedAudioCounter(Arc<AudioCounter>);

impl AudioTrackSinkHandler for SharedAudioCounter {
    fn on_data(
        &mut self,
        audio_data: &[u8],
        _bits_per_sample: i32,
        sample_rate: i32,
        number_of_channels: usize,
        _number_of_frames: usize,
    ) {
        // 受信スレッド上で呼ばれるため Python には触れず計数だけする。
        self.0.frames.fetch_add(1, Ordering::Relaxed);
        self.0
            .bytes
            .fetch_add(audio_data.len() as u64, Ordering::Relaxed);
        self.0.sample_rate.store(sample_rate, Ordering::Relaxed);
        self.0.channels.store(number_of_channels, Ordering::Relaxed);
    }
}

/// 映像受信の計数器。
#[derive(Debug, Default)]
struct VideoState {
    /// on_frame 呼び出し回数。
    frames: AtomicU64,
    /// 最初に観測した幅。
    width: AtomicI32,
    /// 最初に観測した高さ。
    height: AtomicI32,
    /// 最初に変換した ARGB フレーム。
    argb: Mutex<Option<Vec<u8>>>,
}

/// Sink に渡す共有所有版。
struct SharedVideoCounter(Arc<VideoState>);

impl VideoSinkHandler for SharedVideoCounter {
    fn on_frame(&mut self, frame: VideoFrameRef<'_>) {
        // デコーダースレッド上で呼ばれるため Python には触れず計数だけする。
        if self.0.frames.fetch_add(1, Ordering::Relaxed) > 0 {
            return;
        }
        // 最初のフレームだけ寸法と ARGB 変換を記録する。
        let width = frame.width();
        let height = frame.height();
        self.0.width.store(width, Ordering::Relaxed);
        self.0.height.store(height, Ordering::Relaxed);
        let mut buffer = frame.buffer();
        let Some(i420) = buffer.to_i420() else {
            return;
        };
        let mut argb = vec![0u8; width as usize * height as usize * 4];
        let converted = convert_from_i420(
            i420.y_data(),
            i420.stride_y(),
            i420.u_data(),
            i420.stride_u(),
            i420.v_data(),
            i420.stride_v(),
            &mut argb,
            width * 4,
            width,
            height,
            LibyuvFourcc::Argb,
        );
        if converted {
            *self.0.argb.lock().expect("video state lock poisoned") = Some(argb);
        }
    }
}

/// 通過させるだけの計数トランスフォーマー。
struct CountingTransformer {
    /// transform 呼び出し回数。
    count: Arc<AtomicU64>,
}

impl FrameTransformerHandler for CountingTransformer {
    fn transform(&self, frame: TransformableFrame) -> Option<TransformableFrame> {
        // エンコーダー / ネットワークスレッド上で呼ばれるため Python には触れない。
        // 加工せず通過させ、呼び出し回数だけ数える。
        self.count.fetch_add(1, Ordering::Relaxed);
        Some(frame)
    }
}

/// 受信側のイベントハンドラ。トラック種別ごとに対応する Sink を付ける。
struct LoopbackReceiver {
    /// 音声計数器。
    audio: Arc<AudioCounter>,
    /// 映像計数器。
    video: Arc<VideoState>,
    /// 判別不能トラック数。
    unknown_tracks: Arc<AtomicU64>,
    /// Sink は登録解除まで保持する (C++ 側は所有しないため)。
    audio_sinks: Vec<AudioTrackSink>,
    /// Sink は登録解除まで保持する (C++ 側は所有しないため)。
    video_sinks: Vec<VideoSink>,
}

impl SoraConnectionEventHandler for LoopbackReceiver {
    fn on_track(&mut self, transceiver: RtpTransceiver) {
        // sora_sdk のイベントタスク上で直列に呼ばれる。
        let track = transceiver.receiver().track();
        let kind = track.kind().unwrap_or_default();
        if kind == "audio" {
            let sink =
                AudioTrackSink::new_with_handler(Box::new(SharedAudioCounter(self.audio.clone())));
            track.cast_to_audio_track().add_sink(&sink);
            self.audio_sinks.push(sink);
        } else if kind == "video" {
            let sink =
                VideoSink::new_with_handler(Box::new(SharedVideoCounter(self.video.clone())));
            track
                .cast_to_video_track()
                .add_or_update_sink(&sink, &VideoSinkWants::new());
            self.video_sinks.push(sink);
        } else {
            self.unknown_tracks.fetch_add(1, Ordering::Relaxed);
        }
    }
}

/// 音声ループバックの結果。
pub(crate) struct AudioFlow {
    /// 受信 on_data 回数。
    pub frames: u64,
    /// 受信バイト数合計。
    pub bytes: u64,
    /// 観測したサンプルレート。
    pub sample_rate: i32,
    /// 観測したチャンネル数。
    pub channels: usize,
    /// 判別不能トラック数。
    pub unknown_tracks: u64,
}

/// 送信側 (音声) と受信側を同一チャネルに接続し、PCM 受信を数える。
///
/// microphone が真の場合は実マイクを使う。偽の場合は既定の無音構成になる。
pub(crate) async fn loopback_audio(args: ValidatedArgs, microphone: bool) -> PyResult<AudioFlow> {
    let context = if microphone {
        // 実マイクを使う構成にする。
        let config = SoraConnectionContextConfig {
            adm_config: AdmConfig::UseBuiltIn,
            ..Default::default()
        };
        SoraConnectionContext::new_with_config(config).map_err(|e| {
            PyRuntimeError::new_err(format!("failed to create connection context: {e}"))
        })?
    } else {
        SoraConnectionContext::new().map_err(|e| {
            PyRuntimeError::new_err(format!("failed to create connection context: {e}"))
        })?
    };
    let audio_source = context
        .create_audio_source()
        .map_err(|e| PyRuntimeError::new_err(format!("failed to create audio source: {e}")))?;
    let audio_track = context
        .create_audio_track(&audio_source)
        .map_err(|e| PyRuntimeError::new_err(format!("failed to create audio track: {e}")))?;
    let counter = Arc::new(AudioCounter::default());
    let unknown_tracks = Arc::new(AtomicU64::default());
    let mut sender_builder = SoraConnection::builder(
        context.clone(),
        args.signaling_urls.clone(),
        args.channel_id.clone(),
        Role::SendOnly,
        DiscardingEventHandler,
    )
    .sender_audio_track(audio_track);
    if let Some(metadata) = args.metadata.clone() {
        sender_builder = sender_builder.metadata(metadata);
    }
    let (sender, sender_handle) = sender_builder
        .build()
        .map_err(|e| PyRuntimeError::new_err(format!("failed to build sender connection: {e}")))?;
    let receiver_events = LoopbackReceiver {
        audio: counter.clone(),
        video: Arc::new(VideoState::default()),
        unknown_tracks: unknown_tracks.clone(),
        audio_sinks: Vec::new(),
        video_sinks: Vec::new(),
    };
    let mut receiver_builder = SoraConnection::builder(
        context,
        args.signaling_urls,
        args.channel_id,
        Role::RecvOnly,
        receiver_events,
    );
    if let Some(metadata) = args.metadata {
        receiver_builder = receiver_builder.metadata(metadata);
    }
    let (receiver, receiver_handle) = receiver_builder.build().map_err(|e| {
        PyRuntimeError::new_err(format!("failed to build receiver connection: {e}"))
    })?;
    let sender_task = tokio::spawn(async move { sender.run().await });
    let receiver_task = tokio::spawn(async move { receiver.run().await });
    tokio::time::sleep(Duration::from_secs_f64(args.duration_secs)).await;
    let _ = sender_handle.disconnect().await;
    let _ = receiver_handle.disconnect().await;
    join_connection(sender_task, "sender").await?;
    join_connection(receiver_task, "receiver").await?;
    Ok(AudioFlow {
        frames: counter.frames.load(Ordering::Relaxed),
        bytes: counter.bytes.load(Ordering::Relaxed),
        sample_rate: counter.sample_rate.load(Ordering::Relaxed),
        channels: counter.channels.load(Ordering::Relaxed),
        unknown_tracks: unknown_tracks.load(Ordering::Relaxed),
    })
}

/// 映像ループバックの結果。
pub(crate) struct VideoFlow {
    /// 受信 on_frame 回数。
    pub received_frames: u64,
    /// 送信側 transform 回数。
    pub transformed_frames: u64,
    /// 判別不能トラック数。
    pub unknown_tracks: u64,
    /// 観測した幅。
    pub width: i32,
    /// 観測した高さ。
    pub height: i32,
    /// 最初に変換した ARGB フレーム。
    pub argb_frame: Vec<u8>,
}

/// 黒フレームを定期的に投入する。
async fn push_black_frames(source: AdaptedVideoTrackSource) {
    let mut buffer = I420Buffer::new(VIDEO_WIDTH, VIDEO_HEIGHT);
    {
        let (y, u, v) = buffer.planes_mut();
        y.fill(16);
        u.fill(128);
        v.fill(128);
    }
    let mut ticker = tokio::time::interval(VIDEO_PUSH_INTERVAL);
    let started = std::time::Instant::now();
    loop {
        ticker.tick().await;
        let mut builder = VideoFrame::builder(&buffer.cast_to_video_frame_buffer());
        builder.set_timestamp_us(started.elapsed().as_micros() as i64);
        source.on_frame(&builder.build());
    }
}

/// 送信側 (映像) と受信側を同一チャネルに接続し、受信と encoded 変換を数える。
pub(crate) async fn loopback_video(args: ValidatedArgs) -> PyResult<VideoFlow> {
    let context = SoraConnectionContext::new().map_err(|e| {
        PyRuntimeError::new_err(format!("failed to create connection context: {e}"))
    })?;
    let video_source = AdaptedVideoTrackSource::new();
    let video_track = context
        .create_video_track(&video_source.cast_to_video_track_source())
        .map_err(|e| PyRuntimeError::new_err(format!("failed to create video track: {e}")))?;
    let transformed = Arc::new(AtomicU64::default());
    let mut sender_builder = SoraConnection::builder(
        context.clone(),
        args.signaling_urls.clone(),
        args.channel_id.clone(),
        Role::SendOnly,
        DiscardingEventHandler,
    )
    .sender_video_track(video_track)
    .sender_video_transform(Box::new(CountingTransformer {
        count: transformed.clone(),
    }));
    if let Some(metadata) = args.metadata.clone() {
        sender_builder = sender_builder.metadata(metadata);
    }
    let (sender, sender_handle) = sender_builder
        .build()
        .map_err(|e| PyRuntimeError::new_err(format!("failed to build sender connection: {e}")))?;
    let video = Arc::new(VideoState::default());
    let unknown_tracks = Arc::new(AtomicU64::default());
    let receiver_events = LoopbackReceiver {
        audio: Arc::new(AudioCounter::default()),
        video: video.clone(),
        unknown_tracks: unknown_tracks.clone(),
        audio_sinks: Vec::new(),
        video_sinks: Vec::new(),
    };
    let mut receiver_builder = SoraConnection::builder(
        context,
        args.signaling_urls,
        args.channel_id,
        Role::RecvOnly,
        receiver_events,
    );
    if let Some(metadata) = args.metadata {
        receiver_builder = receiver_builder.metadata(metadata);
    }
    let (receiver, receiver_handle) = receiver_builder.build().map_err(|e| {
        PyRuntimeError::new_err(format!("failed to build receiver connection: {e}"))
    })?;
    let pusher = tokio::spawn(push_black_frames(video_source));
    let sender_task = tokio::spawn(async move { sender.run().await });
    let receiver_task = tokio::spawn(async move { receiver.run().await });
    tokio::time::sleep(Duration::from_secs_f64(args.duration_secs)).await;
    let _ = sender_handle.disconnect().await;
    let _ = receiver_handle.disconnect().await;
    pusher.abort();
    let _ = pusher.await;
    join_connection(sender_task, "sender").await?;
    join_connection(receiver_task, "receiver").await?;
    let argb_frame = video
        .argb
        .lock()
        .expect("video state lock poisoned")
        .clone()
        .unwrap_or_default();
    Ok(VideoFlow {
        received_frames: video.frames.load(Ordering::Relaxed),
        transformed_frames: transformed.load(Ordering::Relaxed),
        unknown_tracks: unknown_tracks.load(Ordering::Relaxed),
        width: video.width.load(Ordering::Relaxed),
        height: video.height.load(Ordering::Relaxed),
        argb_frame,
    })
}

/// 接続タスクの終了を待ち、失敗を例外に変える。
async fn join_connection(
    task: tokio::task::JoinHandle<sora_sdk::Result<()>>,
    name: &str,
) -> PyResult<()> {
    let result = task
        .await
        .map_err(|_| PyRuntimeError::new_err(format!("{name} task did not finish")))?;
    result.map_err(|e| PyRuntimeError::new_err(format!("{name} connection failed: {e}")))
}
