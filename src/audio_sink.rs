//! 音声 Sink と音声フレームの Python 公開型。
//!
//! 既存 `sora_sdk` の `SoraAudioSink` / `SoraAudioFrame` に対応する。
//! リサンプルは未対応で、受信ネイティブの形式で渡す。

use std::collections::VecDeque;
use std::sync::{
    atomic::{AtomicI32, AtomicUsize, Ordering},
    Arc, Mutex,
};
use std::time::{Duration, Instant};

use ::sora_sdk::SoraConnectionContext;
use numpy::{PyArrayMethods, ToPyArray};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use shiguredo_webrtc::{AudioTrack, AudioTrackSink, AudioTrackSinkHandler};

use crate::frames::SoraAudioFrame;

use crate::track::SoraMediaTrack;

/// キューに積む音声データ。
struct QueuedAudio {
    /// インタリーブ PCM (int16)。
    samples: Vec<i16>,
    /// チャンネル数。
    channels: usize,
}

/// Sink 共有状態。
struct SinkState {
    /// 受信待ちキュー。
    queue: Mutex<VecDeque<QueuedAudio>>,
    /// 通知済みの実効サンプルレート。
    sample_rate: AtomicI32,
    /// 通知済みの実効チャンネル数。
    channels: AtomicUsize,
    /// 要求された出力周波数。正でなければ受信そのまま。
    output_frequency: i32,
    /// 要求された出力溝数。正でなければ受信そのまま。
    output_channels: usize,
    /// on_data コールバック。
    on_data: Mutex<Option<Py<PyAny>>>,
    /// on_format コールバック。
    on_format: Mutex<Option<Py<PyAny>>>,
}

/// 実効形式を求める。正の指定がなければ受信そのままとする。
fn effective_format(
    requested_rate: i32,
    requested_channels: usize,
    native_rate: i32,
    native_channels: usize,
) -> (i32, usize) {
    let rate = if requested_rate > 0 {
        requested_rate
    } else {
        native_rate
    };
    let channels = if requested_channels > 0 {
        requested_channels
    } else {
        native_channels
    };
    (rate, channels)
}

/// PCM を直線補間で形式変換する。溝変換後に周波数変換する。
pub(crate) fn resample_pcm(
    samples: &[i16],
    native_rate: i32,
    native_channels: usize,
    out_rate: i32,
    out_channels: usize,
) -> Vec<i16> {
    if samples.is_empty() || native_channels == 0 || out_channels == 0 {
        return Vec::new();
    }
    let frames = samples.len() / native_channels;
    // 溝変換する。
    let mapped: Vec<i16> = (0..frames)
        .flat_map(|index| {
            let base = index * native_channels;
            (0..out_channels).map(move |out| {
                if native_channels == out_channels {
                    samples[base + out]
                } else if out_channels == 1 {
                    // 平均で単溝化する。
                    (samples[base..base + native_channels]
                        .iter()
                        .map(|sample| i32::from(*sample))
                        .sum::<i32>()
                        / native_channels as i32) as i16
                } else if native_channels == 1 {
                    samples[base]
                } else {
                    samples[base + out.min(native_channels - 1)]
                }
            })
        })
        .collect();
    if native_rate <= 0 || out_rate <= 0 || native_rate == out_rate {
        return mapped;
    }
    // 直線補間で周波数変換する。
    let out_frames = (frames * out_rate as usize + native_rate as usize / 2) / native_rate as usize;
    let mut converted = Vec::with_capacity(out_frames * out_channels);
    for index in 0..out_frames {
        let position = index as f64 * native_rate as f64 / out_rate as f64;
        let base = position.floor() as usize;
        let frac = (position - base as f64) as f32;
        let next = (base + 1).min(frames - 1);
        for channel in 0..out_channels {
            let first = f32::from(mapped[base * out_channels + channel]);
            let second = f32::from(mapped[next * out_channels + channel]);
            converted.push(
                (first + (second - first) * frac)
                    .round()
                    .clamp(i16::MIN as f32, i16::MAX as f32) as i16,
            );
        }
    }
    converted
}

