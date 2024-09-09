import argparse
import hashlib
import multiprocessing
import os
import shlex
import shutil
import sys
from typing import List, Optional

from buildbase import (
    Platform,
    add_path,
    build_sora,
    build_webrtc,
    cd,
    cmake_path,
    cmd,
    cmdcap,
    get_macos_osver,
    get_sora_info,
    get_webrtc_info,
    get_webrtc_platform,
    get_windows_osver,
    install_cmake,
    install_llvm,
    install_openh264,
    install_rootfs,
    install_sora_and_deps,
    install_webrtc,
    mkdir_p,
    read_version_file,
)
from pypath import get_python_include_dir, get_python_library, get_python_version

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def install_deps(
    platform: Platform,
    source_dir,
    build_dir,
    install_dir,
    debug,
    local_webrtc_build_dir: Optional[str],
    local_webrtc_build_args: List[str],
    local_sora_cpp_sdk_dir: Optional[str],
    local_sora_cpp_sdk_args: List[str],
):
    version = read_version_file("VERSION")

    # multistrap を使った sysroot の構築
    if platform.target.os == "jetson":
        conf = os.path.join("multistrap", f"{platform.target.package_name}.conf")
        # conf ファイルのハッシュ値をバージョンとする
        version_md5 = hashlib.md5(open(conf, "rb").read()).hexdigest()
        install_rootfs_args = {
            "version": version_md5,
            "version_file": os.path.join(install_dir, "rootfs.version"),
            "install_dir": install_dir,
            "conf": conf,
        }
        install_rootfs(**install_rootfs_args)

    # WebRTC
    webrtc_platform = get_webrtc_platform(platform)
    if local_webrtc_build_dir is None:
        install_webrtc_args = {
            "version": version["WEBRTC_BUILD_VERSION"],
            "version_file": os.path.join(install_dir, "webrtc.version"),
            "source_dir": source_dir,
            "install_dir": install_dir,
            "platform": webrtc_platform,
        }
        install_webrtc(**install_webrtc_args)
    else:
        build_webrtc_args = {
            "platform": webrtc_platform,
            "local_webrtc_build_dir": local_webrtc_build_dir,
            "local_webrtc_build_args": local_webrtc_build_args,
            "debug": debug,
        }
        build_webrtc(**build_webrtc_args)

    webrtc_info = get_webrtc_info(webrtc_platform, local_webrtc_build_dir, install_dir, debug)
    webrtc_version = read_version_file(webrtc_info.version_file)

    if platform.build.os == "ubuntu" and local_webrtc_build_dir is None:
        # LLVM
        tools_url = webrtc_version["WEBRTC_SRC_TOOLS_URL"]
        tools_commit = webrtc_version["WEBRTC_SRC_TOOLS_COMMIT"]
        libcxx_url = webrtc_version["WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_URL"]
        libcxx_commit = webrtc_version["WEBRTC_SRC_THIRD_PARTY_LIBCXX_SRC_COMMIT"]
        buildtools_url = webrtc_version["WEBRTC_SRC_BUILDTOOLS_URL"]
        buildtools_commit = webrtc_version["WEBRTC_SRC_BUILDTOOLS_COMMIT"]
        install_llvm_args = {
            "version": f"{tools_url}.{tools_commit}."
            f"{libcxx_url}.{libcxx_commit}."
            f"{buildtools_url}.{buildtools_commit}",
            "version_file": os.path.join(install_dir, "llvm.version"),
            "install_dir": install_dir,
            "tools_url": tools_url,
            "tools_commit": tools_commit,
            "libcxx_url": libcxx_url,
            "libcxx_commit": libcxx_commit,
            "buildtools_url": buildtools_url,
            "buildtools_commit": buildtools_commit,
        }
        install_llvm(**install_llvm_args)

    # CMake
    install_cmake_args = {
        "version": version["CMAKE_VERSION"],
        "version_file": os.path.join(install_dir, "cmake.version"),
        "source_dir": source_dir,
        "install_dir": install_dir,
        "platform": "",
        "ext": "tar.gz",
    }
    if platform.build.os == "windows" and platform.build.arch == "x86_64":
        install_cmake_args["platform"] = "windows-x86_64"
        install_cmake_args["ext"] = "zip"
    elif platform.build.os == "macos":
        install_cmake_args["platform"] = "macos-universal"
    elif platform.build.os == "ubuntu" and platform.build.arch == "x86_64":
        install_cmake_args["platform"] = "linux-x86_64"
    elif platform.build.os == "ubuntu" and platform.build.arch == "arm64":
        install_cmake_args["platform"] = "linux-aarch64"
    else:
        raise Exception("Failed to install CMake")
    install_cmake(**install_cmake_args)

    # Sora C++ SDK
    if local_sora_cpp_sdk_dir is None:
        install_sora_and_deps(platform.target.package_name, source_dir, install_dir)
    else:
        build_sora(
            platform.target.package_name,
            local_sora_cpp_sdk_dir,
            local_sora_cpp_sdk_args,
            debug,
            local_webrtc_build_dir,
        )

    if platform.build.os == "macos":
        add_path(os.path.join(install_dir, "cmake", "CMake.app", "Contents", "bin"))
    else:
        add_path(os.path.join(install_dir, "cmake", "bin"))

    if platform.build.os != "windows":
        # OpenH264
        install_openh264_args = {
            "version": version["OPENH264_VERSION"],
            "version_file": os.path.join(install_dir, "openh264.version"),
            "source_dir": source_dir,
            "install_dir": install_dir,
            "is_windows": platform.target.os == "windows",
        }
        install_openh264(**install_openh264_args)


