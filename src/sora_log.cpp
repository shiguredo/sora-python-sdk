#include "sora_log.h"

#include <string>

#include <rtc_base/logging.h>

#include "gil.h"

void EnableLibwebrtcLog(webrtc::LoggingSeverity severity) {
  webrtc::LogMessage::LogToDebug(severity);
  webrtc::LogMessage::LogTimestamps();
  webrtc::LogMessage::LogThreads();
}

void RtcLog(webrtc::LoggingSeverity severity, const std::string& message) {
  // Python C-API (PyEval_GetFrame / PyFrame_GetCode 等) は GIL 保持が必須。
  // 公開 API は通常 Python から呼ばれるが、GIL 非保持経路でも安全にする。
  gil_scoped_acquire acq;

  // Python のどこから呼ばれたかを一緒に出力する
  PyFrameObject* frame = PyEval_GetFrame();
  if (frame != nullptr) {
    // PyFrame_GetCode は新参照を返す。使い終わったら必ず Py_DECREF する。
    PyCodeObject* code = PyFrame_GetCode(frame);
    // PyUnicode_AsUTF8 のポインタは code 生存期間に紐付くため、
    // ログ組み立て前に std::string へコピーしてから解放する。
    std::string filename = PyUnicode_AsUTF8(code->co_filename);
    int lineno = PyFrame_GetLineNumber(frame);
    Py_DECREF(code);
    RTC_LOG_V(severity) << "[" << filename << ":" << lineno << "] " << message;
  } else {
    RTC_LOG_V(severity) << message;
  }
}
