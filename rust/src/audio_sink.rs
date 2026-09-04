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

use numpy::{PyArrayMethods, ToPyArray};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use shiguredo_webrtc::{AudioTrack, AudioTrackSink, AudioTrackSinkHandler};
use sora_sdk::SoraConnectionContext;

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
    /// 通知済みのサンプルレート。
    sample_rate: AtomicI32,
    /// 通知済みのチャンネル数。
    channels: AtomicUsize,
    /// on_data コールバック。
    on_data: Mutex<Option<Py<PyAny>>>,
    /// on_format コールバック。
    on_format: Mutex<Option<Py<PyAny>>>,
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
        let samples: Vec<i16> = audio_data
            .as_chunks::<2>()
            .0
            .iter()
            .map(|chunk| i16::from_ne_bytes(*chunk))
            .collect();
        // 形式変化を on_format で中継する。初回も通知する。
        let previous_rate = self.state.sample_rate.swap(sample_rate, Ordering::Relaxed);
        let previous_channels = self
            .state
            .channels
            .swap(number_of_channels, Ordering::Relaxed);
        let format_changed =
            previous_rate != sample_rate || previous_channels != number_of_channels;
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
                    if let Err(error) = callback.call1(py, (sample_rate, number_of_channels)) {
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
                let shaped =
                    array.reshape([samples.len() / number_of_channels, number_of_channels]);
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
#[pyclass(module = "sora_rust_sdk")]
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
        // output_frequency / output_channels は受け付けるが、
        // リサンプル未対応のため受信ネイティブで動作する。
        let _ = (output_frequency, output_channels);
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
        let samples: Vec<i16> = audio_data
            .as_chunks::<2>()
            .0
            .iter()
            .map(|chunk| i16::from_ne_bytes(*chunk))
            .collect();
        let samples_per_channel = samples.len() / number_of_channels;
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
            let frame = SoraAudioFrame::from_pcm(
                samples,
                samples_per_channel,
                number_of_channels,
                sample_rate,
            );
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
#[pyclass(module = "sora_rust_sdk")]
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
        // output_frequency / output_channels は受け付けるが、
        // リサンプル未対応のため受信ネイティブで動作する。
        let _ = (output_frequency, output_channels);
        let kind = track.kind()?;
        if kind != "audio" {
            return Err(PyValueError::new_err(format!(
                "SoraAudioStreamSink requires an audio track, got {kind}"
            )));
        }
        let state = Arc::new(StreamSinkState {
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
