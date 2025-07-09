#include "sora_log.h"

void EnableLibwebrtcLog(webrtc::LoggingSeverity severity) {
  webrtc::LogMessage::LogToDebug(severity);
  webrtc::LogMessage::LogTimestamps();
  webrtc::LogMessage::LogThreads();
}

void RtcLog(webrtc::LoggingSeverity severity, const std::string& message) {
  // Python のどこから呼ばれたかを一緒に出力する
  PyFrameObject* frame = PyEval_GetFrame();
  if (frame != nullptr) {
    PyCodeObject* code = PyFrame_GetCode(frame);
    const char* filename = PyUnicode_AsUTF8(code->co_filename);
    int lineno = PyFrame_GetLineNumber(frame);
    RTC_LOG_V(severity) << "[" << filename << ":" << lineno << "] " << message;
  } else {
    RTC_LOG_V(severity) << message;
  }
}
