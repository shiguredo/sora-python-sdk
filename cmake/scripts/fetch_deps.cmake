# WebRTC / Sora C++ SDK / Boost / OpenH264 と libc++ / libc++abi ヘッダを
# CMake configure 時に取得するスクリプト。
# 親 CMakeLists.txt から include() で呼び出される前提。
#
# 入力契約 (呼び出し側で設定済みであること):
#   - SORA_PYTHON_SDK_PLATFORM       : 例 "ubuntu-24.04_x86_64"
#   - DEPS_ROOT                      : 例 "${PROJECT_SOURCE_DIR}/_deps"
#   - _SORA_UBUNTU_VERSION_ID        : 例 "24.04"
#
# 出力契約 (スクリプト末尾で CACHE PATH ... FORCE で上書き):
#   - SORA_DIR
#   - Boost_ROOT
#   - WEBRTC_INCLUDE_DIR
#   - WEBRTC_LIBRARY_DIR
#   - OPENH264_DIR
#   - LIBCXX_INCLUDE_DIR
#   - LIBCXXABI_INCLUDE_DIR
#
# 副作用:
#   - ${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/{webrtc,sora,boost,openh264} に展開
#   - ${DEPS_ROOT}/llvm/${_SORA_LLVM_HOST_KEY}/{libcxx,buildtools} に git clone
#   - ${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}/.stamps と
#     ${DEPS_ROOT}/llvm/${_SORA_LLVM_HOST_KEY}/.stamps に再 fetch 判定用 stamp を書き込み
#   - OpenH264 ヘッダ配置のため再 fetch 時のみ make を呼ぶ
#   - git clone と HTTP DOWNLOAD を呼ぶ

file(READ "${CMAKE_CURRENT_SOURCE_DIR}/deps.json" _SORA_DEPS_JSON)

string(JSON _SORA_DEPS_WEBRTC_VERSION   GET "${_SORA_DEPS_JSON}" "webrtc"        "version")
string(JSON _SORA_DEPS_WEBRTC_URL_TMPL  GET "${_SORA_DEPS_JSON}" "webrtc"        "url_template")
string(JSON _SORA_DEPS_WEBRTC_STRIP     GET "${_SORA_DEPS_JSON}" "webrtc"        "strip_components")

string(JSON _SORA_DEPS_SORA_VERSION     GET "${_SORA_DEPS_JSON}" "sora_cpp_sdk"  "version")
string(JSON _SORA_DEPS_SORA_URL_TMPL    GET "${_SORA_DEPS_JSON}" "sora_cpp_sdk"  "url_template")
string(JSON _SORA_DEPS_SORA_STRIP       GET "${_SORA_DEPS_JSON}" "sora_cpp_sdk"  "strip_components")

string(JSON _SORA_DEPS_BOOST_VERSION    GET "${_SORA_DEPS_JSON}" "boost"         "version")
string(JSON _SORA_DEPS_BOOST_URL_TMPL   GET "${_SORA_DEPS_JSON}" "boost"         "url_template")
string(JSON _SORA_DEPS_BOOST_STRIP      GET "${_SORA_DEPS_JSON}" "boost"         "strip_components")

string(JSON _SORA_DEPS_OPENH264_VERSION GET "${_SORA_DEPS_JSON}" "openh264"      "version")
string(JSON _SORA_DEPS_OPENH264_GIT     GET "${_SORA_DEPS_JSON}" "openh264"      "git")

# {sora_version} は値の中に {version} 等を含み得る複合プレースホルダのため、最後に置換する。
# 先に置換すると展開後の文字列に対して再度 {version} 置換が走り誤動作する。
function(_sora_render_url out_var template version sora_version platform)
  set(_url "${template}")
  string(REPLACE "{version}" "${version}" _url "${_url}")
  string(REPLACE "{sora_version}" "${sora_version}" _url "${_url}")
  string(REPLACE "{platform}" "${platform}" _url "${_url}")
  set(${out_var} "${_url}" PARENT_SCOPE)
endfunction()

function(_sora_stamp_matches out_var stamp_path expected)
  if(NOT EXISTS "${stamp_path}")
    set(${out_var} FALSE PARENT_SCOPE)
    return()
  endif()
  file(READ "${stamp_path}" _actual)
  string(STRIP "${_actual}" _actual)
  if(_actual STREQUAL expected)
    set(${out_var} TRUE PARENT_SCOPE)
  else()
    set(${out_var} FALSE PARENT_SCOPE)
  endif()
endfunction()

function(_sora_stamp_write stamp_path content)
  get_filename_component(_dir "${stamp_path}" DIRECTORY)
  file(MAKE_DIRECTORY "${_dir}")
  file(WRITE "${stamp_path}" "${content}\n")
endfunction()

