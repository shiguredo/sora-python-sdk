# https://github.com/scikit-build/scikit-build/blob/d06e8724e51885d1d147accfc9f65dd84f1ae7f7/skbuild/cmaker.py より
import configparser
import contextlib
import itertools
import os
import sys
import sysconfig
from pathlib import Path

import distutils.sysconfig as du_sysconfig


def get_python_version() -> str:
    """Get version associated with the current python interpreter.

    Returns:
        str: python version string

    Example:
        >>> # xdoc: +IGNORE_WANT
        >>> from skbuild.cmaker import CMaker
        >>> python_version = CMaker.get_python_version()
        >>> print('python_version = {!r}'.format(python_version))
        python_version = '3.7'
    """
    python_version = sysconfig.get_config_var("VERSION")

    if not python_version:
        python_version = sysconfig.get_config_var("py_version_short")

    if not python_version:
        python_version = ".".join(map(str, sys.version_info[:2]))

    assert isinstance(python_version, str)

    return python_version


# NOTE(opadron): The try-excepts raise the cyclomatic complexity, but we
# need them for this function.
def get_python_include_dir(python_version: str):
    """Get include directory associated with the current python
    interpreter.

    Args:
        python_version (str): python version, may be partial.

    Returns:
        PathLike: python include dir

    Example:
        >>> # xdoc: +IGNORE_WANT
        >>> from skbuild.cmaker import CMaker
        >>> python_version = CMaker.get_python_version()
        >>> python_include_dir = CMaker.get_python_include_dir(python_version)
        >>> print('python_include_dir = {!r}'.format(python_include_dir))
        python_include_dir = '.../conda/envs/py37/include/python3.7m'
    """
    # determine python include dir
    python_include_dir: str | None = sysconfig.get_config_var("INCLUDEPY")

    # if Python.h not found (or python_include_dir is None), try to find a
    # suitable include dir
    found_python_h = python_include_dir is not None and os.path.exists(
        os.path.join(python_include_dir, "Python.h")
    )

    if not found_python_h:
        # NOTE(opadron): these possible prefixes must be guarded against
        # AttributeErrors and KeyErrors because they each can throw on
        # different platforms or even different builds on the same platform.
        include_py: str | None = sysconfig.get_config_var("INCLUDEPY")
        include_dir: str | None = sysconfig.get_config_var("INCLUDEDIR")
        include: str | None = None
        plat_include: str | None = None
        python_inc: str | None = None
        python_inc2: str | None = None

        with contextlib.suppress(AttributeError, KeyError):
            include = sysconfig.get_path("include")

        with contextlib.suppress(AttributeError, KeyError):
            plat_include = sysconfig.get_path("platinclude")

        with contextlib.suppress(AttributeError):
            python_inc = sysconfig.get_python_inc()  # type: ignore[attr-defined]

        if include_py is not None:
            include_py = os.path.dirname(include_py)
        if include is not None:
            include = os.path.dirname(include)
        if plat_include is not None:
            plat_include = os.path.dirname(plat_include)
        if python_inc is not None:
            python_inc2 = os.path.join(python_inc, ".".join(map(str, sys.version_info[:2])))

        all_candidate_prefixes = [
            include_py,
            include_dir,
            include,
            plat_include,
            python_inc,
            python_inc2,
        ]
        candidate_prefixes: list[str] = [pre for pre in all_candidate_prefixes if pre]

        candidate_versions: tuple[str, ...] = (python_version,)
        if python_version:
            candidate_versions += ("",)

            pymalloc = None
            with contextlib.suppress(AttributeError):
                pymalloc = bool(sysconfig.get_config_var("WITH_PYMALLOC"))

            if pymalloc:
                candidate_versions += (python_version + "m",)

        candidates = (
            os.path.join(prefix, "".join(("python", ver)))
            for (prefix, ver) in itertools.product(candidate_prefixes, candidate_versions)
        )

        for candidate in candidates:
            if os.path.exists(os.path.join(candidate, "Python.h")):
                # we found an include directory
                python_include_dir = candidate
                break

    # TODO(opadron): what happens if we don't find an include directory?
    #                Throw SKBuildError?

    return python_include_dir


