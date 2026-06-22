# fetch_deps.cmake
#
# `CMAKE_PROJECT_TOP_LEVEL_INCLUDES` 経由で `project()` の中（言語有効化前）に呼ばれる。
# WebRTC / Sora C++ SDK / Boost / OpenH264 / LLVM の取得を CMake configure 時に完結させる。

# 入力: Python_EXECUTABLE は scikit-build-core が CMakeInit.txt 経由で渡してくる
if(NOT Python_EXECUTABLE)
  message(FATAL_ERROR
    "Python_EXECUTABLE must be provided by scikit-build-core. "
    "Run via 'uv build --wheel' instead of invoking cmake directly.")
endif()

# DEPS_ROOT は repository root 配下の _deps
set(DEPS_ROOT "${CMAKE_SOURCE_DIR}/_deps")

# SORA_PYTHON_SDK_PLATFORM 自動検出（未設定時のみ）
if(NOT SORA_PYTHON_SDK_PLATFORM)
  if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux")
    if(NOT EXISTS "/etc/os-release")
      message(FATAL_ERROR "/etc/os-release not found; cannot detect platform")
    endif()
    file(READ "/etc/os-release" _OS_RELEASE)
    string(REPLACE "\n" ";" _OS_LINES "${_OS_RELEASE}")
    set(_OS_ID "")
    set(_OS_VERSION_ID "")
    foreach(_line IN LISTS _OS_LINES)
      if(_line MATCHES "^ID=\"?([^\"]+)\"?$")
        set(_OS_ID "${CMAKE_MATCH_1}")
      elseif(_line MATCHES "^VERSION_ID=\"?([^\"]+)\"?$")
        set(_OS_VERSION_ID "${CMAKE_MATCH_1}")
      endif()
    endforeach()
    if(NOT _OS_ID STREQUAL "ubuntu")
      message(FATAL_ERROR
        "Linux host must be ubuntu; got ID='${_OS_ID}' from /etc/os-release")
    endif()
    if(NOT _OS_VERSION_ID)
      message(FATAL_ERROR "Failed to read VERSION_ID from /etc/os-release")
    endif()
    set(SORA_PYTHON_SDK_PLATFORM
      "ubuntu-${_OS_VERSION_ID}_${CMAKE_HOST_SYSTEM_PROCESSOR}"
      CACHE STRING "" FORCE)
  elseif(CMAKE_HOST_SYSTEM_NAME STREQUAL "Darwin")
    # Xcode Command Line Tools 不在を早期に検出する。
    find_program(_XCRUN_EXECUTABLE xcrun NO_CACHE)
    if(NOT _XCRUN_EXECUTABLE)
      message(FATAL_ERROR
        "Xcode Command Line Tools not found. "
        "Run 'xcode-select --install' in a terminal and re-run the build.")
    endif()
    # Rosetta 経由で起動した CMake は x86_64-Darwin を返すため、 arm64 host のみ通す。
    if(NOT CMAKE_HOST_SYSTEM_PROCESSOR STREQUAL "arm64")
      message(FATAL_ERROR
        "macOS host must be arm64; got '${CMAKE_HOST_SYSTEM_PROCESSOR}'. "
        "macOS x86_64 is not supported.")
    endif()
    set(SORA_PYTHON_SDK_PLATFORM "macos_arm64" CACHE STRING "" FORCE)
  elseif(CMAKE_HOST_SYSTEM_NAME STREQUAL "Windows")
    # Windows 上の CMake 64-bit 版では通常 AMD64 を返す。x86_64 を許容するのは、
    # 一部ツールチェーンやクロスコンパイル環境で x86_64 が返る可能性に備えるため。
    if(CMAKE_HOST_SYSTEM_PROCESSOR MATCHES "^(AMD64|x86_64)$")
      set(SORA_PYTHON_SDK_PLATFORM "windows_x86_64" CACHE STRING "" FORCE)
    else()
      message(FATAL_ERROR
        "Windows host must be x86_64; got '${CMAKE_HOST_SYSTEM_PROCESSOR}'. "
        "Windows arm64 / x86 are not supported.")
    endif()
  else()
    message(FATAL_ERROR
      "Unsupported host: '${CMAKE_HOST_SYSTEM_NAME}'. "
      "Supported hosts: Linux (ubuntu only), Darwin (arm64 only), Windows (x86_64 only).")
  endif()
