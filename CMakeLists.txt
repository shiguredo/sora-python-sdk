cmake_minimum_required(VERSION 3.18)
project(sora_sdk)

# Only interpret if() arguments as variables or keywords when unquoted.
cmake_policy(SET CMP0054 NEW)
# MSVC runtime library flags are selected by an abstraction.
cmake_policy(SET CMP0091 NEW)

if (NOT CMAKE_CROSSCOMPILING)
  set(Python_VERSION "${PYTHON_VERSION_STRING}")
  set(Python_EXECUTABLE "${PYTHON_EXECUTABLE}")
  set(Python_INCLUDE_DIR "${PYTHON_INCLUDE_DIR}")
  set(Python_LIBRARIES "${PYTHON_LIBRARY}")
  find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
endif()

if (CMAKE_CROSSCOMPILING)
  set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY NEVER)
  set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE NEVER)
  set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE NEVER)
  find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
  set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)
  set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
  set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
endif()

message(STATUS "-- Python_FOUND: ${Python_FOUND}")
message(STATUS "-- Python_Development.Module_FOUND: ${Python_Development.Module_FOUND}")
message(STATUS "-- Python_EXECUTABLE: ${Python_EXECUTABLE}")
message(STATUS "-- Python_INCLUDE_DIR: ${Python_INCLUDE_DIR}")
message(STATUS "-- Python_INCLUDE_DIRS: ${Python_INCLUDE_DIRS}")
message(STATUS "-- Python_LIBRARIES: ${Python_LIBRARIES}")
message(STATUS "-- Python_LIBRARY_DIRS: ${Python_LIBRARY_DIRS}")
message(STATUS "-- Python_RUNTIME_LIBRARY_DIRS: ${Python_RUNTIME_LIBRARY_DIRS}")


execute_process(
  COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
  OUTPUT_STRIP_TRAILING_WHITESPACE OUTPUT_VARIABLE NB_DIR)
list(APPEND CMAKE_PREFIX_PATH "${NB_DIR}")

set(TARGET_OS "" CACHE STRING "ビルド対象の動作する OS。\n有効な値は windows, macos, ubuntu")
set(WEBRTC_INCLUDE_DIR "" CACHE PATH "WebRTC のインクルードディレクトリ")
set(WEBRTC_LIBRARY_DIR "" CACHE PATH "WebRTC のライブラリディレクトリ")
set(WEBRTC_LIBRARY_NAME "webrtc" CACHE STRING "WebRTC のライブラリ名")
set(BOOST_ROOT "" CACHE PATH "Boost のルートディレクトリ")
set(SORA_DIR "" CACHE PATH "Sora のルートディレクトリ")

list(APPEND CMAKE_PREFIX_PATH ${SORA_DIR})
list(APPEND CMAKE_MODULE_PATH ${SORA_DIR}/share/cmake)

set(Boost_USE_STATIC_LIBS ON)
if(TARGET_OS STREQUAL "windows")
  set(Boost_USE_STATIC_RUNTIME ON)
endif()

find_package(Boost REQUIRED COMPONENTS json filesystem)
find_package(Lyra REQUIRED)
find_package(WebRTC REQUIRED)
find_package(Sora REQUIRED)
find_package(nanobind CONFIG REQUIRED)
if(NOT TARGET_OS STREQUAL "windows")
  find_package(Threads REQUIRED)
endif()
if(TARGET_OS STREQUAL "ubuntu")
  find_package(Libva REQUIRED)
  find_package(Libdrm REQUIRED)
endif()


nanobind_add_module(
  sora_sdk_ext
  NB_STATIC
  src/dummy_audio_mixer.cpp
  src/sora.cpp
  src/sora_audio_sink.cpp
  src/sora_audio_source.cpp
  src/sora_connection.cpp
  src/sora_factory.cpp
  src/sora_log.cpp
  src/sora_sdk_ext.cpp
  src/sora_video_sink.cpp
  src/sora_video_source.cpp
)

set_target_properties(sora_sdk_ext PROPERTIES CXX_STANDARD 20 C_STANDARD 20)
set_target_properties(sora_sdk_ext PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(TARGET_OS STREQUAL "macos")
  set_target_properties(sora_sdk_ext PROPERTIES CXX_VISIBILITY_PRESET hidden)
elseif(TARGET_OS STREQUAL "ubuntu")
  target_compile_options(sora_sdk_ext
    PRIVATE
      "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXX_INCLUDE_DIR}>"
  )
elseif(TARGET_OS STREQUAL "jetson")
  target_compile_options(sora_sdk_ext
    PRIVATE
      "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXX_INCLUDE_DIR}>"
  )
  target_link_directories(sora_sdk_ext PRIVATE ${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/tegra)
elseif(TARGET_OS STREQUAL "windows")
  # 文字コードを utf-8 として扱うのと、シンボルテーブル数を増やす
  target_compile_options(sora_sdk_ext PRIVATE /utf-8 /bigobj)
  # CRTライブラリを静的リンクさせる
  # MSVC_RUNTIME_LIBRARY で設定ても反映されないため CMAKE_CXX_FLAGS を用いた
  string(REPLACE "/MD" "/MT" CMAKE_CXX_FLAGS_RELEASE ${CMAKE_CXX_FLAGS_RELEASE})
  target_compile_definitions(sora_sdk_ext
    PRIVATE
      _CONSOLE
      _WIN32_WINNT=0x0A00
      NOMINMAX
      WIN32_LEAN_AND_MEAN
      HAVE_SNPRINTF
  )
endif()

# Windows 以外は OpenH264 の動的呼び出しに対応する
if (NOT TARGET_OS STREQUAL "windows")
  target_include_directories(sora_sdk_ext PRIVATE ${OPENH264_DIR}/include)
  target_sources(sora_sdk_ext
    PRIVATE
      src/dynamic_h264_decoder.cpp
      src/dynamic_h264_encoder.cpp)
endif()

target_link_libraries(sora_sdk_ext PRIVATE Sora::sora)

install(TARGETS sora_sdk_ext LIBRARY DESTINATION .)
install(
  FILES
  ${LYRA_DIR}/share/model_coeffs/lyra_config.binarypb
  ${LYRA_DIR}/share/model_coeffs/lyragan.tflite
  ${LYRA_DIR}/share/model_coeffs/quantizer.tflite
  ${LYRA_DIR}/share/model_coeffs/soundstream_encoder.tflite
  DESTINATION model_coeffs)
