#include "sora_log.h"

void EnableLibwebrtcLog(rtc::LoggingSeverity severity) {
  rtc::LogMessage::LogToDebug(severity);
  rtc::LogMessage::LogTimestamps();
  rtc::LogMessage::LogThreads();
}

void RtcLog(rtc::LoggingSeverity severity, const std::string& message) {
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