AVAILABLE_TARGETS = [
    "windows_x86_64",
    "macos_arm64",
    "ubuntu-22.04_x86_64",
    "ubuntu-24.04_x86_64",
    "ubuntu-22.04_armv8_jetson",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--relwithdebinfo", action="store_true")
    parser.add_argument("--local-webrtc-build-dir", type=os.path.abspath)
    parser.add_argument("--local-webrtc-build-args", default="", type=shlex.split)
    parser.add_argument("--local-sora-cpp-sdk-dir", type=os.path.abspath)
    parser.add_argument("--local-sora-cpp-sdk-args", default="", type=shlex.split)
    parser.add_argument("target", choices=AVAILABLE_TARGETS)

    args = parser.parse_args()
    if args.target == "windows_x86_64":
        platform = Platform("windows", get_windows_osver(), "x86_64")
    elif args.target == "macos_x86_64":
        platform = Platform("macos", get_macos_osver(), "x86_64")
    elif args.target == "macos_arm64":
        platform = Platform("macos", get_macos_osver(), "arm64")
    elif args.target == "ubuntu-22.04_x86_64":
        platform = Platform("ubuntu", "22.04", "x86_64")
    elif args.target == "ubuntu-24.04_x86_64":
        platform = Platform("ubuntu", "24.04", "x86_64")
    elif args.target == "ubuntu-22.04_armv8_jetson":
        platform = Platform("jetson", None, "armv8", "ubuntu-22.04")
    else:
        raise Exception(f"Unknown target {args.target}")

    source_dir = os.path.join(BASE_DIR, "_source", platform.target.package_name)
    build_dir = os.path.join(BASE_DIR, "_build", platform.target.package_name)
    install_dir = os.path.join(BASE_DIR, "_install", platform.target.package_name)
    mkdir_p(source_dir)
    mkdir_p(build_dir)
    mkdir_p(install_dir)

    with cd(BASE_DIR):
        install_deps(
            platform,
            source_dir,
            build_dir,
            install_dir,
            args.debug,
            args.local_webrtc_build_dir,
            args.local_webrtc_build_args,
            args.local_sora_cpp_sdk_dir,
            args.local_sora_cpp_sdk_args,
        )

        configuration = "Release"

        webrtc_platform = get_webrtc_platform(platform)
        webrtc_info = get_webrtc_info(
            webrtc_platform, args.local_webrtc_build_dir, install_dir, args.debug
        )
        
        sora_info = get_sora_info(
            webrtc_platform, args.local_sora_cpp_sdk_dir, install_dir, args.debug
        )

        cmake_args = []
        cmake_args.append(f"-DCMAKE_BUILD_TYPE={configuration}")
        cmake_args.append(f"-DTARGET_OS={platform.target.os}")
        cmake_args.append(f"-DBOOST_ROOT={cmake_path(sora_info.boost_install_dir)}")
        cmake_args.append(f"-DWEBRTC_INCLUDE_DIR={cmake_path(webrtc_info.webrtc_include_dir)}")
        cmake_args.append(f"-DWEBRTC_LIBRARY_DIR={cmake_path(webrtc_info.webrtc_library_dir)}")
        cmake_args.append(f"-DSORA_DIR={cmake_path(sora_info.sora_install_dir)}")
        cmake_args.append(f"-DOPENH264_DIR={cmake_path(os.path.join(install_dir, 'openh264'))}")
        python_version = get_python_version()
        cmake_args.append(f"-DPYTHON_VERSION_STRING={python_version}")
        cmake_args.append(f"-DPYTHON_INCLUDE_DIR={get_python_include_dir(python_version)}")
        cmake_args.append(f"-DPYTHON_EXECUTABLE={cmake_path(sys.executable)}")
        python_library = get_python_library(python_version)
        if python_library is None:
            raise Exception("Failed to get Python library")
        cmake_args.append(f"-DPYTHON_LIBRARY={cmake_path(python_library)}")

        if platform.target.os == "ubuntu":
            # クロスコンパイルの設定。
            # 本来は toolchain ファイルに書く内容
            cmake_args += [
                f"-DCMAKE_C_COMPILER={os.path.join(webrtc_info.clang_dir, 'bin', 'clang')}",
                f"-DCMAKE_CXX_COMPILER={os.path.join(webrtc_info.clang_dir, 'bin', 'clang++')}",
                f"-DLIBCXX_INCLUDE_DIR={cmake_path(os.path.join(webrtc_info.libcxx_dir, 'include'))}",
            ]
        elif platform.target.os == "macos":
            sysroot = cmdcap(["xcrun", "--sdk", "macosx", "--show-sdk-path"])
            cmake_args += [
                "-DCMAKE_SYSTEM_PROCESSOR=arm64",
                "-DCMAKE_OSX_ARCHITECTURES=arm64",
                "-DCMAKE_C_COMPILER=clang",
                "-DCMAKE_C_COMPILER_TARGET=aarch64-apple-darwin",
                "-DCMAKE_CXX_COMPILER=clang++",
                "-DCMAKE_CXX_COMPILER_TARGET=aarch64-apple-darwin",
                f"-DCMAKE_SYSROOT={sysroot}",
            ]
        elif platform.target.os == "jetson":
            sysroot = os.path.join(install_dir, "rootfs")
            cmake_args += [
                "-DCMAKE_SYSTEM_NAME=Linux",
                "-DCMAKE_SYSTEM_PROCESSOR=aarch64",
                f"-DCMAKE_C_COMPILER={os.path.join(webrtc_info.clang_dir, 'bin', 'clang')}",
                "-DCMAKE_C_COMPILER_TARGET=aarch64-linux-gnu",
                f"-DCMAKE_CXX_COMPILER={os.path.join(webrtc_info.clang_dir, 'bin', 'clang++')}",
                "-DCMAKE_CXX_COMPILER_TARGET=aarch64-linux-gnu",
                f"-DCMAKE_FIND_ROOT_PATH={sysroot}",
                "-DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER",
                "-DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=BOTH",
                "-DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=BOTH",
                "-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=BOTH",
                f"-DCMAKE_SYSROOT={sysroot}",
                f"-DLIBCXX_INCLUDE_DIR={cmake_path(os.path.join(webrtc_info.libcxx_dir, 'include'))}",
                f"-DPython_ROOT_DIR={cmake_path(os.path.join(sysroot, 'usr', 'include', 'python3.10'))}",
                "-DNB_SUFFIX=.cpython-310-aarch64-linux-gnu.so",
            ]

        # Windows 以外の、クロスコンパイルでない環境では pyi ファイルを生成する
        if (
            platform.target.os != "windows"
            and platform.build.package_name == platform.target.package_name
        ):
            cmake_args.append("-DSORA_GEN_PYI=ON")

        sora_src_dir = os.path.join("src", "sora_sdk")
        sora_build_dir = os.path.join(build_dir, "sora_sdk")
        if platform.target.os == "windows":
            sora_build_target_dir = os.path.join(build_dir, "sora_sdk", configuration)
        else:
            sora_build_target_dir = os.path.join(build_dir, "sora_sdk")

        mkdir_p(sora_build_dir)
        with cd(sora_build_dir):
            cmd(["cmake", BASE_DIR, *cmake_args])
            cmd(
                [
                    "cmake",
                    "--build",
                    ".",
                    "--config",
                    configuration,
                    f"-j{multiprocessing.cpu_count()}",
                ]
            )

        for file in os.listdir(sora_src_dir):
            if file.startswith("sora_sdk_ext.") and (
                file.endswith(".so") or file.endswith(".dylib") or file.endswith(".pyd")
            ):
                os.remove(os.path.join(sora_src_dir, file))

        for file in os.listdir(sora_build_target_dir):
            if file.startswith("sora_sdk_ext.") and (
                file.endswith(".so") or file.endswith(".dylib") or file.endswith(".pyd")
            ):
                shutil.copyfile(
                    os.path.join(sora_build_target_dir, file), os.path.join(sora_src_dir, file)
                )
            if file in ("sora_sdk_ext.pyi", "py.typed"):
                shutil.copyfile(
                    os.path.join(sora_build_target_dir, file), os.path.join(sora_src_dir, file)
                )


if __name__ == "__main__":
    main()