/// キューに積むハンドラ。
struct QueueingAudioHandler {
    /// 共有状態。
    state: Arc<SinkState>,
}

impl AudioTrackSinkHandler for QueueingAudioHandler {
    fn on_data(
        &mut self,
        audio_data: &[u8],
        bits_per_sample: i32,
        sample_rate: i32,
        number_of_channels: usize,
        _number_of_frames: usize,
    ) {
        // 受信スレッド上で呼ばれる。16bit 以外は扱わない。
        if bits_per_sample != 16 || number_of_channels == 0 || !audio_data.len().is_multiple_of(2) {
            return;
        }
        let native: Vec<i16> = audio_data
            .as_chunks::<2>()
            .0
            .iter()
            .map(|chunk| i16::from_ne_bytes(*chunk))
            .collect();
        // 要求形式に変換する。
        let (rate, channels) = effective_format(
            self.state.output_frequency,
            self.state.output_channels,
            sample_rate,
            number_of_channels,
        );
        let samples = resample_pcm(&native, sample_rate, number_of_channels, rate, channels);
        // 形式変化を on_format で中継する。初回も通知する。
        let previous_rate = self.state.sample_rate.swap(rate, Ordering::Relaxed);
        let previous_channels = self.state.channels.swap(channels, Ordering::Relaxed);
        let format_changed = previous_rate != rate || previous_channels != channels;
        Python::attach(|py| {
            if format_changed {
                if let Some(callback) = self
                    .state
                    .on_format
                    .lock()
                    .expect("callback lock poisoned")
                    .as_ref()
                    .map(|callback| callback.clone_ref(py))
                {
                    if let Err(error) = callback.call1(py, (rate, channels)) {
                        error.print(py);
                    }
                }
            }
            if let Some(callback) = self
                .state
                .on_data
                .lock()
                .expect("callback lock poisoned")
                .as_ref()
                .map(|callback| callback.clone_ref(py))
            {
                let array = samples.to_pyarray(py);
                let shaped = array.reshape([samples.len() / channels.max(1), channels.max(1)]);
                match shaped {
                    Ok(shaped) => {
                        if let Err(error) = callback.call1(py, (shaped,)) {
                            error.print(py);
                        }
                    }
                    Err(error) => error.print(py),
                }
            }
        });
        // キューに積んで read() を起こす。
        self.state
            .queue
            .lock()
            .expect("audio queue lock poisoned")
            .push_back(QueuedAudio {
                samples,
                channels: number_of_channels,
            });
    }
}

/// 音声 Sink。
#[pyclass(module = "sora_sdk")]
pub(crate) struct SoraAudioSink {
    /// 共有状態。
    state: Arc<SinkState>,
    /// 登録済み Sink (登録解除まで保持する)。
    sink: Mutex<Option<AudioTrackSink>>,
    /// 所有維持するトラック。
    _track: AudioTrack,
    /// factory 所有のコンテキスト。破棄順序のため保持する。
    _context: Arc<SoraConnectionContext>,
}

#[pymethods]
impl SoraAudioSink {
    /// Sink を作りトラックに付ける。
    #[new]
    #[pyo3(signature = (track, output_frequency = -1, output_channels = 0))]
    fn new(
        track: &SoraMediaTrack,
        output_frequency: i32,
        output_channels: usize,
    ) -> PyResult<Self> {
        let kind = track.kind()?;
        if kind != "audio" {
            return Err(PyValueError::new_err(format!(
                "SoraAudioSink requires an audio track, got {kind}"
            )));
        }
        let state = Arc::new(SinkState {
            queue: Mutex::new(VecDeque::new()),
            sample_rate: AtomicI32::new(-1),
            channels: AtomicUsize::new(0),
            output_frequency,
            output_channels,
            on_data: Mutex::new(None),
            on_format: Mutex::new(None),
        });
        let sink = AudioTrackSink::new_with_handler(Box::new(QueueingAudioHandler {
            state: state.clone(),
        }));
        let context = track.connection_context();
        let audio = track.with_webrtc_track(|track| track.cast_to_audio_track());
        audio.add_sink(&sink);
        Ok(Self {
            state,
            sink: Mutex::new(Some(sink)),
            _track: audio,
            _context: context,
        })
    }

