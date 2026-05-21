cmake_minimum_required(VERSION 4.1)
project(sora_sdk)

# Only interpret if() arguments as variables or keywords when unquoted.
cmake_policy(SET CMP0054 NEW)
# MSVC runtime library flags are selected by an abstraction.
cmake_policy(SET CMP0091 NEW)
# find_package uses upper-case <PACKAGENAME>_ROOT variables.
cmake_policy(SET CMP0144 NEW)
# The FindBoost module is removed.
cmake_policy(SET CMP0167 NEW)
# Modules FindPython3, FindPython2 and FindPython enforce consistency of artifacts in cross-compiling mode.
# CMake 4.1 からクロスコンパイル時に FindPython する時に CMAKE_CROSSCOMPILING_EMULATOR を要求されてしまうが、
# クロスコンパイル時でもホストの Python を使うためエミュレータは不要となるので OLD に設定する
cmake_policy(SET CMP0190 OLD)

if (NOT CMAKE_CROSSCOMPILING)
  find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
endif()

if (CMAKE_CROSSCOMPILING)
  # 一時的に CMAKE_FIND_ROOT_PATH の検索モードを NEVER に設定
  # これでローカルの Python だけを検索するようになる。
  # ローカルの Python は x86_64 向けのライブラリだが、
  # クロスコンパイルすること自体に問題は無かったのでローカルの Python を使用する
  set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY NEVER)
  set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE NEVER)
  set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE NEVER)
  set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)

  find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)

  # 検索モードを元に戻す
  set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)
  set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
  set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
  set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM BOTH)
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

set(SORA_GEN_PYI ON CACHE BOOL ".pyi スタブを生成するか")
set(WEBRTC_INCLUDE_DIR "" CACHE PATH "WebRTC のインクルードディレクトリ")
set(WEBRTC_LIBRARY_DIR "" CACHE PATH "WebRTC のライブラリディレクトリ")
set(WEBRTC_LIBRARY_NAME "webrtc" CACHE STRING "WebRTC のライブラリ名")
set(Boost_ROOT "" CACHE PATH "Boost のルートディレクトリ")
set(SORA_DIR "" CACHE PATH "Sora のルートディレクトリ")

# scikit-build-core 経由のビルドで WebRTC / Sora C++ SDK / Boost / OpenH264 と
# libc++ / libc++abi ヘッダを CMake configure 時に取得する。
# 0001 では ubuntu-24.04 x86_64 ネイティブビルドのみサポートし、
# 他 platform は 0002〜0005 で順次対応する。
set(SORA_PYTHON_SDK_PLATFORM "" CACHE STRING "Sora Python SDK の platform 識別子 (例: ubuntu-24.04_x86_64)")

if(NOT EXISTS "/etc/os-release")
  message(FATAL_ERROR
    "Sora Python SDK requires /etc/os-release on the build host; not found.")
endif()
file(READ "/etc/os-release" _SORA_OS_RELEASE)

string(REGEX MATCH "(^|\n)ID=\"?([^\"\n]+)\"?" _ "${_SORA_OS_RELEASE}")
if(NOT CMAKE_MATCH_2)
  message(FATAL_ERROR "Sora Python SDK failed to parse ID from /etc/os-release.")
endif()
set(_SORA_OS_ID "${CMAKE_MATCH_2}")
if(NOT _SORA_OS_ID STREQUAL "ubuntu")
  message(FATAL_ERROR "Sora Python SDK currently supports ubuntu only; got '${_SORA_OS_ID}'.")
endif()

string(REGEX MATCH "(^|\n)VERSION_ID=\"?([^\"\n]+)\"?" _ "${_SORA_OS_RELEASE}")
if(NOT CMAKE_MATCH_2)
  message(FATAL_ERROR "Sora Python SDK failed to parse VERSION_ID from /etc/os-release.")
endif()
set(_SORA_UBUNTU_VERSION_ID "${CMAKE_MATCH_2}")

if(NOT SORA_PYTHON_SDK_PLATFORM)
  set(SORA_PYTHON_SDK_PLATFORM
    "ubuntu-${_SORA_UBUNTU_VERSION_ID}_${CMAKE_HOST_SYSTEM_PROCESSOR}"
    CACHE STRING "" FORCE)
endif()
if(NOT SORA_PYTHON_SDK_PLATFORM STREQUAL "ubuntu-24.04_x86_64")
  message(FATAL_ERROR
    "Sora Python SDK currently supports ubuntu-24.04_x86_64 only; "
    "got '${SORA_PYTHON_SDK_PLATFORM}'.")
endif()

# 0001 では ubuntu のみサポート。OpenH264 / libc++ 設定の分岐に必要な TARGET_OS は
# SORA_PYTHON_SDK_PLATFORM から派生させる。CACHE では公開しない。
set(TARGET_OS "ubuntu")

set(DEPS_ROOT "${PROJECT_SOURCE_DIR}/_deps")
include("${PROJECT_SOURCE_DIR}/cmake/scripts/fetch_deps.cmake")

# VERSION ファイルから SDK バージョンを取得する。BUILD_PROFILE=debug の場合は
# C++ 側に渡す文字列のみ +debug を末尾に連結する (Python 側 __version__ は素のまま)。
file(READ "${PROJECT_SOURCE_DIR}/VERSION" _SORA_VERSION_RAW)
string(STRIP "${_SORA_VERSION_RAW}" SORA_PYTHON_SDK_VERSION)
if(DEFINED ENV{BUILD_PROFILE} AND "$ENV{BUILD_PROFILE}" STREQUAL "debug")
  set(SORA_PYTHON_SDK_VERSION "${SORA_PYTHON_SDK_VERSION}+debug")
