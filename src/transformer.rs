//! encoded 変換の Python 公開型。
//!
//! 既存 `sora_sdk` の `SoraVideoFrameTransformer` 等に対応する。
//! 処理器は同期的だが既存 API は非同期 (on_transform 後に enqueue) のため、
//! 待ち合わせで橋渡しする。音声の変換経路は受け口がなく対象外。

use std::collections::HashMap;
use std::sync::{
    atomic::{AtomicBool, AtomicU64, Ordering},
    Arc, Mutex,
};

use numpy::{PyArray1, PyArrayMethods, ToPyArray};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use shiguredo_webrtc::{
    FrameTransformerHandler, TransformableFrame, TransformableFrameDirection,
    TransformableVideoFrame,
};

use crate::audio_sink::set_callback;
use crate::enums::{SoraTransformableAudioFrameType, SoraTransformableFrameDirection};

// 待ち合わせ路の容量。送り側を塞がないよう 1 件分を持つ。
const RENDEZVOUS_CAPACITY: usize = 1;

/// 変換結果の配送。
enum TransformedOutcome {
    /// 加工済みで送る。
    Forward(TransformableFrame),
    /// 捨てる。
    Drop,
}

/// 変換器の共有状態。
pub(crate) struct TransformerShared {
    /// Python コールバック。
    callback: Mutex<Option<Py<PyAny>>>,
    /// 短絡時は Python を呼ばず通過させる。
    short_circuit: AtomicBool,
    /// 生存中か。切断時に待機者を起こす。
    alive: AtomicBool,
    /// 通番。
    next_id: AtomicU64,
    /// 待ち合わせ中の送り口。
    pending: Mutex<HashMap<u64, std::sync::mpsc::SyncSender<TransformedOutcome>>>,
}

impl TransformerShared {
    /// 共有状態を作る。
    pub(crate) fn new() -> Self {
        Self {
            callback: Mutex::new(None),
            short_circuit: AtomicBool::new(false),
            alive: AtomicBool::new(true),
            next_id: AtomicU64::new(1),
            pending: Mutex::new(HashMap::new()),
        }
    }

    /// 待機者を捨て扱いで起こし、新規受付を止める。
    pub(crate) fn shutdown(&self) {
        self.alive.store(false, Ordering::Relaxed);
        let mut pending = self.pending.lock().expect("transformer lock poisoned");
        for (_, sender) in pending.drain() {
            let _ = sender.try_send(TransformedOutcome::Drop);
        }
    }

    /// 短絡を開始する。以後のフレームは Python を呼ばず通過する。
    pub(crate) fn start_short_circuiting(&self) {
        self.short_circuit.store(true, Ordering::Relaxed);
    }
}

/// 処理器から Python に中継する。
pub(crate) struct VideoTransformRelay {
    /// 共有状態。
    shared: Arc<TransformerShared>,
}

impl VideoTransformRelay {
    /// 中継器を作る。
    pub(crate) fn new(shared: Arc<TransformerShared>) -> Self {
        Self { shared }
    }
}

impl FrameTransformerHandler for VideoTransformRelay {
    fn transform(&self, frame: TransformableFrame) -> Option<TransformableFrame> {
        if self.shared.short_circuit.load(Ordering::Relaxed)
            || !self.shared.alive.load(Ordering::Relaxed)
        {
            return Some(frame);
        }
        let id = self.shared.next_id.fetch_add(1, Ordering::Relaxed);
        let (sender, receiver) = std::sync::mpsc::sync_channel(RENDEZVOUS_CAPACITY);
        self.shared
            .pending
            .lock()
            .expect("transformer lock poisoned")
            .insert(id, sender);
        // Python 呼び出しは待機と別にし、錠は持たない。
        let mut slot = Some(frame);
        let proceed = Python::attach(|py| {
            let callback = self
                .shared
                .callback
                .lock()
                .expect("transformer lock poisoned")
                .as_ref()
                .map(|callback| callback.clone_ref(py));
            let Some(callback) = callback else {
                return false;
            };
            let frame = slot.take().expect("transformer frame taken twice");
            let wrapper = match Py::new(
                py,
                SoraTransformableVideoFrame::new(id, frame, self.shared.clone()),
            ) {
                Ok(wrapper) => wrapper,
                Err(error) => {
                    error.print(py);
                    return false;
                }
            };
            if let Err(error) = callback.call1(py, (wrapper,)) {
                error.print(py);
            }
            true
        });
        if !proceed {
            self.shared
                .pending
                .lock()
                .expect("transformer lock poisoned")
                .remove(&id);
            // 枠生成に失敗した分は破棄扱い、呼び先なしは通過扱いとする。
            return slot.take();
        }
        match receiver.recv() {
            Ok(TransformedOutcome::Forward(frame)) => Some(frame),
            Ok(TransformedOutcome::Drop) | Err(_) => None,
        }
    }
}

