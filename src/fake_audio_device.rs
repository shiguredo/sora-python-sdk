//! 送受信駆動用の偽オーディオデバイス。
//!
//! 既定の Dummy ADM では再生ループがなく音声引き抜きが止まるため、
//! 10ms 周期で再生要求を出す偽デバイスでミキサーを駆動する。
//! 録音側も同じ周期で取り込み要求を出し、送信 PCM の投入口になる。

use std::collections::VecDeque;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::time::Duration;

use shiguredo_webrtc::{
    AudioDeviceModule, AudioDeviceModuleHandler, AudioParameters, AudioTransportRef,
};

// 再生要求の形式。エンジン側の書き込みが要求を上回らないよう、
// 余裕を持ってステレオで要求する。受信引き抜きの駆動だけが目的のため
// 内容は使わない。
// 再生サンプルレート (Hz)。
const PLAY_SAMPLE_RATE: u32 = 48000;
// 再生チャンネル数。
const PLAY_CHANNELS: usize = 2;
// 10ms あたりのサンプル数。
const PLAY_SAMPLES_10MS: usize = 480;

// 送信キューの上限 (秒数)。Python 側の投入過多で記憶域が膨らまないようにする。
const SEND_QUEUE_LIMIT_SECS: usize = 10;

/// 取り込み形式。
struct CaptureConfig {
    /// チャンネル数。
    channels: usize,
    /// サンプルレート (Hz)。
    sample_rate: u32,
}

/// 送受信ポンプの共有状態。
pub(crate) struct AudioPumpState {
    /// 登録された転送路。
    transport: Mutex<Option<AudioTransportRef>>,
    /// 取り込み形式。音声送信元が登録する。
    capture: Mutex<Option<CaptureConfig>>,
    /// 送信待ちのインタリーブ PCM。
    send_queue: Mutex<VecDeque<i16>>,
    /// 初期化済みか。
    initialized: AtomicBool,
    /// 録音初期化済みか。
    recording_initialized: AtomicBool,
    /// 再生初期化済みか。
    playout_initialized: AtomicBool,
    /// 再生中か。
    playing: AtomicBool,
    /// 録音中か。
    recording: AtomicBool,
    /// 駆動スレッド。
    pump: Mutex<Option<std::thread::JoinHandle<()>>>,
}

impl AudioPumpState {
    /// 共有状態を作る。
    pub(crate) fn new() -> Self {
        Self {
            transport: Mutex::new(None),
            capture: Mutex::new(None),
            send_queue: Mutex::new(VecDeque::new()),
            initialized: AtomicBool::new(false),
            recording_initialized: AtomicBool::new(false),
            playout_initialized: AtomicBool::new(false),
            playing: AtomicBool::new(false),
            recording: AtomicBool::new(false),
            pump: Mutex::new(None),
        }
    }

    /// 取り込み形式を登録する。
    pub(crate) fn set_capture(&self, channels: usize, sample_rate: u32) {
        *self.capture.lock().expect("audio device lock poisoned") = Some(CaptureConfig {
            channels,
            sample_rate,
        });
    }

    /// 送信 PCM を積む。上限を超えた古い分は捨てる。
    pub(crate) fn push_send(&self, samples: &[i16], channels: usize, sample_rate: u32) {
        let mut queue = self.send_queue.lock().expect("audio device lock poisoned");
        queue.extend(samples.iter().copied());
        // 上限は取り込み形式ではなく投入側の形式で数える。
        let limit = sample_rate as usize * channels * SEND_QUEUE_LIMIT_SECS;
        while queue.len() > limit {
            queue.pop_front();
        }
    }
}

/// 再生要求と取り込み要求を出し続けて送受信を駆動する。
fn pump(state: Arc<AudioPumpState>) {
    let mut play_buffer = vec![0u8; PLAY_SAMPLES_10MS * 2 * PLAY_CHANNELS];
    while state.playing.load(Ordering::Relaxed) || state.recording.load(Ordering::Relaxed) {
        let tick = std::time::Instant::now();
        let transport = *state.transport.lock().expect("audio device lock poisoned");
        if let Some(transport) = transport {
            if state.playing.load(Ordering::Relaxed) {
                // 取得データは破棄する。受信引き抜きの駆動が目的。
                let mut samples_out = 0usize;
                let mut elapsed_time_ms = 0i64;
                let mut ntp_time_ms = 0i64;
                unsafe {
                    transport.need_more_play_data(
                        PLAY_SAMPLES_10MS,
                        2,
                        PLAY_CHANNELS,
                        PLAY_SAMPLE_RATE,
                        play_buffer.as_mut_ptr(),
                        &mut samples_out,
                        &mut elapsed_time_ms,
                        &mut ntp_time_ms,
                    );
                }
            }
            if state.recording.load(Ordering::Relaxed) {
                push_capture(&state, &transport);
            }
        }
        let elapsed = tick.elapsed();
        if elapsed < Duration::from_millis(10) {
            std::thread::sleep(Duration::from_millis(10) - elapsed);
        }
    }
}

/// 10ms 分の送信 PCM を取り込み要求で渡す。不足分は無音で埋める。
fn push_capture(state: &AudioPumpState, transport: &AudioTransportRef) {
    let (channels, sample_rate) = {
        let capture = state.capture.lock().expect("audio device lock poisoned");
        match capture.as_ref() {
            Some(config) => (config.channels, config.sample_rate),
            None => return,
        }
    };
    // 10ms 分のサンプル数。
    let frames_10ms = sample_rate as usize / 100;
    let mut chunk = vec![0i16; frames_10ms * channels];
    {
        let mut queue = state.send_queue.lock().expect("audio device lock poisoned");
        let take = queue.len().min(chunk.len());
        for (out, sample) in chunk.iter_mut().zip(queue.drain(..take)) {
            *out = sample;
        }
    }
    let mut new_mic_level = 0u32;
    unsafe {
        transport.recorded_data_is_available(
            chunk.as_ptr() as *const u8,
            frames_10ms,
            2,
            channels,
            sample_rate,
            0,
            0,
            0,
            false,
            &mut new_mic_level,
            None,
        );
    }
}

