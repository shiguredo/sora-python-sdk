#include "sora_log.h"

void EnableLibwebrtcLog(rtc::LoggingSeverity severity) {
  rtc::LogMessage::LogToDebug(severity);
  rtc::LogMessage::LogTimestamps();
  rtc::LogMessage::LogThreads();
}