/// 変換フレームの共通操作。
fn take_frame(wrapper: &Mutex<Option<TransformableFrame>>) -> PyResult<TransformableFrame> {
    wrapper
        .lock()
        .expect("transformable frame lock poisoned")
        .take()
        .ok_or_else(|| PyRuntimeError::new_err("frame is already enqueued"))
}

/// 変換フレームを借りて処理する。
fn with_frame<T>(
    wrapper: &Mutex<Option<TransformableFrame>>,
    f: impl FnOnce(&mut TransformableFrame) -> PyResult<T>,
) -> PyResult<T> {
    let mut frame = take_frame(wrapper)?;
    let result = f(&mut frame);
    *wrapper.lock().expect("transformable frame lock poisoned") = Some(frame);
    result
}

/// 映像の変換フレーム。
#[pyclass(module = "sora_sdk")]
pub(crate) struct SoraTransformableVideoFrame {
    /// 通番。
    id: u64,
    /// 保持するフレーム。queue 受け渡しのため Mutex で包む。
    frame: Mutex<Option<TransformableFrame>>,
    /// 変換器の共有状態。
    shared: Arc<TransformerShared>,
}

impl SoraTransformableVideoFrame {
    /// フレームを包む。
    fn new(id: u64, frame: TransformableFrame, shared: Arc<TransformerShared>) -> Self {
        Self {
            id,
            frame: Mutex::new(Some(frame)),
            shared,
        }
    }

    /// 映像面を借りて処理する。非映像では誤りにする。
    fn with_video<T>(
        &self,
        f: impl FnOnce(&TransformableVideoFrame) -> PyResult<T>,
    ) -> PyResult<T> {
        let mut guard = self
            .frame
            .lock()
            .expect("transformable frame lock poisoned");
        let owned = guard
            .take()
            .ok_or_else(|| PyRuntimeError::new_err("frame is already enqueued"))?;
        match TransformableVideoFrame::try_from(owned) {
            Ok(video) => {
                let result = f(&video);
                *guard = Some(video.into_base());
                result
            }
            Err(base) => {
                *guard = Some(base);
                Err(PyValueError::new_err("frame is not a video frame"))
            }
        }
    }
}

impl Drop for SoraTransformableVideoFrame {
    fn drop(&mut self) {
        // enqueue されずに捨てられたら待機者を起こす。
        if self
            .frame
            .lock()
            .expect("transformable frame lock poisoned")
            .is_some()
        {
            self.frame
                .lock()
                .expect("transformable frame lock poisoned")
                .take();
            if let Some(sender) = self
                .shared
                .pending
                .lock()
                .expect("transformer lock poisoned")
                .remove(&self.id)
            {
                let _ = sender.try_send(TransformedOutcome::Drop);
            }
        }
    }
}

#[pymethods]
impl SoraTransformableVideoFrame {
    /// 符号化済みデータを読む。
    fn get_data<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyArray1<u8>>> {
        with_frame(&self.frame, |frame| Ok(frame.data().to_pyarray(py)))
    }

    /// 符号化済みデータを書く。
    fn set_data(&self, data: Bound<'_, PyArray1<u8>>) -> PyResult<()> {
        let owned = data.readonly().as_slice()?.to_vec();
        with_frame(&self.frame, |frame| {
            frame.set_data(&owned);
            Ok(())
        })
    }

    /// 荷物種別。
    #[getter]
    fn payload_type(&self) -> PyResult<u8> {
        with_frame(&self.frame, |frame| Ok(frame.payload_type()))
    }

    /// 送信元識別子。
    #[getter]
    fn ssrc(&self) -> PyResult<u32> {
        with_frame(&self.frame, |frame| Ok(frame.ssrc()))
    }

    /// RTP 時刻印。
    #[getter]
    fn rtp_timestamp(&self) -> PyResult<u32> {
        with_frame(&self.frame, |frame| {
            Ok(match frame.rtp_timestamp_info() {
                shiguredo_webrtc::RtpTimestampInfo::WithOffset(value)
                | shiguredo_webrtc::RtpTimestampInfo::WithoutOffset(value) => value,
            })
        })
    }

    /// RTP 時刻印を設定する。
    #[setter]
    fn set_rtp_timestamp(&self, value: u32) -> PyResult<()> {
        with_frame(&self.frame, |frame| {
            frame.set_rtp_timestamp(value);
            Ok(())
        })
    }

