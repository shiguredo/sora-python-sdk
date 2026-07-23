# fetch_deps.cmake
# CMAKE_PROJECT_TOP_LEVEL_INCLUDES 経由で project() 内に実行される。
# WebRTC / Sora C++ SDK / Boost / OpenH264 / LLVM を CMake configure 時に取得する。

# ---------------------------------------------------------------------------
# Python_EXECUTABLE ガード
# scikit-build-core が CMakeInit.txt 経由で注入する。
# 手動 cmake configure では設定されないため即座に失敗させる。
# ---------------------------------------------------------------------------
if(NOT Python_EXECUTABLE)
  message(FATAL_ERROR
    "[fetch_deps] Python_EXECUTABLE is not set. "
    "Use 'uv build --wheel' instead of running cmake directly.")
endif()

# ---------------------------------------------------------------------------
# KEY=value パーサ
# DEPS / VERSIONS / /etc/os-release で共通に使う。
# KEY="value" のクォートも除去する。
# ---------------------------------------------------------------------------
function(_sora_kv_get content key out_var)
  string(REPLACE "\n" ";" _lines "${content}")
  foreach(_line IN LISTS _lines)
    string(STRIP "${_line}" _line)
    if(_line MATCHES "^${key}=\"?([^\"]*)\"?$")
      set(${out_var} "${CMAKE_MATCH_1}" PARENT_SCOPE)
      return()
    endif()
  endforeach()
  set(${out_var} "" PARENT_SCOPE)
endfunction()

# ---------------------------------------------------------------------------
# SORA_PYTHON_SDK_PLATFORM の自動検出と許容リスト検証
# 未設定時のみ /etc/os-release から算出する。
# 許容リスト検証は明示指定時も含め常に実行する。
# ---------------------------------------------------------------------------
set(_SORA_ALLOWED_PLATFORMS "ubuntu-24.04_x86_64")