    /// 受信 PCM を取り出す。空なら (False, None) を返す。
    #[pyo3(signature = (frames = 0, timeout = 1.0))]
    fn read(&self, py: Python<'_>, frames: usize, timeout: f64) -> PyResult<Py<PyAny>> {
        if !timeout.is_finite() || timeout < 0.0 {
            return Err(PyValueError::new_err(format!(
                "timeout must be a finite value >= 0, got {timeout}"
            )));
        }
        let deadline = Instant::now() + Duration::from_secs_f64(timeout);
        // GIL を外して待つ。100ms 刻みで割り込みを確認する。
        // Condvar のガードはスレッドをまたげないため、待ちは sleep の分割で行う。
        loop {
            let (ready, expired) = {
                let guard = self.state.queue.lock().expect("audio queue lock poisoned");
                let channels = self.state.channels.load(Ordering::Relaxed);
                let buffered: usize = guard.iter().map(|queued| queued.samples.len()).sum();
                let ready = if frames == 0 {
                    buffered > 0
                } else {
                    channels > 0 && buffered >= frames * channels
                };
                (ready, Instant::now() >= deadline)
            };
            if ready || expired {
                break;
            }
            let remaining = deadline.saturating_duration_since(Instant::now());
            let slice = remaining.min(Duration::from_millis(100));
            py.detach(|| std::thread::sleep(slice));
            Python::attach(|py| py.check_signals())?;
        }
        let mut guard = self.state.queue.lock().expect("audio queue lock poisoned");
        let channels = self.state.channels.load(Ordering::Relaxed);
        // 形式が一致する分だけ取り出す。
        let mut taken: Vec<i16> = Vec::new();
        let wanted = if frames == 0 {
            usize::MAX
        } else {
            frames * channels.max(1)
        };
        while taken.len() < wanted {
            match guard.front() {
                Some(front) if front.channels == channels || channels == 0 => {
                    let front = guard.pop_front().expect("audio queue changed unexpectedly");
                    taken.extend_from_slice(&front.samples);
                }
                _ => break,
            }
        }
        drop(guard);
        Python::attach(|py| {
            if taken.is_empty() {
                Ok((false, py.None()).into_pyobject(py)?.into_any().unbind())
            } else {
                let columns = channels.max(1);
                let array = taken.to_pyarray(py);
                let shaped = array.reshape([taken.len() / columns, columns])?;
                Ok((true, shaped).into_pyobject(py)?.into_any().unbind())
            }
        })
    }

    /// on_data コールバック。
    #[getter]
    fn on_data(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.state
            .on_data
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_data コールバックを設定する。
    #[setter]
    fn set_on_data(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.state.on_data, value, "on_data")
    }

    /// on_format コールバック。
    #[getter]
    fn on_format(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.state
            .on_format
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_format コールバックを設定する。
    #[setter]
    fn set_on_format(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.state.on_format, value, "on_format")
    }
}

/// コールバック用 setter の共通処理。呼び出し可能か検証する。
pub(crate) fn set_callback(
    py: Python<'_>,
    slot: &Mutex<Option<Py<PyAny>>>,
    value: Option<Py<PyAny>>,
    name: &str,
) -> PyResult<()> {
    if let Some(callback) = &value {
        if !callback.bind(py).is_callable() {
            return Err(PyValueError::new_err(format!(
                "{name} must be callable or None"
            )));
        }
    }
    *slot.lock().expect("callback lock poisoned") = value;
    Ok(())
}

impl Drop for SoraAudioSink {
    fn drop(&mut self) {
        // トラックから登録解除する。
        if let Some(sink) = self.sink.lock().expect("sink lock poisoned").take() {
            self._track.remove_sink(&sink);
        }
    }
}