    /// 方向。
    #[getter]
    fn direction(&self, py: Python<'_>) -> PyResult<Py<SoraTransformableFrameDirection>> {
        let direction = with_frame(&self.frame, |frame| Ok(frame.direction()))?;
        let value = match direction {
            TransformableFrameDirection::Receiver => SoraTransformableFrameDirection::Receiver,
            TransformableFrameDirection::Sender => SoraTransformableFrameDirection::Sender,
            TransformableFrameDirection::Unknown(_) => SoraTransformableFrameDirection::Unknown,
        };
        Py::new(py, value)
    }

    /// MIME 型。
    #[getter]
    fn mime_type(&self) -> PyResult<String> {
        with_frame(&self.frame, |frame| {
            frame
                .mime_type()
                .map_err(|e| PyRuntimeError::new_err(format!("failed to get mime type: {e}")))
        })
    }

    /// 鍵面かどうか。
    #[getter]
    fn is_key_frame(&self) -> PyResult<bool> {
        self.with_video(|video| Ok(video.is_key_frame()))
    }

    /// 面識別子。
    #[getter]
    fn frame_id(&self) -> PyResult<Option<i64>> {
        self.with_video(|video| Ok(video.metadata().frame_id()))
    }

    /// 面依存列。
    #[getter]
    fn frame_dependencies<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyArray1<i64>>> {
        self.with_video(|video| {
            Ok(video
                .metadata()
                .dependencies()
                .unwrap_or_default()
                .to_pyarray(py))
        })
    }

    /// 幅。
    #[getter]
    fn width(&self) -> PyResult<u16> {
        self.with_video(|video| Ok(video.metadata().width()))
    }

    /// 高さ。
    #[getter]
    fn height(&self) -> PyResult<u16> {
        self.with_video(|video| Ok(video.metadata().height()))
    }

    /// 空間番号。
    #[getter]
    fn spatial_index(&self) -> PyResult<i32> {
        self.with_video(|video| Ok(video.metadata().spatial_index()))
    }

    /// 時間番号。
    #[getter]
    fn temporal_index(&self) -> PyResult<i32> {
        self.with_video(|video| Ok(video.metadata().temporal_index()))
    }

    /// 寄与元列。
    #[getter]
    fn contributing_sources<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyArray1<u32>>> {
        // 寄与元の取得口がないため空で返す。差分として記録する。
        Ok(Vec::<u32>::new().to_pyarray(py))
    }
}

/// 音声の変換フレーム。変換経路がないため受け口のみ。
#[pyclass(module = "sora_sdk")]
pub(crate) struct SoraTransformableAudioFrame;

#[pymethods]
impl SoraTransformableAudioFrame {
    /// 符号化済みデータを読む。変換経路がないため常に誤り。
    fn get_data<'py>(&self, _py: Python<'py>) -> PyResult<Bound<'py, PyArray1<u8>>> {
        Err(PyRuntimeError::new_err(
            "audio transformable frame is not supported",
        ))
    }

    /// 符号化済みデータを書く。変換経路がないため常に誤り。
    fn set_data(&self, _data: Bound<'_, PyArray1<u8>>) -> PyResult<()> {
        Err(PyRuntimeError::new_err(
            "audio transformable frame is not supported",
        ))
    }

    /// 荷物種別。変換経路がないため常に誤り。
    #[getter]
    fn payload_type(&self) -> PyResult<u8> {
        Err(PyRuntimeError::new_err(
            "audio transformable frame is not supported",
        ))
    }

    /// 送信元識別子。変換経路がないため常に誤り。
    #[getter]
    fn ssrc(&self) -> PyResult<u32> {
        Err(PyRuntimeError::new_err(
            "audio transformable frame is not supported",
        ))
    }

    /// RTP 時刻印。変換経路がないため常に誤り。
    #[getter]
    fn rtp_timestamp(&self) -> PyResult<u32> {
        Err(PyRuntimeError::new_err(
            "audio transformable frame is not supported",
        ))
    }

    /// 方向。変換経路がないため不明とする。
    #[getter]
    fn direction(&self, py: Python<'_>) -> PyResult<Py<SoraTransformableFrameDirection>> {
        Py::new(py, SoraTransformableFrameDirection::Unknown)
    }

    /// MIME 型。変換経路がないため常に誤り。
    #[getter]
    fn mime_type(&self) -> PyResult<String> {
        Err(PyRuntimeError::new_err(
            "audio transformable frame is not supported",
        ))
    }

    /// 寄与元列。変換経路がないため空とする。
    #[getter]
    fn contributing_sources<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyArray1<u32>>> {
        Ok(Vec::<u32>::new().to_pyarray(py))
    }

    /// 連番。変換経路がないためなしとする。
    #[getter]
    fn sequence_number(&self) -> Option<i64> {
        None
    }

    /// 取り込み時刻。変換経路がないためなしとする。
    #[getter]
    fn absolute_capture_timestamp(&self) -> Option<i64> {
        None
    }

    /// 種別。変換経路がないため無音とする。
    #[getter]
    fn r#type(&self, py: Python<'_>) -> PyResult<Py<SoraTransformableAudioFrameType>> {
        Py::new(py, SoraTransformableAudioFrameType::Empty)
    }

    /// 音量。変換経路がないためなしとする。
    #[getter]
    fn audio_level(&self) -> Option<i64> {
        None
    }

    /// 受信時刻。変換経路がないためなしとする。
    #[getter]
    fn receive_time(&self) -> Option<i64> {
        None
    }
}

