#ifndef SORA_JSON_H_
#define SORA_JSON_H_

// nonobind
// clang-format off
#include <nanobind/nanobind.h>
// clang-format on

// Boost
#include <boost/json.hpp>

namespace nb = nanobind;

/**
 * Python で渡された値を boost::json::value に変換します。
 *
 * 呼び出し元は GIL を保持している必要があります。
 * 変換規則は次のとおりです。
 * - None は JSON の null になります (JSON-RPC 2.0 の params 省略とは意味が異なります)
 * - bool / int64 の範囲内の整数 / float / str / list / dict は対応する JSON の値になります
 *   - float は float32 で厳密に表現できる値だけが変換できます (0.1 のような値は nb::type_error になります)
 * - int64 の範囲を超える整数と、キーが文字列でない dict は nb::cast_error になります
 * - numpy の数値・真偽値スカラー型 (numpy.int64 / numpy.float64 / numpy.bool_ など) を含め、上記以外の型は nb::type_error になります
 *
 * @param value Python から渡された値の nanobind::handle
 * @param error_message 上記以外の型だった場合に nb::type_error で返す際のエラーメッセージ
 * @return boost::json::value
 */
boost::json::value ConvertJsonValue(nb::handle value,
                                    const char* error_message);

#endif