endif()

# 許容リスト検証
set(_SORA_ALLOWED_PLATFORMS "ubuntu-24.04_x86_64" "macos_arm64" "windows_x86_64")
list(FIND _SORA_ALLOWED_PLATFORMS "${SORA_PYTHON_SDK_PLATFORM}" _SORA_PLATFORM_INDEX)
if(_SORA_PLATFORM_INDEX EQUAL -1)
  message(FATAL_ERROR
    "Unsupported SORA_PYTHON_SDK_PLATFORM='${SORA_PYTHON_SDK_PLATFORM}'. "
    "Supported: ubuntu-24.04_x86_64, macos_arm64, windows_x86_64.")
endif()

# 排他ロック取得（複数 Python ABI 並列ビルド時の _deps/<platform>/ 競合回避）
file(MAKE_DIRECTORY "${DEPS_ROOT}")
file(LOCK "${DEPS_ROOT}/.fetch.lock" GUARD PROCESS TIMEOUT 1800)

# パス計算
set(_PLATFORM_ROOT "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}")
set(_STAMPS_ROOT "${_PLATFORM_ROOT}/.stamps")
file(MAKE_DIRECTORY "${_PLATFORM_ROOT}" "${_STAMPS_ROOT}")

if(NOT WIN32)
  set(_LLVM_HOST_KEY "${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}")
  set(_LLVM_ROOT "${DEPS_ROOT}/llvm/${_LLVM_HOST_KEY}")
  set(_LLVM_STAMPS_ROOT "${_LLVM_ROOT}/.stamps")
  file(MAKE_DIRECTORY "${_LLVM_ROOT}" "${_LLVM_STAMPS_ROOT}")
endif()

# ---------- ヘルパ関数 ----------

# git shallow clone（buildbase.py:git_clone_shallow と等価）
function(_sora_git_shallow url ref dest)
  file(REMOVE_RECURSE "${dest}")
  file(MAKE_DIRECTORY "${dest}")
  set(_attempt 0)
  set(_max_attempts 3)
  while(_attempt LESS _max_attempts)
    math(EXPR _attempt "${_attempt} + 1")
    execute_process(
      COMMAND git init
      WORKING_DIRECTORY "${dest}"
      RESULT_VARIABLE _r OUTPUT_QUIET ERROR_QUIET)
    if(NOT _r EQUAL 0)
      file(REMOVE_RECURSE "${dest}")
      file(MAKE_DIRECTORY "${dest}")
      execute_process(COMMAND ${CMAKE_COMMAND} -E sleep 1)
      continue()
    endif()
    execute_process(
      COMMAND git remote add origin "${url}"
      WORKING_DIRECTORY "${dest}"
      OUTPUT_QUIET ERROR_QUIET)
    execute_process(
      COMMAND git fetch --depth=1 origin "${ref}"
      WORKING_DIRECTORY "${dest}"
      RESULT_VARIABLE _r OUTPUT_QUIET ERROR_QUIET)
    if(_r EQUAL 0)
      execute_process(
        COMMAND git reset --hard FETCH_HEAD
        WORKING_DIRECTORY "${dest}"
        RESULT_VARIABLE _r OUTPUT_QUIET ERROR_QUIET)
      if(_r EQUAL 0)
        return()
      endif()
    endif()
    file(REMOVE_RECURSE "${dest}")
    file(MAKE_DIRECTORY "${dest}")
    execute_process(COMMAND ${CMAKE_COMMAND} -E sleep 1)
  endwhile()
  message(FATAL_ERROR
    "Failed to git fetch ${url} at ${ref} after ${_max_attempts} retries. "
    "Check network connectivity or HTTPS_PROXY.")
endfunction()