/// 映像の encoded 変換器。
#[pyclass(module = "sora_sdk")]
pub(crate) struct SoraVideoFrameTransformer {
    /// 共有状態。
    shared: Arc<TransformerShared>,
}

impl SoraVideoFrameTransformer {
    /// 共有状態を取り出す。
    pub(crate) fn shared(&self) -> Arc<TransformerShared> {
        self.shared.clone()
    }
}

impl Drop for SoraVideoFrameTransformer {
    fn drop(&mut self) {
        // 変換器が先になくなっても待機者が残らないようにする。
        self.shared.shutdown();
    }
}

#[pymethods]
impl SoraVideoFrameTransformer {
    /// 変換器を作る。
    #[new]
    fn new() -> Self {
        Self {
            shared: Arc::new(TransformerShared::new()),
        }
    }

    /// 変換後フレームを送る。
    fn enqueue(&self, frame: Py<SoraTransformableVideoFrame>) -> PyResult<()> {
        Python::attach(|py| {
            let wrapper = frame.borrow(py);
            let owned = {
                wrapper
                    .frame
                    .lock()
                    .expect("transformable frame lock poisoned")
                    .take()
                    .ok_or_else(|| PyRuntimeError::new_err("frame is already enqueued"))?
            };
            let id = wrapper.id;
            let shared = wrapper.shared.clone();
            drop(wrapper);
            let sender = shared
                .pending
                .lock()
                .expect("transformer lock poisoned")
                .remove(&id);
            match sender {
                Some(sender) => sender
                    .try_send(TransformedOutcome::Forward(owned))
                    .map_err(|_| PyRuntimeError::new_err("transformer is already shut down")),
                None => Err(PyRuntimeError::new_err(
                    "frame is expired or already enqueued",
                )),
            }
        })
    }

    /// 短絡を開始する。
    fn start_short_circuiting(&self) {
        self.shared.start_short_circuiting();
    }

    /// on_transform コールバック。
    #[getter]
    fn on_transform(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.shared
            .callback
            .lock()
            .expect("transformer lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_transform コールバックを設定する。
    #[setter]
    fn set_on_transform(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.shared.callback, value, "on_transform")
    }
}

/// 音声の encoded 変換器。変換経路がないため受け口のみ。
#[pyclass(module = "sora_sdk")]
pub(crate) struct SoraAudioFrameTransformer {
    /// 共有状態。受け口の保持用。
    shared: Arc<TransformerShared>,
}

#[pymethods]
impl SoraAudioFrameTransformer {
    /// 変換器を作る。
    #[new]
    fn new() -> Self {
        Self {
            shared: Arc::new(TransformerShared::new()),
        }
    }

    /// 変換後フレームを送る。変換経路がないため常に誤り。
    fn enqueue(&self, _frame: Py<SoraTransformableAudioFrame>) -> PyResult<()> {
        Err(PyRuntimeError::new_err(
            "audio frame transformer is not supported",
        ))
    }

    /// 短絡を開始する。受け付けるが何もしない。
    fn start_short_circuiting(&self) {
        self.shared.start_short_circuiting();
    }

    /// on_transform コールバック。
    #[getter]
    fn on_transform(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.shared
            .callback
            .lock()
            .expect("transformer lock poisoned")
            .as_ref()
            .map(|callback| callback.clone_ref(py))
    }

    /// on_transform コールバックを設定する。
    #[setter]
    fn set_on_transform(&self, py: Python<'_>, value: Option<Py<PyAny>>) -> PyResult<()> {
        set_callback(py, &self.shared.callback, value, "on_transform")
    }
}