if(NOT SORA_PYTHON_SDK_PLATFORM)
  # Linux 以外は未対応
  if(NOT CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux")
    message(FATAL_ERROR
      "[fetch_deps] Unsupported host OS: ${CMAKE_HOST_SYSTEM_NAME}. "
      "Only Linux is currently supported.")
  endif()

  # /etc/os-release から ID / VERSION_ID を抽出する
  if(NOT EXISTS "/etc/os-release")
    message(FATAL_ERROR "[fetch_deps] /etc/os-release not found")
  endif()
  file(READ "/etc/os-release" _os_release_content)
  _sora_kv_get("${_os_release_content}" "ID" _os_id)
  _sora_kv_get("${_os_release_content}" "VERSION_ID" _os_version_id)

  if(NOT _os_id STREQUAL "ubuntu")
    message(FATAL_ERROR
      "[fetch_deps] Unsupported distribution: ${_os_id}. Only ubuntu is supported.")
  endif()

  set(SORA_PYTHON_SDK_PLATFORM "ubuntu-${_os_version_id}_${CMAKE_HOST_SYSTEM_PROCESSOR}"
    CACHE STRING "" FORCE)
  message(STATUS "[fetch_deps] Detected platform: ${SORA_PYTHON_SDK_PLATFORM}")
endif()

# 許容リスト検証（バイパスは認めない）
if(NOT SORA_PYTHON_SDK_PLATFORM IN_LIST _SORA_ALLOWED_PLATFORMS)
  message(FATAL_ERROR
    "[fetch_deps] Platform '${SORA_PYTHON_SDK_PLATFORM}' is not in the allowed list: "
    "${_SORA_ALLOWED_PLATFORMS}")
endif()

# ---------------------------------------------------------------------------
# ディレクトリレイアウト
# ---------------------------------------------------------------------------
set(DEPS_ROOT "${CMAKE_SOURCE_DIR}/_deps")
set(_platform_dir "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}")
set(_archive_dir "${_platform_dir}/.archives")
set(_extract_dir "${_platform_dir}/.extract")
set(_stamp_dir "${_platform_dir}/.stamps")
set(_host_key "${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}")
set(_llvm_dir "${DEPS_ROOT}/llvm/${_host_key}")
set(_llvm_stamp_dir "${_llvm_dir}/.stamps")

file(MAKE_DIRECTORY "${DEPS_ROOT}")

# ---------------------------------------------------------------------------
# 排他ロック
# 複数 Python ABI 並列ビルド時の _deps/<platform>/ への同時書き込みを回避する。
# process 終了で自動 release される。
# ---------------------------------------------------------------------------
file(LOCK "${DEPS_ROOT}/.fetch.lock" GUARD PROCESS TIMEOUT 3600)

# ---------------------------------------------------------------------------
# DEPS のパース
# ---------------------------------------------------------------------------
set(_deps_file "${CMAKE_SOURCE_DIR}/DEPS")
if(NOT EXISTS "${_deps_file}")
  message(FATAL_ERROR "[fetch_deps] DEPS file not found: ${_deps_file}")
endif()
file(READ "${_deps_file}" _deps_content)

_sora_kv_get("${_deps_content}" "SORA_CPP_SDK_VERSION" _sora_cpp_sdk_version)
_sora_kv_get("${_deps_content}" "WEBRTC_BUILD_VERSION" _webrtc_build_version)
_sora_kv_get("${_deps_content}" "BOOST_VERSION" _boost_version)
_sora_kv_get("${_deps_content}" "OPENH264_VERSION" _openh264_version)

# 4 キーの存在を検証
if(NOT _sora_cpp_sdk_version)
  message(FATAL_ERROR "[fetch_deps] Missing required key in DEPS: SORA_CPP_SDK_VERSION")
endif()
if(NOT _webrtc_build_version)
  message(FATAL_ERROR "[fetch_deps] Missing required key in DEPS: WEBRTC_BUILD_VERSION")
endif()
if(NOT _boost_version)
  message(FATAL_ERROR "[fetch_deps] Missing required key in DEPS: BOOST_VERSION")
endif()
if(NOT _openh264_version)
  message(FATAL_ERROR "[fetch_deps] Missing required key in DEPS: OPENH264_VERSION")
endif()

# ダウンロード URL の組み立て
set(_webrtc_url "https://github.com/shiguredo-webrtc-build/webrtc-build/releases/download/${_webrtc_build_version}/webrtc.${SORA_PYTHON_SDK_PLATFORM}.tar.gz")
set(_sora_url "https://github.com/shiguredo/sora-cpp-sdk/releases/download/${_sora_cpp_sdk_version}/sora-cpp-sdk-${_sora_cpp_sdk_version}_${SORA_PYTHON_SDK_PLATFORM}.tar.gz")
set(_boost_url "https://github.com/shiguredo/sora-cpp-sdk/releases/download/${_sora_cpp_sdk_version}/boost-${_boost_version}_sora-cpp-sdk-${_sora_cpp_sdk_version}_${SORA_PYTHON_SDK_PLATFORM}.tar.gz")
set(_openh264_git_url "https://github.com/cisco/openh264.git")

# ---------------------------------------------------------------------------
# _sora_fetch_archive
# アーカイブのダウンロード・展開・stamp 管理を行う。
# SHA256 キーワード引数の受け口を用意する（現時点では未使用）。
# ---------------------------------------------------------------------------
function(_sora_fetch_archive name url stamp_path dest_dir)
  cmake_parse_arguments(_arg "" "SHA256" "" ${ARGN})

  # stamp が url と一致したら skip
  if(EXISTS "${stamp_path}")
    file(READ "${stamp_path}" _stamp_content)
    string(STRIP "${_stamp_content}" _stamp_content)
    if(_stamp_content STREQUAL "${url}")
      message(STATUS "[fetch_deps] ${name}: up-to-date, skipping")
      return()
    endif()
  endif()

  # 旧 stamp を削除（取得失敗時に旧 stamp が残って空の dest を指すのを防ぐ）
  file(REMOVE "${stamp_path}")

  # ダウンロード
  file(MAKE_DIRECTORY "${_archive_dir}")
  set(_archive_path "${_archive_dir}/${name}.tar.gz")

  set(_retry 0)
  set(_ok FALSE)
  while(NOT _ok AND _retry LESS 3)
    if(_retry GREATER 0)
      message(STATUS "[fetch_deps] ${name}: download retry ${_retry}/2")
      execute_process(COMMAND "${CMAKE_COMMAND}" -E sleep 1)
    endif()
    file(DOWNLOAD "${url}" "${_archive_path}"
      INACTIVITY_TIMEOUT 120
      STATUS _dl_status
    )
    list(GET _dl_status 0 _dl_code)
    if(_dl_code EQUAL 0)
      set(_ok TRUE)
    else()
      list(GET _dl_status 1 _dl_msg)
      message(WARNING "[fetch_deps] ${name}: download failed: ${_dl_msg}")
      file(REMOVE "${_archive_path}")
      math(EXPR _retry "${_retry}+1")
    endif()
  endwhile()

  if(NOT _ok)
    message(FATAL_ERROR "[fetch_deps] ${name}: download failed after 3 attempts: ${url}")
  endif()

  # 展開
  set(_tmp_dir "${_extract_dir}/${name}")
  file(REMOVE_RECURSE "${_tmp_dir}")
  file(MAKE_DIRECTORY "${_tmp_dir}")
  file(ARCHIVE_EXTRACT INPUT "${_archive_path}" DESTINATION "${_tmp_dir}")

  # 単一トップディレクトリならそれを dest_dir に移動、そうでなければ tmp 自体を移動
  get_filename_component(_dest_parent "${dest_dir}" DIRECTORY)
  file(MAKE_DIRECTORY "${_dest_parent}")
  file(REMOVE_RECURSE "${dest_dir}")

  file(GLOB _entries "${_tmp_dir}/*")
  list(LENGTH _entries _count)
  if(_count EQUAL 1)
    list(GET _entries 0 _single)
    if(IS_DIRECTORY "${_single}")
      file(RENAME "${_single}" "${dest_dir}")
    else()
      file(RENAME "${_tmp_dir}" "${dest_dir}")
    endif()
  else()
    file(RENAME "${_tmp_dir}" "${dest_dir}")
  endif()

  # 一時ディレクトリのクリーンアップ
  file(REMOVE_RECURSE "${_tmp_dir}")

  # stamp 書き込み
  file(MAKE_DIRECTORY "${_stamp_dir}")
  file(WRITE "${stamp_path}" "${url}\n")

  message(STATUS "[fetch_deps] ${name}: done")
endfunction()

# ---------------------------------------------------------------------------
# _sora_git_shallow
# git init → remote add → fetch --depth=1 → reset --hard で浅く clone する。
# git clone --depth 1 --branch <sha> は raw SHA を拒否するサーバがあるため使わない。
# ---------------------------------------------------------------------------
function(_sora_git_shallow url ref dest)
  # git の存在確認
  find_program(_SORA_GIT_EXECUTABLE git NO_CACHE)
  if(NOT _SORA_GIT_EXECUTABLE)
    message(FATAL_ERROR
      "[fetch_deps] git not found. Install git: sudo apt-get install git")
  endif()

  set(_retry 0)
  set(_ok FALSE)
  set(_last_error "")
  while(NOT _ok AND _retry LESS 3)
    if(_retry GREATER 0)
      message(STATUS "[fetch_deps] git retry ${_retry}/2 for ${url}")
      execute_process(COMMAND "${CMAKE_COMMAND}" -E sleep 1)
    endif()

    file(REMOVE_RECURSE "${dest}")
    file(MAKE_DIRECTORY "${dest}")

    execute_process(
      COMMAND "${_SORA_GIT_EXECUTABLE}" init
      WORKING_DIRECTORY "${dest}"
      RESULT_VARIABLE _r OUTPUT_QUIET ERROR_VARIABLE _err)
    if(NOT _r EQUAL 0)
      set(_last_error "git init: ${_err}")
      math(EXPR _retry "${_retry}+1")
      continue()
    endif()

    execute_process(
      COMMAND "${_SORA_GIT_EXECUTABLE}" remote add origin "${url}"
      WORKING_DIRECTORY "${dest}"
      RESULT_VARIABLE _r OUTPUT_QUIET ERROR_VARIABLE _err)
    if(NOT _r EQUAL 0)
      set(_last_error "git remote add: ${_err}")
      math(EXPR _retry "${_retry}+1")
      continue()
    endif()

    execute_process(
      COMMAND "${_SORA_GIT_EXECUTABLE}" fetch --depth=1 origin "${ref}"
      WORKING_DIRECTORY "${dest}"
      RESULT_VARIABLE _r OUTPUT_QUIET ERROR_VARIABLE _err)
    if(NOT _r EQUAL 0)
      set(_last_error "git fetch: ${_err}")
      math(EXPR _retry "${_retry}+1")
      continue()
    endif()

    execute_process(
      COMMAND "${_SORA_GIT_EXECUTABLE}" reset --hard FETCH_HEAD
      WORKING_DIRECTORY "${dest}"
      RESULT_VARIABLE _r OUTPUT_QUIET ERROR_VARIABLE _err)
    if(NOT _r EQUAL 0)
      set(_last_error "git reset: ${_err}")
      math(EXPR _retry "${_retry}+1")
      continue()
    endif()

    set(_ok TRUE)
  endwhile()

  if(NOT _ok)
    file(REMOVE_RECURSE "${dest}")
    message(FATAL_ERROR
      "[fetch_deps] git shallow clone failed after 3 attempts: ${url} @ ${ref}\n"
      "Last error: ${_last_error}")
  endif()
endfunction()

# ---------------------------------------------------------------------------
# _sora_fetch_openh264
# git clone して make install-headers でヘッダだけ取得する。
# ---------------------------------------------------------------------------
function(_sora_fetch_openh264 version git_url dest stamp_path)
  # stamp チェック
  if(EXISTS "${stamp_path}")
    file(READ "${stamp_path}" _stamp_content)
    string(STRIP "${_stamp_content}" _stamp_content)
    if(_stamp_content STREQUAL "${version}")
      message(STATUS "[fetch_deps] openh264: up-to-date, skipping")
      return()
    endif()
  endif()

  file(REMOVE "${stamp_path}")

  # make の解決
  find_program(_SORA_MAKE_EXECUTABLE make NO_CACHE)
  if(NOT _SORA_MAKE_EXECUTABLE)
    message(FATAL_ERROR
      "[fetch_deps] make not found. "
      "Install build-essential: sudo apt-get install build-essential")
  endif()

  # git shallow clone
  set(_src_dir "${_extract_dir}/openh264")
  _sora_git_shallow("${git_url}" "${version}" "${_src_dir}")

  # ヘッダのインストール
  file(MAKE_DIRECTORY "${dest}")
  execute_process(
    COMMAND "${_SORA_MAKE_EXECUTABLE}" -C "${_src_dir}" install-headers "PREFIX=${dest}"
    RESULT_VARIABLE _r OUTPUT_QUIET ERROR_VARIABLE _make_err)
  if(NOT _r EQUAL 0)
    file(REMOVE_RECURSE "${_src_dir}")
    file(REMOVE_RECURSE "${dest}")
    message(FATAL_ERROR "[fetch_deps] openh264: make install-headers failed\n${_make_err}")
  endif()

  file(REMOVE_RECURSE "${_src_dir}")

  # stamp 書き込み
  file(MAKE_DIRECTORY "${_stamp_dir}")
  file(WRITE "${stamp_path}" "${version}\n")

  message(STATUS "[fetch_deps] openh264: done")
endfunction()

# ---------------------------------------------------------------------------
# _sora_fetch_llvm
# webrtc/VERSIONS から URL と commit を読み取り、
# tools / libcxx / buildtools を clone して update.py で clang を取得する。
# ---------------------------------------------------------------------------
function(_sora_fetch_llvm webrtc_install_dir dest_root stamp_path)
  # VERSIONS から 6 キーを抽出
  set(_versions_file "${webrtc_install_dir}/VERSIONS")
  if(NOT EXISTS "${_versions_file}")
    message(FATAL_ERROR "[fetch_deps] llvm: VERSIONS not found: ${_versions_file}")
  endif()
  file(READ "${_versions_file}" _ver_content)

  _sora_kv_get("${_ver_content}" "WEBRTC_SRC_TOOLS_URL" _tools_url)
  _sora_kv_get("${_ver_content}" "WEBRTC_SRC_TOOLS_COMMIT" _tools_commit)
  _sora_kv_get("${_ver_content}" "WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL" _libcxx_url)
  _sora_kv_get("${_ver_content}" "WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT" _libcxx_commit)
  _sora_kv_get("${_ver_content}" "WEBRTC_SRC_BUILDTOOLS_URL" _buildtools_url)
  _sora_kv_get("${_ver_content}" "WEBRTC_SRC_BUILDTOOLS_COMMIT" _buildtools_commit)

  # 6 キーの存在を検証
  if(NOT _tools_url)
    message(FATAL_ERROR "[fetch_deps] llvm: missing required key in VERSIONS: WEBRTC_SRC_TOOLS_URL")
  endif()
  if(NOT _tools_commit)
    message(FATAL_ERROR "[fetch_deps] llvm: missing required key in VERSIONS: WEBRTC_SRC_TOOLS_COMMIT")
  endif()
  if(NOT _libcxx_url)
    message(FATAL_ERROR "[fetch_deps] llvm: missing required key in VERSIONS: WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL")
  endif()
  if(NOT _libcxx_commit)
    message(FATAL_ERROR "[fetch_deps] llvm: missing required key in VERSIONS: WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT")
  endif()
  if(NOT _buildtools_url)
    message(FATAL_ERROR "[fetch_deps] llvm: missing required key in VERSIONS: WEBRTC_SRC_BUILDTOOLS_URL")
  endif()
  if(NOT _buildtools_commit)
    message(FATAL_ERROR "[fetch_deps] llvm: missing required key in VERSIONS: WEBRTC_SRC_BUILDTOOLS_COMMIT")
  endif()

  # 6 値の連結を stamp とする（改行セパレータで境界の曖昧さを排除）
  set(_stamp_value "${_tools_url}\n${_tools_commit}\n${_libcxx_url}\n${_libcxx_commit}\n${_buildtools_url}\n${_buildtools_commit}")

  if(EXISTS "${stamp_path}")
    file(READ "${stamp_path}" _stamp_content)
    string(STRIP "${_stamp_content}" _stamp_content)
    if(_stamp_content STREQUAL "${_stamp_value}")
      message(STATUS "[fetch_deps] llvm: up-to-date, skipping")
      return()
    endif()
  endif()

  file(REMOVE "${stamp_path}")

  # 旧成果物の削除
  file(REMOVE_RECURSE "${dest_root}/clang")
  file(REMOVE_RECURSE "${dest_root}/libcxx")
  file(REMOVE_RECURSE "${dest_root}/buildtools")
  file(REMOVE_RECURSE "${dest_root}/tools")

  # tools / libcxx / buildtools を clone
  _sora_git_shallow("${_tools_url}" "${_tools_commit}" "${dest_root}/tools")
  _sora_git_shallow("${_libcxx_url}" "${_libcxx_commit}" "${dest_root}/libcxx")
  _sora_git_shallow("${_buildtools_url}" "${_buildtools_commit}" "${dest_root}/buildtools")

  # update.py で clang バイナリを取得
  execute_process(
    COMMAND "${Python_EXECUTABLE}"
      "${dest_root}/tools/clang/scripts/update.py"
      --output-dir "${dest_root}/clang"
    WORKING_DIRECTORY "${dest_root}/tools"
    RESULT_VARIABLE _r)
  if(NOT _r EQUAL 0)
    file(REMOVE_RECURSE "${dest_root}/clang")
    file(REMOVE_RECURSE "${dest_root}/libcxx")
    file(REMOVE_RECURSE "${dest_root}/buildtools")
    file(REMOVE_RECURSE "${dest_root}/tools")
    message(FATAL_ERROR "[fetch_deps] llvm: update.py failed")
  endif()

  # __config_site と __assertion_handler を libcxx/include/ にコピー
  configure_file(
    "${dest_root}/buildtools/third_party/libc++/__config_site"
    "${dest_root}/libcxx/include/__config_site"
    COPYONLY)
  configure_file(
    "${dest_root}/buildtools/third_party/libc++/__assertion_handler"
    "${dest_root}/libcxx/include/__assertion_handler"
    COPYONLY)

  # tools / buildtools を削除
  file(REMOVE_RECURSE "${dest_root}/tools")
  file(REMOVE_RECURSE "${dest_root}/buildtools")

  # stamp 書き込み
  get_filename_component(_llvm_stamp_parent "${stamp_path}" DIRECTORY)
  file(MAKE_DIRECTORY "${_llvm_stamp_parent}")
  file(WRITE "${stamp_path}" "${_stamp_value}\n")

  message(STATUS "[fetch_deps] llvm: done")
endfunction()

# ---------------------------------------------------------------------------
# メイン: webrtc → sora → boost → openh264 → llvm の順に取得
# LLVM が webrtc/VERSIONS を参照するため webrtc を先に確定させる。
# ---------------------------------------------------------------------------
message(STATUS "[fetch_deps] platform: ${SORA_PYTHON_SDK_PLATFORM}")
message(STATUS "[fetch_deps] deps root: ${DEPS_ROOT}")

# webrtc
_sora_fetch_archive("webrtc" "${_webrtc_url}"
  "${_stamp_dir}/webrtc"
  "${_platform_dir}/webrtc")

# sora
_sora_fetch_archive("sora" "${_sora_url}"
  "${_stamp_dir}/sora"
  "${_platform_dir}/sora")

# boost
_sora_fetch_archive("boost" "${_boost_url}"
  "${_stamp_dir}/boost"
  "${_platform_dir}/boost")

# openh264
_sora_fetch_openh264("${_openh264_version}" "${_openh264_git_url}"
  "${_platform_dir}/openh264"
  "${_stamp_dir}/openh264")

# llvm
_sora_fetch_llvm("${_platform_dir}/webrtc"
  "${_llvm_dir}"
  "${_llvm_stamp_dir}/llvm")

# ---------------------------------------------------------------------------
# 出力契約: CACHE FORCE で確定する変数
# ---------------------------------------------------------------------------
set(SORA_DIR "${_platform_dir}/sora" CACHE PATH "" FORCE)
set(Boost_ROOT "${_platform_dir}/boost" CACHE PATH "" FORCE)
set(WEBRTC_INCLUDE_DIR "${_platform_dir}/webrtc/include" CACHE PATH "" FORCE)
set(WEBRTC_LIBRARY_DIR "${_platform_dir}/webrtc/lib" CACHE PATH "" FORCE)
set(OPENH264_DIR "${_platform_dir}/openh264" CACHE PATH "" FORCE)
set(LIBCXX_INCLUDE_DIR "${_llvm_dir}/libcxx/include" CACHE PATH "" FORCE)
set(LIBCXXABI_INCLUDE_DIR "${_platform_dir}/webrtc/include/third_party/libc++abi/src/include" CACHE PATH "" FORCE)
set(_SORA_CLANG_DIR "${_llvm_dir}/clang" CACHE PATH "" FORCE)

# コンパイラ設定（冪等: 既に期待値なら再設定しない）
set(_expected_c "${_SORA_CLANG_DIR}/bin/clang")
set(_expected_cxx "${_SORA_CLANG_DIR}/bin/clang++")
if(NOT CMAKE_C_COMPILER STREQUAL "${_expected_c}")
  set(CMAKE_C_COMPILER "${_expected_c}" CACHE FILEPATH "" FORCE)
endif()
if(NOT CMAKE_CXX_COMPILER STREQUAL "${_expected_cxx}")
  set(CMAKE_CXX_COMPILER "${_expected_cxx}" CACHE FILEPATH "" FORCE)
endif()

message(STATUS "[fetch_deps] all dependencies ready")