# tar.gz / zip アーカイブの取得 + 展開 + stamp 書き込み
function(_sora_fetch_archive name url stamp_path dest_dir strip_components ext)
  # sha256 検証を導入する際の受け口（現時点では値を渡さない）
  cmake_parse_arguments(_arg "" "SHA256" "" ${ARGN})

  if(EXISTS "${stamp_path}")
    file(READ "${stamp_path}" _existing)
    string(STRIP "${_existing}" _existing)
    if(_existing STREQUAL "${url}")
      message(STATUS "Sora deps: ${name} cache hit (${url})")
      return()
    endif()
  endif()

  message(STATUS "Sora deps: fetching ${name} from ${url}")
  if(EXISTS "${dest_dir}")
    # Windows ではアーカイブ内の読み取り専用ファイルが残っていると削除に失敗するため、
    # 事前に書き込み権限を付与してから削除する。
    if(WIN32)
      file(CHMOD_RECURSE "${dest_dir}" PERMISSIONS OWNER_WRITE GROUP_WRITE WORLD_WRITE)
    endif()
    file(REMOVE_RECURSE "${dest_dir}")
  endif()
  file(MAKE_DIRECTORY "${dest_dir}")
  get_filename_component(_stamp_parent "${stamp_path}" DIRECTORY)
  file(MAKE_DIRECTORY "${_stamp_parent}")
  set(_archive_dir "${_stamp_parent}/.archives")
  file(MAKE_DIRECTORY "${_archive_dir}")
  set(_archive "${_archive_dir}/${name}.${ext}")

  set(_attempt 0)
  set(_max_attempts 3)
  set(_success FALSE)
  while(_attempt LESS _max_attempts)
    math(EXPR _attempt "${_attempt} + 1")
    file(REMOVE "${_archive}")
    file(DOWNLOAD "${url}" "${_archive}"
      TLS_VERIFY ON
      INACTIVITY_TIMEOUT 120
      TIMEOUT 1800
      STATUS _dl_status)
    list(GET _dl_status 0 _dl_code)
    if(_dl_code EQUAL 0)
      set(_success TRUE)
      break()
    endif()
    list(GET _dl_status 1 _dl_msg)
    message(WARNING "Sora deps: download ${name} failed (${_dl_code}: ${_dl_msg}), retrying")
    execute_process(COMMAND ${CMAKE_COMMAND} -E sleep 1)
  endwhile()
  if(NOT _success)
    file(REMOVE "${_archive}")
    message(FATAL_ERROR
      "Failed to download ${name} from ${url} after ${_max_attempts} retries.")
  endif()

  if(_arg_SHA256)
    file(SHA256 "${_archive}" _actual_sha256)
    if(NOT _actual_sha256 STREQUAL "${_arg_SHA256}")
      file(REMOVE "${_archive}")
      message(FATAL_ERROR
        "SHA256 mismatch for ${name}. "
        "Expected: ${_arg_SHA256}. Actual: ${_actual_sha256}.")
    endif()
  endif()

  # CMake の `cmake -E tar` は --strip-components をサポートしていないため system tar を使う。
  # Windows では Git for Windows 同梱の GNU tar が zip を展開できないため、
  # OS 標準の tar.exe（bsdtar / libarchive）を優先して探す。
  if(WIN32)
    find_program(_SORA_TAR_EXECUTABLE NAMES tar
      PATHS "$ENV{SystemRoot}/System32" "C:/Windows/System32"
      NO_DEFAULT_PATH NO_CACHE)
  else()
    find_program(_SORA_TAR_EXECUTABLE NAMES tar NO_CACHE)
  endif()
  if(NOT _SORA_TAR_EXECUTABLE)
    message(FATAL_ERROR
      "tar command is required to extract archives. "
      "On Debian/Ubuntu: it ships with the base system; "
      "on Windows 10+: it ships with the OS.")
  endif()

  if(ext STREQUAL "zip")
    execute_process(
      COMMAND "${_SORA_TAR_EXECUTABLE}" -xf "${_archive}"
              "--strip-components=${strip_components}" -C "${dest_dir}"
      RESULT_VARIABLE _extract_result)
  elseif(ext STREQUAL "tar.gz")
    execute_process(
      COMMAND "${_SORA_TAR_EXECUTABLE}" -xzf "${_archive}"
              "--strip-components=${strip_components}" -C "${dest_dir}"
      RESULT_VARIABLE _extract_result)
  else()
    message(FATAL_ERROR "Unsupported archive extension: ${ext}")
  endif()

  if(NOT _extract_result EQUAL 0)
    file(REMOVE_RECURSE "${dest_dir}")
    message(FATAL_ERROR "Failed to extract ${name} archive: ${_archive}")
  endif()

  file(WRITE "${stamp_path}" "${url}")
