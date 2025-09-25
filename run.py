import argparse
import glob
import hashlib
import importlib.metadata
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
from pypath import get_python_include_dir, get_python_version

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
    version = read_version_file("DEPS")

    # multistrap を使った sysroot の構築
    if platform.target.package_name in (
        "ubuntu-22.04_armv8_jetson",
        "raspberry-pi-os_armv8",
        "ubuntu-22.04_armv8",
        "ubuntu-24.04_armv8",
    ):
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

    if (
        platform.build.os == "macos" or platform.build.os == "ubuntu"
    ) and local_webrtc_build_dir is None:
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
    elif platform.build.os == "ubuntu" and platform.build.arch == "armv8":
        install_cmake_args["platform"] = "linux-aarch64"
    else:
        raise Exception("Failed to install CMake")
    install_cmake(**install_cmake_args)

    # Sora C++ SDK
    if local_sora_cpp_sdk_dir is None:
        install_sora_and_deps(
            version["SORA_CPP_SDK_VERSION"],
            version["BOOST_VERSION"],
            platform.target.package_name,
            source_dir,
            install_dir,
        )
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
    "ubuntu-22.04_armv8",
    "ubuntu-24.04_armv8",
    "ubuntu-22.04_armv8_jetson",
    "raspberry-pi-os_armv8",
]


def _find_clang_binary(name: str) -> Optional[str]:
    if shutil.which(name) is not None:
        return name
    else:
        for n in range(50, 14, -1):
            if shutil.which(f"{name}-{n}") is not None:
                return f"{name}-{n}"
    return None


def _get_platform(target: str) -> Platform:
    if target == "windows_x86_64":
        platform = Platform("windows", get_windows_osver(), "x86_64")
    elif target == "macos_x86_64":
        platform = Platform("macos", get_macos_osver(), "x86_64")
    elif target == "macos_arm64":
        platform = Platform("macos", get_macos_osver(), "arm64")
    elif target == "ubuntu-22.04_x86_64":
        platform = Platform("ubuntu", "22.04", "x86_64")
    elif target == "ubuntu-24.04_x86_64":
        platform = Platform("ubuntu", "24.04", "x86_64")
    elif target == "ubuntu-22.04_armv8":
        platform = Platform("ubuntu", "22.04", "armv8")
    elif target == "ubuntu-24.04_armv8":
        platform = Platform("ubuntu", "24.04", "armv8")
    elif target == "ubuntu-22.04_armv8_jetson":
        platform = Platform("jetson", None, "armv8", "ubuntu-22.04")
    elif target == "raspberry-pi-os_armv8":
        platform = Platform("raspberry-pi-os", None, "armv8")
    else:
        raise Exception(f"Unknown target {target}")
    return platform