# tar.gz の DL + 展開 + stamp 書き込みまで担う。
# stamp_path に書かれる識別子は url とする。url が変われば再 fetch される。
function(_sora_fetch_archive name url stamp_path dest_dir strip)
  _sora_stamp_matches(_hit "${stamp_path}" "${url}")
  if(_hit)
    message(STATUS "fetch_deps: ${name} cache hit")
    return()
  endif()

  set(_archive "${CMAKE_CURRENT_BINARY_DIR}/_sora_fetch/${name}.tar.gz")
  get_filename_component(_archive_dir "${_archive}" DIRECTORY)
  file(MAKE_DIRECTORY "${_archive_dir}")

  set(_attempt 0)
  set(_max_attempts 3)
  set(_success FALSE)
  set(_last_msg "")
  while(NOT _success AND _attempt LESS _max_attempts)
    math(EXPR _attempt "${_attempt} + 1")
    message(STATUS "fetch_deps: download ${name} (attempt ${_attempt}/${_max_attempts}) ${url}")
    file(DOWNLOAD
      "${url}"
      "${_archive}"
      TLS_VERIFY ON
      INACTIVITY_TIMEOUT 120
      STATUS _st
    )
    list(GET _st 0 _code)
    if(_code EQUAL 0)
      set(_success TRUE)
    else()
      list(GET _st 1 _last_msg)
      message(WARNING "fetch_deps: download failed for ${name} (status=${_code}, ${_last_msg})")
      file(REMOVE "${_archive}")
    endif()
  endwhile()
  if(NOT _success)
    message(FATAL_ERROR
      "fetch_deps: failed to download ${name} from ${url} after ${_max_attempts} attempts (last error: ${_last_msg})")
  endif()

  # CMake 4.x の `cmake -E tar` は --strip-components を解釈しないため、
  # 0001 でサポートするホスト (ubuntu) に同梱されている system tar を使う。
  find_program(TAR_EXECUTABLE tar)
  if(NOT TAR_EXECUTABLE)
    message(FATAL_ERROR
      "fetch_deps: 'tar' is required to extract ${name} but was not found in PATH.")
  endif()
  file(REMOVE_RECURSE "${dest_dir}")
  file(MAKE_DIRECTORY "${dest_dir}")
  execute_process(
    COMMAND "${TAR_EXECUTABLE}" xzf "${_archive}" --strip-components=${strip}
    WORKING_DIRECTORY "${dest_dir}"
    RESULT_VARIABLE _extract_rc
    OUTPUT_VARIABLE _extract_out
    ERROR_VARIABLE  _extract_err
  )
  file(REMOVE "${_archive}")
  if(NOT _extract_rc EQUAL 0)
    message(FATAL_ERROR
      "fetch_deps: extract failed for ${name} (rc=${_extract_rc})\nstdout: ${_extract_out}\nstderr: ${_extract_err}")
  endif()

  _sora_stamp_write("${stamp_path}" "${url}")
endfunction()

function(_sora_git_shallow url ref dest)
  # commit SHA を ref に取りたいが、`git clone --depth 1 --branch <sha>` は
  # Gerrit 系サーバー (chromium.googlesource.com 等) でサポートされていない。
  # buildbase.py:git_clone_shallow と同じく
  # git init + remote add + fetch --depth 1 <ref> + reset --hard FETCH_HEAD
  # の手順を取ることで commit SHA / tag / branch のいずれの ref でも動かす。
  file(REMOVE_RECURSE "${dest}")
  get_filename_component(_parent "${dest}" DIRECTORY)
  file(MAKE_DIRECTORY "${_parent}")

  set(_attempt 0)
  set(_max_attempts 3)
  set(_success FALSE)
  set(_last_err "")
  while(NOT _success AND _attempt LESS _max_attempts)
    math(EXPR _attempt "${_attempt} + 1")
    message(STATUS "fetch_deps: git shallow fetch ${url}@${ref} (attempt ${_attempt}/${_max_attempts})")

    file(MAKE_DIRECTORY "${dest}")
    set(_step_failed FALSE)
    set(_step_err "")

    foreach(_step
        "init"
        "remote;add;origin;${url}"
        "fetch;--depth=1;origin;${ref}"
        "reset;--hard;FETCH_HEAD")
      string(REPLACE ";" " " _step_label "${_step}")
      execute_process(
        COMMAND git ${_step}
        WORKING_DIRECTORY "${dest}"
        RESULT_VARIABLE _rc
        OUTPUT_VARIABLE _out
        ERROR_VARIABLE  _err
      )
      if(NOT _rc EQUAL 0)
        set(_step_failed TRUE)
        set(_step_err "git ${_step_label} failed (rc=${_rc}): ${_err}")
        break()
      endif()
    endforeach()

    if(NOT _step_failed)
      set(_success TRUE)
    else()
      set(_last_err "${_step_err}")
      message(WARNING "fetch_deps: git shallow fetch failed for ${url}@${ref}\n${_step_err}")
      file(REMOVE_RECURSE "${dest}")
    endif()
  endwhile()
  if(NOT _success)
    message(FATAL_ERROR
      "fetch_deps: failed to git shallow fetch ${url}@${ref} after ${_max_attempts} attempts (last error: ${_last_err})")
  endif()
