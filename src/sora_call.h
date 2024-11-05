#ifndef SORA_CALL_H_
#define SORA_CALL_H_

#include <type_traits>

// nanobind
#include <nanobind/nanobind.h>

// WebRTC
#include <rtc_base/logging.h>

template <class F, class... Args>
auto call_python(F f, Args&&... args) -> std::invoke_result_t<F, Args...> {
  try {
    return f(args...);
  } catch (nanobind::python_error& e) {
    RTC_LOG(LS_ERROR) << "Failed to call python function: " << e.what();
    throw;
  } catch (std::exception& e) {
    RTC_LOG(LS_ERROR) << "Failed to call python function: " << e.what();
    throw;
  } catch (...) {
    RTC_LOG(LS_ERROR) << "Failed to call python function: Unknown exception";
    throw;
  }
}

#endif