def get_python_library(python_version: str):
    """Get path to the python library associated with the current python
    interpreter.

    Args:
        python_version (str): python version, may be partial.

    Returns:
        PathLike: python_library : python shared library

    Example:
        >>> # xdoc: +IGNORE_WANT
        >>> from skbuild.cmaker import CMaker
        >>> python_version = CMaker.get_python_version()
        >>> python_library = CMaker.get_python_include_dir(python_version)
        >>> print('python_library = {!r}'.format(python_library))
        python_library = '.../conda/envs/py37/include/python3.7m'
    """
    # On Windows, support cross-compiling in the same way as setuptools
    # When cross-compiling, check DIST_EXTRA_CONFIG first
    config_file = os.environ.get("DIST_EXTRA_CONFIG", None)
    if config_file and Path(config_file).is_file():
        cp = configparser.ConfigParser()
        cp.read(config_file)
        result = cp.get("build_ext", "library_dirs", fallback="")
        if result:
            minor = sys.version_info[1]
            return str(Path(result) / f"python3{minor}.lib")

    # This seems to be the simplest way to detect the library path with
    # modern python versions that avoids the complicated construct below.
    # It avoids guessing the library name. Tested with cpython 3.8 and
    # pypy 3.8 on Ubuntu.
    libdir: str | None = sysconfig.get_config_var("LIBDIR")
    ldlibrary: str | None = sysconfig.get_config_var("LDLIBRARY")
    if libdir and ldlibrary and os.path.exists(libdir):
        if sysconfig.get_config_var("MULTIARCH"):
            masd = sysconfig.get_config_var("multiarchsubdir")
            if masd:
                if masd.startswith(os.sep):
                    masd = masd[len(os.sep) :]
                libdir_masd = os.path.join(libdir, masd)
                if os.path.exists(libdir_masd):
                    libdir = libdir_masd
        libpath = os.path.join(libdir, ldlibrary)
        if libpath and os.path.exists(libpath):
            return libpath

    return _guess_python_library(python_version)


def _guess_python_library(python_version: str):
    # determine direct path to libpython
    python_library: str | None = sysconfig.get_config_var("LIBRARY")

    # if static (or nonexistent), try to find a suitable dynamic libpython
    if not python_library or os.path.splitext(python_library)[1][-2:] == ".a":
        candidate_lib_prefixes = ["", "lib"]

        candidate_suffixes = [""]
        candidate_implementations = ["python"]
        if sys.implementation.name == "pypy":
            candidate_implementations[:0] = ["pypy-c", "pypy3-c", "pypy"]
            candidate_suffixes.append("-c")

        candidate_extensions = [".lib", ".so", ".a"]
        # On pypy + MacOS, the variable WITH_DYLD is not set. It would
        # actually be possible to determine the python library there using
        # LDLIBRARY + LIBDIR. As a simple fix, we check if the LDLIBRARY
        # ends with .dylib and add it to the candidate matrix in this case.
        with_ld = sysconfig.get_config_var("WITH_DYLD")
        ld_lib = sysconfig.get_config_var("LDLIBRARY")
        if with_ld or (ld_lib and ld_lib.endswith(".dylib")):
            candidate_extensions.insert(0, ".dylib")

        candidate_versions = [python_version]
        if python_version:
            candidate_versions.append("")
            candidate_versions.insert(0, "".join(python_version.split(".")[:2]))

        abiflags = getattr(sys, "abiflags", "")
        candidate_abiflags = [abiflags]
        if abiflags:
            candidate_abiflags.append("")

        # Ensure the value injected by virtualenv is
        # returned on windows.
        # Because calling `sysconfig.get_config_var('multiarchsubdir')`
        # returns an empty string on Linux, `du_sysconfig` is only used to
        # get the value of `LIBDIR`.
        candidate_libdirs = []
        libdir_a = du_sysconfig.get_config_var("LIBDIR")
        assert not isinstance(libdir_a, int)
        if libdir_a is None:
            libdest = sysconfig.get_config_var("LIBDEST")
            candidate_libdirs.append(
                os.path.abspath(os.path.join(libdest, "..", "libs") if libdest else "libs")
            )
        libdir_b = sysconfig.get_config_var("LIBDIR")
        for libdir in (libdir_a, libdir_b):
            if libdir is None:
                continue
            if sysconfig.get_config_var("MULTIARCH"):
                masd = sysconfig.get_config_var("multiarchsubdir")
                if masd:
                    if masd.startswith(os.sep):
                        masd = masd[len(os.sep) :]
                    candidate_libdirs.append(os.path.join(libdir, masd))
            candidate_libdirs.append(libdir)

        candidates = (
            os.path.join(libdir, "".join((pre, impl, ver, abi, suf, ext)))
            for (libdir, pre, impl, ext, ver, abi, suf) in itertools.product(
                candidate_libdirs,
                candidate_lib_prefixes,
                candidate_implementations,
                candidate_extensions,
                candidate_versions,
                candidate_abiflags,
                candidate_suffixes,
            )
        )

        for candidate in candidates:
            if os.path.exists(candidate):
                # we found a (likely alternate) libpython
                python_library = candidate
                break

    # Temporary workaround for some libraries (opencv) processing the
    # string output.  Will return None instead of empty string in future
    # versions if the library does not exist.
    if python_library is None:
        return None
    return python_library if python_library and os.path.exists(python_library) else ""