endfunction()

# Sora C++ SDK のランタイムが動的ロードするため、Python SDK 側はヘッダだけ取得する。
function(_sora_fetch_openh264 version git_url dest stamp_path)
  _sora_stamp_matches(_hit "${stamp_path}" "${version}")
  if(_hit)
    message(STATUS "fetch_deps: openh264 cache hit (${version})")
    return()
  endif()

  find_program(MAKE_EXECUTABLE make)
  if(NOT MAKE_EXECUTABLE)
    message(FATAL_ERROR
      "OpenH264 header install requires 'make'. Install build-essential (apt install build-essential).")
  endif()

  file(REMOVE_RECURSE "${dest}")
  set(_src "${CMAKE_CURRENT_BINARY_DIR}/_sora_fetch/openh264_src")
  _sora_git_shallow("${git_url}" "${version}" "${_src}")

  file(MAKE_DIRECTORY "${dest}")
  execute_process(
    COMMAND "${MAKE_EXECUTABLE}" -C "${_src}" install-headers "PREFIX=${dest}"
    RESULT_VARIABLE _rc
    OUTPUT_VARIABLE _out
    ERROR_VARIABLE  _err
  )
  if(NOT _rc EQUAL 0)
    message(FATAL_ERROR
      "fetch_deps: openh264 install-headers failed (rc=${_rc})\nstdout: ${_out}\nstderr: ${_err}")
  endif()
  file(REMOVE_RECURSE "${_src}")
  _sora_stamp_write("${stamp_path}" "${version}")
endfunction()

# WebRTC アーカイブ展開済みディレクトリから VERSIONS を読み、
# 同梱 libcxx と buildtools を git shallow clone し、
# __config_site と __assertion_handler を libcxx 側 include に配置する。
function(_sora_fetch_llvm webrtc_install_dir dest stamp_path)
  set(_versions_file "${webrtc_install_dir}/VERSIONS")
  if(NOT EXISTS "${_versions_file}")
    message(FATAL_ERROR "fetch_deps: VERSIONS file not found at ${_versions_file}")
  endif()
  file(READ "${_versions_file}" _versions_raw)

  foreach(_key
      WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL
      WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT
      WEBRTC_SRC_BUILDTOOLS_URL
      WEBRTC_SRC_BUILDTOOLS_COMMIT)
    string(REGEX MATCH "(^|\n)${_key}=\"?([^\"\n]+)\"?" _matched "${_versions_raw}")
    if(NOT _matched)
      message(FATAL_ERROR "fetch_deps: VERSIONS does not contain ${_key}")
    endif()
    set(_${_key} "${CMAKE_MATCH_2}")
  endforeach()

  set(_expected
    "${_WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL}.${_WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT}.${_WEBRTC_SRC_BUILDTOOLS_URL}.${_WEBRTC_SRC_BUILDTOOLS_COMMIT}")
  _sora_stamp_matches(_hit "${stamp_path}" "${_expected}")
  if(_hit)
    message(STATUS "fetch_deps: llvm cache hit")
    return()
  endif()

  file(REMOVE_RECURSE "${dest}")
  set(_libcxx_dest    "${dest}/libcxx")
  set(_buildtools_dest "${dest}/buildtools")
  _sora_git_shallow("${_WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL}" "${_WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT}" "${_libcxx_dest}")
  _sora_git_shallow("${_WEBRTC_SRC_BUILDTOOLS_URL}"             "${_WEBRTC_SRC_BUILDTOOLS_COMMIT}"             "${_buildtools_dest}")

  set(_config_site "${_buildtools_dest}/third_party/libc++/__config_site")
  set(_assertion_handler "${_buildtools_dest}/third_party/libc++/__assertion_handler")
  if(NOT EXISTS "${_config_site}")
    message(FATAL_ERROR "fetch_deps: ${_config_site} not found in buildtools")
  endif()
  if(NOT EXISTS "${_assertion_handler}")
    message(FATAL_ERROR "fetch_deps: ${_assertion_handler} not found in buildtools")
  endif()
  file(COPY "${_config_site}"       DESTINATION "${_libcxx_dest}/include")
  file(COPY "${_assertion_handler}" DESTINATION "${_libcxx_dest}/include")

  _sora_stamp_write("${stamp_path}" "${_expected}")
endfunction()

