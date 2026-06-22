# aarch64-linux-gnu 用 cross-compile toolchain (Ubuntu / Raspberry Pi OS / Jetson 共通)。
# CMAKE_SYSROOT は CMake 仕様で toolchain ファイル内でのみ設定可能。
# sysroot path は CI step (もしくは開発者の uv build 起動時) に環境変数で渡す。
# sysroot の中身は fetch_deps.cmake 内 _sora_fetch_rootfs で構築する。
# CMAKE_C_COMPILER / CMAKE_CXX_COMPILER は fetch_deps.cmake で LLVM 同梱 clang に確定する。
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_CXX_COMPILER_TARGET aarch64-linux-gnu)
if(DEFINED ENV{SORA_PYTHON_SDK_SYSROOT_DIR})
  set(CMAKE_SYSROOT "$ENV{SORA_PYTHON_SDK_SYSROOT_DIR}")
endif()
