#ifndef SORA_LOG_H_
#define SORA_LOG_H_

#include "sora.h"

void EnableLibwebrtcLog(rtc::LoggingSeverity severity);
void RtcLog(rtc::LoggingSeverity severity, const std::string& message);

#endif