set(_SORA_PLATFORM_DIR  "${DEPS_ROOT}/${SORA_PYTHON_SDK_PLATFORM}")
set(_SORA_STAMPS_DIR    "${_SORA_PLATFORM_DIR}/.stamps")
set(_SORA_WEBRTC_DEST   "${_SORA_PLATFORM_DIR}/webrtc")
set(_SORA_SORA_DEST     "${_SORA_PLATFORM_DIR}/sora")
set(_SORA_BOOST_DEST    "${_SORA_PLATFORM_DIR}/boost")
set(_SORA_OPENH264_DEST "${_SORA_PLATFORM_DIR}/openh264")

# glibc 互換性のため LLVM 取得キャッシュには ubuntu VERSION_ID も含める。
# 0002 以降で他 OS 対応する際はホスト OS 識別子の組み立てを必ず見直すこと。
set(_SORA_LLVM_HOST_KEY   "${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}-${_SORA_UBUNTU_VERSION_ID}")
set(_SORA_LLVM_DIR        "${DEPS_ROOT}/llvm/${_SORA_LLVM_HOST_KEY}")
set(_SORA_LLVM_STAMPS_DIR "${_SORA_LLVM_DIR}/.stamps")

_sora_render_url(_SORA_WEBRTC_URL
  "${_SORA_DEPS_WEBRTC_URL_TMPL}"
  "${_SORA_DEPS_WEBRTC_VERSION}"
  "${_SORA_DEPS_SORA_VERSION}"
  "${SORA_PYTHON_SDK_PLATFORM}")
_sora_fetch_archive(webrtc "${_SORA_WEBRTC_URL}"
  "${_SORA_STAMPS_DIR}/webrtc" "${_SORA_WEBRTC_DEST}" "${_SORA_DEPS_WEBRTC_STRIP}")

_sora_render_url(_SORA_SORA_URL
  "${_SORA_DEPS_SORA_URL_TMPL}"
  "${_SORA_DEPS_SORA_VERSION}"
  "${_SORA_DEPS_SORA_VERSION}"
  "${SORA_PYTHON_SDK_PLATFORM}")
_sora_fetch_archive(sora "${_SORA_SORA_URL}"
  "${_SORA_STAMPS_DIR}/sora" "${_SORA_SORA_DEST}" "${_SORA_DEPS_SORA_STRIP}")

# Boost は Sora C++ SDK の release ページに同梱されているため sora_version が必要。
_sora_render_url(_SORA_BOOST_URL
  "${_SORA_DEPS_BOOST_URL_TMPL}"
  "${_SORA_DEPS_BOOST_VERSION}"
  "${_SORA_DEPS_SORA_VERSION}"
  "${SORA_PYTHON_SDK_PLATFORM}")
_sora_fetch_archive(boost "${_SORA_BOOST_URL}"
  "${_SORA_STAMPS_DIR}/boost" "${_SORA_BOOST_DEST}" "${_SORA_DEPS_BOOST_STRIP}")

_sora_fetch_openh264(
  "${_SORA_DEPS_OPENH264_VERSION}"
  "${_SORA_DEPS_OPENH264_GIT}"
  "${_SORA_OPENH264_DEST}"
  "${_SORA_STAMPS_DIR}/openh264")

_sora_fetch_llvm(
  "${_SORA_WEBRTC_DEST}"
  "${_SORA_LLVM_DIR}"
  "${_SORA_LLVM_STAMPS_DIR}/llvm")

set(SORA_DIR              "${_SORA_SORA_DEST}"
    CACHE PATH "Sora C++ SDK install dir (fetched by fetch_deps.cmake)" FORCE)
set(Boost_ROOT            "${_SORA_BOOST_DEST}"
    CACHE PATH "Boost install dir (fetched by fetch_deps.cmake)" FORCE)
set(WEBRTC_INCLUDE_DIR    "${_SORA_WEBRTC_DEST}/include"
    CACHE PATH "WebRTC include dir (fetched by fetch_deps.cmake)" FORCE)
set(WEBRTC_LIBRARY_DIR    "${_SORA_WEBRTC_DEST}/lib"
    CACHE PATH "WebRTC library dir (fetched by fetch_deps.cmake)" FORCE)
set(OPENH264_DIR          "${_SORA_OPENH264_DEST}"
    CACHE PATH "OpenH264 install dir (fetched by fetch_deps.cmake)" FORCE)
set(LIBCXX_INCLUDE_DIR    "${_SORA_LLVM_DIR}/libcxx/include"
    CACHE PATH "libc++ include dir (fetched by fetch_deps.cmake)" FORCE)
set(LIBCXXABI_INCLUDE_DIR "${_SORA_WEBRTC_DEST}/include/third_party/libc++abi/src/include"
    CACHE PATH "libc++abi include dir (fetched by fetch_deps.cmake)" FORCE)