def _build(
    target: str,
    debug: bool,
    relwithdebinfo: bool,
    local_webrtc_build_dir: Optional[str],
    local_webrtc_build_args: List[str],
    local_sora_cpp_sdk_dir: Optional[str],
    local_sora_cpp_sdk_args: List[str],
):
    platform = _get_platform(target)

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
            debug,
            local_webrtc_build_dir,
            local_webrtc_build_args,
            local_sora_cpp_sdk_dir,
            local_sora_cpp_sdk_args,
        )

        configuration = "Release"
        if debug:
            configuration = "Debug"
        if relwithdebinfo:
            configuration = "RelWithDebInfo"

        webrtc_platform = get_webrtc_platform(platform)
        webrtc_info = get_webrtc_info(webrtc_platform, local_webrtc_build_dir, install_dir, debug)

        sora_info = get_sora_info(webrtc_platform, local_sora_cpp_sdk_dir, install_dir, debug)

        cmake_args = []
        cmake_args.append(f"-DCMAKE_BUILD_TYPE={configuration}")
        cmake_args.append(f"-DTARGET_OS={platform.target.os}")
        # Raspberry Pi OS の場合は sora-sdk-rpi パッケージからバージョンを取得する
        if platform.target.os == "raspberry-pi-os":
            cmake_args.append(
                f"-DSORA_PYTHON_SDK_VERSION={importlib.metadata.version('sora-sdk-rpi')}"
            )
        else:
            cmake_args.append(f"-DSORA_PYTHON_SDK_VERSION={importlib.metadata.version('sora-sdk')}")
        cmake_args.append(f"-DBOOST_ROOT={cmake_path(sora_info.boost_install_dir)}")
        cmake_args.append(f"-DWEBRTC_INCLUDE_DIR={cmake_path(webrtc_info.webrtc_include_dir)}")
        cmake_args.append(f"-DWEBRTC_LIBRARY_DIR={cmake_path(webrtc_info.webrtc_library_dir)}")
        cmake_args.append(f"-DSORA_DIR={cmake_path(sora_info.sora_install_dir)}")
        cmake_args.append(f"-DOPENH264_DIR={cmake_path(os.path.join(install_dir, 'openh264'))}")
        python_version = get_python_version()
        cmake_args.append(f"-DPython_INCLUDE_DIR={get_python_include_dir(python_version)}")
        cmake_args.append(f"-DPython_EXECUTABLE={cmake_path(sys.executable)}")

        if platform.target.os == "ubuntu":
            # クロスコンパイルの設定。
            # 本来は toolchain ファイルに書く内容

            if platform.build.arch == "armv8":
                # ビルド環境が armv8 の場合は libwebrtc のバイナリが使えないのでローカルの clang を利用する
                cmake_args += [
                    "-DCMAKE_C_COMPILER=clang-19",
                    "-DCMAKE_CXX_COMPILER=clang++-19",
                ]
            else:
                cmake_args += [
                    f"-DCMAKE_C_COMPILER={os.path.join(webrtc_info.clang_dir, 'bin', 'clang')}",
                    f"-DCMAKE_CXX_COMPILER={os.path.join(webrtc_info.clang_dir, 'bin', 'clang++')}",
                ]
            cmake_args += [
                f"-DLIBCXX_INCLUDE_DIR={cmake_path(os.path.join(webrtc_info.libcxx_dir, 'include'))}",
                f"-DLIBCXXABI_INCLUDE_DIR={cmake_path(os.path.join(webrtc_info.libcxxabi_dir, 'include'))}",
            ]

            if platform.build.arch != platform.target.arch:
                sysroot = os.path.join(install_dir, "rootfs")
                python_version = get_python_version()
                python_version_short = ".".join(python_version.split(".")[:2])
                cmake_args += [
                    "-DCMAKE_SYSTEM_NAME=Linux",
                    "-DCMAKE_SYSTEM_PROCESSOR=aarch64",
                    "-DCMAKE_C_COMPILER_TARGET=aarch64-linux-gnu",
                    "-DCMAKE_CXX_COMPILER_TARGET=aarch64-linux-gnu",
                    f"-DCMAKE_FIND_ROOT_PATH={sysroot}",
                    "-DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER",
                    "-DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=BOTH",
                    "-DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=BOTH",
                    "-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=BOTH",
                    f"-DCMAKE_SYSROOT={sysroot}",
                    f"-DNB_SUFFIX=.cpython-{python_version_short.replace('.', '')}-aarch64-linux-gnu.so",
                ]
        elif platform.target.os == "macos":
            sysroot = cmdcap(["xcrun", "--sdk", "macosx", "--show-sdk-path"])
            cmake_args += [
                "-DCMAKE_SYSTEM_PROCESSOR=arm64",
                "-DCMAKE_OSX_ARCHITECTURES=arm64",
                f"-DCMAKE_C_COMPILER={os.path.join(webrtc_info.clang_dir, 'bin', 'clang')}",
                "-DCMAKE_C_COMPILER_TARGET=aarch64-apple-darwin",
                f"-DCMAKE_CXX_COMPILER={os.path.join(webrtc_info.clang_dir, 'bin', 'clang++')}",
                "-DCMAKE_CXX_COMPILER_TARGET=aarch64-apple-darwin",
                f"-DCMAKE_SYSROOT={sysroot}",
                f"-DLIBCXX_INCLUDE_DIR={cmake_path(os.path.join(webrtc_info.libcxx_dir, 'include'))}",
                f"-DLIBCXXABI_INCLUDE_DIR={cmake_path(os.path.join(webrtc_info.libcxxabi_dir, 'include'))}",
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
                f"-DLIBCXXABI_INCLUDE_DIR={cmake_path(os.path.join(webrtc_info.libcxxabi_dir, 'include'))}",
                f"-DPython_ROOT_DIR={cmake_path(os.path.join(sysroot, 'usr', 'include', 'python3.10'))}",
                "-DNB_SUFFIX=.cpython-310-aarch64-linux-gnu.so",
            ]
        elif platform.target.os == "raspberry-pi-os":
            sysroot = os.path.join(install_dir, "rootfs")
            python_version = get_python_version()
            python_version_short = ".".join(python_version.split(".")[:2])
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
                f"-DLIBCXXABI_INCLUDE_DIR={cmake_path(os.path.join(webrtc_info.libcxxabi_dir, 'include'))}",
                f"-DNB_SUFFIX=.cpython-{python_version_short.replace('.', '')}-aarch64-linux-gnu.so",
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

        if platform.target.os == "raspberry-pi-os":
            # libcamerac.so を sora_sdk_ext.*.so と同じディレクトリにコピーする
            libcamerac_so = os.path.join(sora_info.sora_install_dir, "lib", "libcamerac.so")
            shutil.copyfile(libcamerac_so, os.path.join(sora_src_dir, "libcamerac.so"))