endfunction()

# OpenH264 ヘッダ取得（git clone + make install-headers）
# Windows では CMakeLists.txt で OpenH264 動的呼び出しを無効にしているため使用しない。
function(_sora_fetch_openh264 version git_url dest stamp_path)
  if(EXISTS "${stamp_path}")
    file(READ "${stamp_path}" _existing)
    string(STRIP "${_existing}" _existing)
    if(_existing STREQUAL "${version}")
      message(STATUS "Sora deps: openh264 cache hit (${version})")
      return()
    endif()
  endif()

  find_program(_SORA_MAKE_EXECUTABLE make NO_CACHE)
  if(NOT _SORA_MAKE_EXECUTABLE)
    message(FATAL_ERROR
      "OpenH264 header installation requires 'make'. "
      "On Debian/Ubuntu: run 'apt-get install build-essential'.")
  endif()

  message(STATUS "Sora deps: fetching openh264 ${version} from ${git_url}")
  file(REMOVE_RECURSE "${dest}")
  get_filename_component(_dest_parent "${dest}" DIRECTORY)
  set(_src "${_dest_parent}/.openh264-src")
  file(REMOVE_RECURSE "${_src}")
  _sora_git_shallow("${git_url}" "${version}" "${_src}")

  file(MAKE_DIRECTORY "${dest}")
  execute_process(
    COMMAND "${_SORA_MAKE_EXECUTABLE}" -C "${_src}" install-headers "PREFIX=${dest}"
    RESULT_VARIABLE _make_result)
  if(NOT _make_result EQUAL 0)
    file(REMOVE_RECURSE "${dest}" "${_src}")
    message(FATAL_ERROR "Failed to install openh264 headers (make install-headers PREFIX=${dest})")
  endif()

  file(REMOVE_RECURSE "${_src}")
  get_filename_component(_stamp_parent "${stamp_path}" DIRECTORY)
  file(MAKE_DIRECTORY "${_stamp_parent}")
  file(WRITE "${stamp_path}" "${version}")
endfunction()

