#include "sora_json.h"

#include <string>

// nonobind
#include <nanobind/stl/string.h>

boost::json::value ConvertJsonValue(nb::handle value,
                                    const char* error_message) {
  if (value.is_none()) {
    return nullptr;
  } else if (nb::isinstance<bool>(value)) {
    return nb::cast<bool>(value);
  } else if (PyLong_Check(value.ptr())) {
    // nb::isinstance<int> は C++ int に収まらない Python int で false になるため
    // PyLong_Check で任意精度整数を受け取り、int64_t へ変換する
    return nb::cast<int64_t>(value);
  } else if (nb::isinstance<float>(value)) {
    return nb::cast<float>(value);
  } else if (nb::isinstance<nb::str>(value)) {
    // nb::cast<std::string> で明示的にコピーを取る
    std::string s = nb::cast<std::string>(value);
    return boost::json::value(boost::json::string(s));
  } else if (nb::isinstance<nb::list>(value)) {
    nb::list nb_list = nb::cast<nb::list>(value);
    boost::json::array json_array;
    for (auto v : nb_list)
      json_array.emplace_back(ConvertJsonValue(v, error_message));
    return json_array;
  } else if (nb::isinstance<nb::dict>(value)) {
    nb::dict nb_dict = nb::cast<nb::dict>(value);
    boost::json::object json_object;
    for (auto [k, v] : nb_dict)
      json_object.emplace(nb::cast<std::string>(k),
                          ConvertJsonValue(v, error_message));
    return json_object;
  }

  throw nb::type_error(error_message);
}