endif()

list(APPEND CMAKE_PREFIX_PATH ${SORA_DIR})
list(APPEND CMAKE_MODULE_PATH ${SORA_DIR}/share/cmake)

set(Boost_USE_STATIC_LIBS ON)
if(TARGET_OS STREQUAL "windows")
  set(Boost_USE_STATIC_RUNTIME ON)
endif()

find_package(Boost CONFIG REQUIRED COMPONENTS json filesystem)
find_package(WebRTC REQUIRED)
find_package(Sora REQUIRED)
find_package(nanobind CONFIG REQUIRED)
if(NOT TARGET_OS STREQUAL "windows")
  find_package(Threads REQUIRED)
endif()


nanobind_add_module(
  sora_sdk_ext
  NB_STATIC
  src/dummy_audio_mixer.cpp
  src/sora.cpp
  src/sora_audio_sink.cpp
  src/sora_audio_stream_sink.cpp
  src/sora_audio_source.cpp
  src/sora_connection.cpp
  src/sora_factory.cpp
  src/sora_log.cpp
  src/sora_sdk_ext.cpp
  src/sora_vad.cpp
  src/sora_video_sink.cpp
  src/sora_video_source.cpp
)

if (SORA_GEN_PYI)
  nanobind_add_stub(
    sora_sdk_ext_stub
    MODULE sora_sdk_ext
    OUTPUT sora_sdk_ext.pyi
    PYTHON_PATH $<TARGET_FILE_DIR:sora_sdk_ext>
    DEPENDS sora_sdk_ext
    MARKER_FILE py.typed
  )
endif()

target_compile_definitions(sora_sdk_ext PRIVATE "SORA_PYTHON_SDK_VERSION=\"${SORA_PYTHON_SDK_VERSION}\"")

set_target_properties(sora_sdk_ext PROPERTIES CXX_STANDARD 20 C_STANDARD 20)
set_target_properties(sora_sdk_ext PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(TARGET_OS STREQUAL "macos")
  set_target_properties(sora_sdk_ext PROPERTIES CXX_VISIBILITY_PRESET hidden)
  # Boost 1.91.0 では macOS 14.4 以降で Asio の kqueue_reactor が
  # std::atomic::wait ベースの atomic_slim_mutex を使うようになった。
  # Sora C++ SDK はこれを無効化しているため、 Sora Python SDK 側でも同じマクロを定義する。
  # 定義がずれると Boost.Asio の内部実装が食い違い、接続時にクラッシュやハングが発生する可能性がある。
  target_compile_definitions(sora_sdk_ext
    PRIVATE
      BOOST_ASIO_DISABLE_STD_ATOMIC_WAIT
  )
  target_compile_options(sora_sdk_ext
    PRIVATE
      "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXX_INCLUDE_DIR}>"
  )
  target_compile_options(nanobind-static
    PRIVATE
      "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXX_INCLUDE_DIR}>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXXABI_INCLUDE_DIR}>"
  )
elseif(TARGET_OS STREQUAL "ubuntu")
  target_compile_options(sora_sdk_ext
    PRIVATE
      "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXX_INCLUDE_DIR}>"
  )
  target_compile_options(nanobind-static
    PRIVATE
      "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXX_INCLUDE_DIR}>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXXABI_INCLUDE_DIR}>"
  )
elseif(TARGET_OS STREQUAL "jetson")
  target_compile_options(sora_sdk_ext
    PRIVATE
      "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXX_INCLUDE_DIR}>"
  )
  target_compile_options(nanobind-static
    PRIVATE
      "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXX_INCLUDE_DIR}>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXXABI_INCLUDE_DIR}>"
  )
  target_link_directories(sora_sdk_ext
    PRIVATE
      ${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/tegra
      ${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/nvidia)
elseif(TARGET_OS STREQUAL "raspberry-pi-os")
  target_compile_options(sora_sdk_ext
    PRIVATE
      "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXX_INCLUDE_DIR}>"
  )
  target_compile_options(nanobind-static
    PRIVATE
      "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXX_INCLUDE_DIR}>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXXABI_INCLUDE_DIR}>"
  )
  target_compile_definitions(sora_sdk_ext PRIVATE USE_V4L2=1)
  set_target_properties(sora_sdk_ext PROPERTIES BUILD_RPATH "\$ORIGIN")
elseif(TARGET_OS STREQUAL "windows")
  # 文字コードを utf-8 として扱うのと、シンボルテーブル数を増やす
  target_compile_options(sora_sdk_ext PRIVATE /utf-8 /bigobj)
  # CRTライブラリを静的リンクさせる
  set_property(TARGET sora_sdk_ext PROPERTY
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  set_property(TARGET nanobind-static PROPERTY
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
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
target_link_libraries(nanobind-static PRIVATE Sora::sora)

install(TARGETS sora_sdk_ext LIBRARY DESTINATION sora_sdk)
if (SORA_GEN_PYI)
  install(FILES
    "${CMAKE_CURRENT_BINARY_DIR}/py.typed"
    "${CMAKE_CURRENT_BINARY_DIR}/sora_sdk_ext.pyi"
    DESTINATION sora_sdk)
endif()