# LLVM 取得（buildbase.py:install_llvm 移植）
function(_sora_fetch_llvm webrtc_install_dir dest_root stamp_path)
  set(_versions_file "${webrtc_install_dir}/VERSIONS")
  if(NOT EXISTS "${_versions_file}")
    message(FATAL_ERROR "WebRTC VERSIONS file not found: ${_versions_file}")
  endif()
  file(READ "${_versions_file}" _versions_content)
  string(REPLACE "\n" ";" _version_lines "${_versions_content}")

  set(_required_keys
    WEBRTC_SRC_TOOLS_URL
    WEBRTC_SRC_TOOLS_COMMIT
    WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL
    WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT
    WEBRTC_SRC_BUILDTOOLS_URL
    WEBRTC_SRC_BUILDTOOLS_COMMIT)

  foreach(_key IN LISTS _required_keys)
    set(_${_key} "")
  endforeach()

  foreach(_line IN LISTS _version_lines)
    foreach(_key IN LISTS _required_keys)
      if(_line MATCHES "^${_key}=\"?([^\"]+)\"?$")
        set(_${_key} "${CMAKE_MATCH_1}")
      endif()
    endforeach()
  endforeach()

  foreach(_key IN LISTS _required_keys)
    if(NOT _${_key})
      message(FATAL_ERROR "Required key ${_key} not found in ${_versions_file}")
    endif()
  endforeach()

  set(_stamp_value
    "${_WEBRTC_SRC_TOOLS_URL}.${_WEBRTC_SRC_TOOLS_COMMIT}.${_WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL}.${_WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT}.${_WEBRTC_SRC_BUILDTOOLS_URL}.${_WEBRTC_SRC_BUILDTOOLS_COMMIT}")

  if(EXISTS "${stamp_path}")
    file(READ "${stamp_path}" _existing)
    string(STRIP "${_existing}" _existing)
    if(_existing STREQUAL "${_stamp_value}")
      message(STATUS "Sora deps: llvm cache hit")
      return()
    endif()
  endif()

  message(STATUS "Sora deps: fetching llvm (clang + libcxx headers)")
  file(REMOVE_RECURSE
    "${dest_root}/clang"
    "${dest_root}/libcxx"
    "${dest_root}/buildtools"
    "${dest_root}/tools")

  _sora_git_shallow("${_WEBRTC_SRC_TOOLS_URL}" "${_WEBRTC_SRC_TOOLS_COMMIT}" "${dest_root}/tools")

  execute_process(
    COMMAND "${Python_EXECUTABLE}"
      "${dest_root}/tools/clang/scripts/update.py"
      "--output-dir" "${dest_root}/clang"
    WORKING_DIRECTORY "${dest_root}/tools"
    RESULT_VARIABLE _update_result)
  if(NOT _update_result EQUAL 0)
    message(FATAL_ERROR
      "clang/scripts/update.py failed (output-dir=${dest_root}/clang)")
  endif()

  _sora_git_shallow("${_WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL}" "${_WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT}" "${dest_root}/libcxx")
  _sora_git_shallow("${_WEBRTC_SRC_BUILDTOOLS_URL}" "${_WEBRTC_SRC_BUILDTOOLS_COMMIT}" "${dest_root}/buildtools")

  configure_file(
    "${dest_root}/buildtools/third_party/libc++/__config_site"
    "${dest_root}/libcxx/include/__config_site"
    COPYONLY)
  configure_file(
    "${dest_root}/buildtools/third_party/libc++/__assertion_handler"
    "${dest_root}/libcxx/include/__assertion_handler"
    COPYONLY)

  file(REMOVE_RECURSE "${dest_root}/tools" "${dest_root}/buildtools")

  get_filename_component(_stamp_parent "${stamp_path}" DIRECTORY)
  file(MAKE_DIRECTORY "${_stamp_parent}")
  file(WRITE "${stamp_path}" "${_stamp_value}")
endfunction()

# ---------- メインスクリプト ----------

# deps.json を読む
file(READ "${CMAKE_SOURCE_DIR}/deps.json" _DEPS_JSON)
string(JSON _WEBRTC_VERSION GET "${_DEPS_JSON}" webrtc version)
string(JSON _WEBRTC_URL_TEMPLATE GET "${_DEPS_JSON}" webrtc url_template)
string(JSON _WEBRTC_STRIP GET "${_DEPS_JSON}" webrtc strip_components)
string(JSON _SORA_VERSION GET "${_DEPS_JSON}" sora_cpp_sdk version)
string(JSON _SORA_URL_TEMPLATE GET "${_DEPS_JSON}" sora_cpp_sdk url_template)
string(JSON _SORA_STRIP GET "${_DEPS_JSON}" sora_cpp_sdk strip_components)
string(JSON _BOOST_VERSION GET "${_DEPS_JSON}" boost version)
string(JSON _BOOST_URL_TEMPLATE GET "${_DEPS_JSON}" boost url_template)
string(JSON _BOOST_STRIP GET "${_DEPS_JSON}" boost strip_components)
string(JSON _OPENH264_VERSION GET "${_DEPS_JSON}" openh264 version)
string(JSON _OPENH264_GIT GET "${_DEPS_JSON}" openh264 git)

# URL テンプレート展開
# {sora_version} を先に置換しないと {sora_version} 内の {version} 部分が誤置換される
# 置換順序: {sora_version} → {version} → {platform} → {ext}
macro(_sora_expand_url out template version sora_version platform ext)
  set(${out} "${template}")
  string(REPLACE "{sora_version}" "${sora_version}" ${out} "${${out}}")
  string(REPLACE "{version}" "${version}" ${out} "${${out}}")
  string(REPLACE "{platform}" "${platform}" ${out} "${${out}}")
  string(REPLACE "{ext}" "${ext}" ${out} "${${out}}")
endmacro()

# Windows ではアーカイブ拡張子が .zip、それ以外では .tar.gz となる
if(WIN32)
  set(_EXT "zip")
else()
  set(_EXT "tar.gz")
endif()

