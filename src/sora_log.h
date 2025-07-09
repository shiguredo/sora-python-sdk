#ifndef SORA_LOG_H_
#define SORA_LOG_H_

#include "sora.h"

void EnableLibwebrtcLog(webrtc::LoggingSeverity severity);
void RtcLog(webrtc::LoggingSeverity severity, const std::string& message);

#endif