/// 送受信ループでミキサーを駆動する偽 ADM ハンドラ。
pub(crate) struct FakeAudioDevice {
    /// 共有状態。
    state: Arc<AudioPumpState>,
}

impl FakeAudioDevice {
    /// 共有状態を指定して作る。
    pub(crate) fn with_state(state: Arc<AudioPumpState>) -> Self {
        Self { state }
    }

    /// webrtc のデバイスモジュールに変える。
    pub(crate) fn into_device_module(self) -> AudioDeviceModule {
        AudioDeviceModule::new_with_handler(Box::new(self))
    }

    /// 駆動スレッドが必要なら起こす。
    fn ensure_pump(&self) {
        if !self.state.playing.load(Ordering::Relaxed)
            && !self.state.recording.load(Ordering::Relaxed)
        {
            return;
        }
        let mut handle = self.state.pump.lock().expect("audio device lock poisoned");
        if handle.is_none() {
            let state = self.state.clone();
            *handle = std::thread::Builder::new()
                .name("fake-audio-pump".to_string())
                .spawn(move || pump(state))
                .ok();
        }
    }

    /// 駆動が不要になればスレッドを畳む。
    fn maybe_stop_pump(&self) {
        if self.state.playing.load(Ordering::Relaxed)
            || self.state.recording.load(Ordering::Relaxed)
        {
            return;
        }
        if let Some(handle) = self
            .state
            .pump
            .lock()
            .expect("audio device lock poisoned")
            .take()
        {
            let _ = handle.join();
        }
    }
}

impl AudioDeviceModuleHandler for FakeAudioDevice {
    fn register_audio_callback(&self, audio_transport: Option<AudioTransportRef>) -> i32 {
        *self
            .state
            .transport
            .lock()
            .expect("audio device lock poisoned") = audio_transport;
        0
    }

    fn init(&self) -> i32 {
        self.state.initialized.store(true, Ordering::Relaxed);
        0
    }

    fn terminate(&self) -> i32 {
        self.state.initialized.store(false, Ordering::Relaxed);
        0
    }

    fn initialized(&self) -> bool {
        self.state.initialized.load(Ordering::Relaxed)
    }

    fn recording_devices(&self) -> i16 {
        1
    }

    fn recording_device_name(&self, index: u16) -> Option<(String, String)> {
        (index == 0).then(|| ("Fake Microphone".to_string(), "fake-microphone".to_string()))
    }

    fn playout_devices(&self) -> i16 {
        1
    }

    fn playout_device_name(&self, index: u16) -> Option<(String, String)> {
        (index == 0).then(|| ("Fake Speaker".to_string(), "fake-speaker".to_string()))
    }

    fn set_recording_device(&self, _index: u16) -> i32 {
        0
    }

    fn set_playout_device(&self, _index: u16) -> i32 {
        0
    }

    fn recording_is_available(&self, available: &mut bool) -> i32 {
        *available = true;
        0
    }

    fn init_recording(&self) -> i32 {
        self.state
            .recording_initialized
            .store(true, Ordering::Relaxed);
        0
    }

    fn recording_is_initialized(&self) -> bool {
        self.state.recording_initialized.load(Ordering::Relaxed)
    }

    fn playout_is_available(&self, available: &mut bool) -> i32 {
        *available = true;
        0
    }

    fn init_playout(&self) -> i32 {
        self.state
            .playout_initialized
            .store(true, Ordering::Relaxed);
        0
    }

    fn playout_is_initialized(&self) -> bool {
        self.state.playout_initialized.load(Ordering::Relaxed)
    }

    fn start_playout(&self) -> i32 {
        self.state.playing.store(true, Ordering::Relaxed);
        self.ensure_pump();
        0
    }

    fn stop_playout(&self) -> i32 {
        self.state.playing.store(false, Ordering::Relaxed);
        self.maybe_stop_pump();
        0
    }

    fn playing(&self) -> bool {
        self.state.playing.load(Ordering::Relaxed)
    }

    fn start_recording(&self) -> i32 {
        self.state.recording.store(true, Ordering::Relaxed);
        self.ensure_pump();
        0
    }

    fn stop_recording(&self) -> i32 {
        self.state.recording.store(false, Ordering::Relaxed);
        self.maybe_stop_pump();
        0
    }

    fn recording(&self) -> bool {
        self.state.recording.load(Ordering::Relaxed)
    }

    fn get_record_audio_parameters(&self, params: &mut Option<AudioParameters>) -> i32 {
        let capture = self
            .state
            .capture
            .lock()
            .expect("audio device lock poisoned");
        match capture.as_ref() {
            Some(config) => {
                *params = Some(AudioParameters::new(
                    config.sample_rate as i32,
                    config.channels,
                    config.sample_rate as usize / 100,
                ));
                0
            }
            None => {
                *params = None;
                -1
            }
        }
    }

    fn init_speaker(&self) -> i32 {
        0
    }

    fn speaker_is_initialized(&self) -> bool {
        true
    }

    fn init_microphone(&self) -> i32 {
        0
    }

    fn microphone_is_initialized(&self) -> bool {
        true
    }
}