# WebRTC 取得（LLVM が webrtc/VERSIONS を参照するため最初）
_sora_expand_url(_WEBRTC_URL "${_WEBRTC_URL_TEMPLATE}" "${_WEBRTC_VERSION}" "" "${SORA_PYTHON_SDK_PLATFORM}" "${_EXT}")
_sora_fetch_archive(webrtc "${_WEBRTC_URL}" "${_STAMPS_ROOT}/webrtc" "${_PLATFORM_ROOT}/webrtc" ${_WEBRTC_STRIP} "${_EXT}")

# Sora C++ SDK 取得
_sora_expand_url(_SORA_URL "${_SORA_URL_TEMPLATE}" "${_SORA_VERSION}" "" "${SORA_PYTHON_SDK_PLATFORM}" "${_EXT}")
_sora_fetch_archive(sora "${_SORA_URL}" "${_STAMPS_ROOT}/sora" "${_PLATFORM_ROOT}/sora" ${_SORA_STRIP} "${_EXT}")

# Boost 取得
_sora_expand_url(_BOOST_URL "${_BOOST_URL_TEMPLATE}" "${_BOOST_VERSION}" "${_SORA_VERSION}" "${SORA_PYTHON_SDK_PLATFORM}" "${_EXT}")
_sora_fetch_archive(boost "${_BOOST_URL}" "${_STAMPS_ROOT}/boost" "${_PLATFORM_ROOT}/boost" ${_BOOST_STRIP} "${_EXT}")

# OpenH264 取得
# Windows では CMakeLists.txt で OpenH264 動的呼び出しを無効にしているため skip する
if(NOT WIN32)
  _sora_fetch_openh264("${_OPENH264_VERSION}" "${_OPENH264_GIT}" "${_PLATFORM_ROOT}/openh264" "${_STAMPS_ROOT}/openh264")
endif()

# LLVM 取得
# Windows では MSVC を使用するため LLVM 取得は不要
if(NOT WIN32)
  _sora_fetch_llvm("${_PLATFORM_ROOT}/webrtc" "${_LLVM_ROOT}" "${_LLVM_STAMPS_ROOT}/llvm")
endif()

# 出力契約 8 変数を CACHE PATH で確定
set(SORA_DIR              "${_PLATFORM_ROOT}/sora"     CACHE PATH "" FORCE)
set(Boost_ROOT            "${_PLATFORM_ROOT}/boost"    CACHE PATH "" FORCE)
set(WEBRTC_INCLUDE_DIR    "${_PLATFORM_ROOT}/webrtc/include" CACHE PATH "" FORCE)
set(WEBRTC_LIBRARY_DIR    "${_PLATFORM_ROOT}/webrtc/lib"     CACHE PATH "" FORCE)

if(NOT WIN32)
  set(OPENH264_DIR          "${_PLATFORM_ROOT}/openh264"       CACHE PATH "" FORCE)
  set(LIBCXX_INCLUDE_DIR    "${_LLVM_ROOT}/libcxx/include"     CACHE PATH "" FORCE)
  set(LIBCXXABI_INCLUDE_DIR "${_PLATFORM_ROOT}/webrtc/include/third_party/libc++abi/src/include" CACHE PATH "" FORCE)
  set(_SORA_CLANG_DIR       "${_LLVM_ROOT}/clang"              CACHE PATH "" FORCE)
endif()

# コンパイラを LLVM 同梱 clang に確定（同じ値の連続 FORCE で cache invalidation が発火するのを避けるためガード付き）
if(NOT WIN32)
  set(_EXPECTED_CLANG   "${_SORA_CLANG_DIR}/bin/clang")
  set(_EXPECTED_CLANGXX "${_SORA_CLANG_DIR}/bin/clang++")
  if(NOT CMAKE_C_COMPILER STREQUAL "${_EXPECTED_CLANG}")
    set(CMAKE_C_COMPILER "${_EXPECTED_CLANG}" CACHE FILEPATH "" FORCE)
  endif()
  if(NOT CMAKE_CXX_COMPILER STREQUAL "${_EXPECTED_CLANGXX}")
    set(CMAKE_CXX_COMPILER "${_EXPECTED_CLANGXX}" CACHE FILEPATH "" FORCE)
  endif()
endif()