def _format(
    clang_format_path: Optional[str] = None,
    skip_clang_format: bool = False,
    skip_ruff: bool = False,
):
    # C++ ファイルのフォーマット
    if not skip_clang_format:
        if clang_format_path is None:
            clang_format_path = _find_clang_binary("clang-format")
        if clang_format_path is None:
            print("Warning: clang-format not found. Skipping C++ formatting.")
        else:
            patterns = [
                "src/**/*.h",
                "src/**/*.cpp",
            ]
            target_files = []
            for pattern in patterns:
                files = glob.glob(pattern, recursive=True)
                target_files.extend(files)
            if target_files:
                print(f"Formatting {len(target_files)} C++ files...")
                cmd([clang_format_path, "-i"] + target_files)

    # Python ファイルのフォーマット
    if not skip_ruff:
        print("Running Python formatting with ruff...")
        try:
            cmd(["uv", "run", "ruff", "format"])
        except Exception as e:
            print(f"Formatting failed: {e}")


def main():
    parser = argparse.ArgumentParser()
    sp = parser.add_subparsers(dest="command", required=True)

    # build サブコマンド
    bp = sp.add_parser("build")
    bp.add_argument("target", choices=AVAILABLE_TARGETS)
    bp.add_argument("--debug", action="store_true")
    bp.add_argument("--relwithdebinfo", action="store_true")
    bp.add_argument("--local-webrtc-build-dir", type=os.path.abspath)
    bp.add_argument("--local-webrtc-build-args", default="", type=shlex.split)
    bp.add_argument("--local-sora-cpp-sdk-dir", type=os.path.abspath)
    bp.add_argument("--local-sora-cpp-sdk-args", default="", type=shlex.split)

    # format サブコマンド
    fp = sp.add_parser("format")
    fp.add_argument("--clang-format-path", type=str, default=None)
    fp.add_argument(
        "--skip-clang-format", action="store_true", help="Skip C++ formatting with clang-format"
    )
    fp.add_argument("--skip-ruff", action="store_true", help="Skip Python formatting with ruff")

    args = parser.parse_args()

    if args.command == "build":
        _build(
            target=args.target,
            debug=args.debug,
            relwithdebinfo=args.relwithdebinfo,
            local_webrtc_build_dir=args.local_webrtc_build_dir,
            local_webrtc_build_args=args.local_webrtc_build_args,
            local_sora_cpp_sdk_dir=args.local_sora_cpp_sdk_dir,
            local_sora_cpp_sdk_args=args.local_sora_cpp_sdk_args,
        )
    elif args.command == "format":
        _format(
            clang_format_path=args.clang_format_path,
            skip_clang_format=args.skip_clang_format,
            skip_ruff=args.skip_ruff,
        )


if __name__ == "__main__":
    main()