/// フレーム中継 Sink 共有状態。
struct StreamSinkState {
    /// 要求された出力周波数。正でなければ受信そのまま。
    output_frequency: i32,
    /// 要求された出力溝数。正でなければ受信そのまま。
    output_channels: usize,
    /// on_frame コールバック。
    on_frame: Mutex<Option<Py<PyAny>>>,
}

/// フレームを中継するハンドラ。
struct RelayingAudioHandler {
    /// 共有状態。
    state: Arc<StreamSinkState>,
}

impl AudioTrackSinkHandler for RelayingAudioHandler {
    fn on_data(
        &mut self,
        audio_data: &[u8],
        bits_per_sample: i32,
        sample_rate: i32,
        number_of_channels: usize,
        _number_of_frames: usize,
    ) {
        // 受信スレッド上で呼ばれる。16bit 以外は扱わない。
        if bits_per_sample != 16 || number_of_channels == 0 || !audio_data.len().is_multiple_of(2) {
            return;
        }
        let native: Vec<i16> = audio_data
            .as_chunks::<2>()
            .0
            .iter()
            .map(|chunk| i16::from_ne_bytes(*chunk))
            .collect();
        let (rate, channels) = effective_format(
            self.state.output_frequency,
            self.state.output_channels,
            sample_rate,
            number_of_channels,
        );
        let samples = resample_pcm(&native, sample_rate, number_of_channels, rate, channels);
        let samples_per_channel = samples.len() / channels.max(1);
        Python::attach(|py| {
            let Some(callback) = self
                .state
                .on_frame
                .lock()
                .expect("callback lock poisoned")
                .as_ref()
                .map(|callback| callback.clone_ref(py))
            else {
                return;
            };
            let frame = SoraAudioFrame::from_pcm(samples, samples_per_channel, channels, rate);
            match Py::new(py, frame) {
                Ok(frame) => {
                    if let Err(error) = callback.call1(py, (frame,)) {
                        error.print(py);
                    }
                }
                Err(error) => error.print(py),
            }
        });
    }
}

/// 音声ストリーム Sink。
#[pyclass(module = "sora_sdk")]
pub(crate) struct SoraAudioStreamSink {
    /// 登録済み Sink (登録解除まで保持する)。
    sink: Mutex<Option<AudioTrackSink>>,
    /// 所有維持するトラック。
    _track: AudioTrack,
    /// factory 所有のコンテキスト。破棄順序のため保持する。
    _context: Arc<SoraConnectionContext>,
    /// 共有状態。
    state: Arc<StreamSinkState>,
}

#[pymethods]
impl SoraAudioStreamSink {
    /// Sink を作りトラックに付ける。
    #[new]
    #[pyo3(signature = (track, output_frequency = -1, output_channels = 0))]
    fn new(
        track: &SoraMediaTrack,
        output_frequency: i32,
        output_channels: usize,
    ) -> PyResult<Self> {
        let kind = track.kind()?;
        if kind != "audio" {
            return Err(PyValueError::new_err(format!(
                "SoraAudioStreamSink requires an audio track, got {kind}"
            )));
        }
        let state = Arc::new(StreamSinkState {
            output_frequency,
            output_channels,
            on_frame: Mutex::new(None),
        });
        let sink = AudioTrackSink::new_with_handler(Box::new(RelayingAudioHandler {
            state: state.clone(),
        }));
        let context = track.connection_context();
        let audio = track.with_webrtc_track(|track| track.cast_to_audio_track());
        audio.add_sink(&sink);
        Ok(Self {
            sink: Mutex::new(Some(sink)),
            _track: audio,
            _context: context,
            state,
        })
    }

    /// on_frame コールバック。
    #[getter]
    fn on_frame(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.state
            .on_frame
            .lock()
            .expect("callback lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_frame コールバックを設定する。
    #[setter]
    fn set_on_frame(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.state.on_frame, value, "on_frame")
    }
}

impl Drop for SoraAudioStreamSink {
    fn drop(&mut self) {
        // トラックから登録解除する。
        if let Some(sink) = self.sink.lock().expect("sink lock poisoned").take() {
            self._track.remove_sink(&sink);
        }
    }
}
