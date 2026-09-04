//! 受信駆動用の偽オーディオデバイス。
//!
//! 既定の Dummy ADM では再生ループがなく音声引き抜きが止まるため、
//! 10ms 周期で再生要求を出す偽デバイスでミキサーを駆動する。
//! 録音側は未対応で、受信専用の駆動が目的である。

use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::time::Duration;

use shiguredo_webrtc::{AudioDeviceModule, AudioDeviceModuleHandler, AudioTransportRef};

// 再生要求の形式。エンジン側の書き込みが要求を上回らないよう、
// 余裕を持ってステレオで要求する。受信引き抜きの駆動だけが目的のため
// 内容は使わない。
// 再生サンプルレート (Hz)。
const PLAY_SAMPLE_RATE: u32 = 48000;
// 再生チャンネル数。
const PLAY_CHANNELS: usize = 2;
// 10ms あたりのサンプル数。
const PLAY_SAMPLES_10MS: usize = 480;

/// 偽デバイスの共有状態。
struct FakeAudioState {
    /// 登録された転送路。
    transport: Mutex<Option<AudioTransportRef>>,
    /// 初期化済みか。
    initialized: AtomicBool,
    /// 録音初期化済みか。
    recording_initialized: AtomicBool,
    /// 再生初期化済みか。
    playout_initialized: AtomicBool,
    /// 再生中か。
    playing: AtomicBool,
    /// 再生スレッド。
    player: Mutex<Option<std::thread::JoinHandle<()>>>,
}

/// 再生ループでミキサーを駆動する偽 ADM ハンドラ。
pub(crate) struct FakeAudioDevice {
    /// 共有状態。
    state: Arc<FakeAudioState>,
}

impl FakeAudioDevice {
    /// 偽デバイスを作る。
    pub(crate) fn new() -> Self {
        Self {
            state: Arc::new(FakeAudioState {
                transport: Mutex::new(None),
                initialized: AtomicBool::new(false),
                recording_initialized: AtomicBool::new(false),
                playout_initialized: AtomicBool::new(false),
                playing: AtomicBool::new(false),
                player: Mutex::new(None),
            }),
        }
    }

    /// webrtc のデバイスモジュールに変える。
    pub(crate) fn into_device_module(self) -> AudioDeviceModule {
        AudioDeviceModule::new_with_handler(Box::new(self))
    }
}

/// 再生要求を出し続けてミキサーを駆動する。
fn pump(state: Arc<FakeAudioState>) {
    let mut buffer = vec![0u8; PLAY_SAMPLES_10MS * 2 * PLAY_CHANNELS];
    while state.playing.load(Ordering::Relaxed) {
        let tick = std::time::Instant::now();
        let transport = *state.transport.lock().expect("audio device lock poisoned");
        if let Some(transport) = transport {
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
                    buffer.as_mut_ptr(),
                    &mut samples_out,
                    &mut elapsed_time_ms,
                    &mut ntp_time_ms,
                );
            }
        }
        let elapsed = tick.elapsed();
        if elapsed < Duration::from_millis(10) {
            std::thread::sleep(Duration::from_millis(10) - elapsed);
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
        let mut player = self
            .state
            .player
            .lock()
            .expect("audio device lock poisoned");
        if player.is_none() {
            let state = self.state.clone();
            *player = std::thread::Builder::new()
                .name("fake-audio-playout".to_string())
                .spawn(move || pump(state))
                .ok();
        }
        0
    }

    fn stop_playout(&self) -> i32 {
        self.state.playing.store(false, Ordering::Relaxed);
        if let Some(player) = self
            .state
            .player
            .lock()
            .expect("audio device lock poisoned")
            .take()
        {
            let _ = player.join();
        }
        0
    }

    fn playing(&self) -> bool {
        self.state.playing.load(Ordering::Relaxed)
    }

    fn recording(&self) -> bool {
        false
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
