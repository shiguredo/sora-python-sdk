#!/usr/bin/env python3
"""
A wrapper script for pytest that checks for memory leaks in nanobind code.

This script runs pytest with the specified arguments and captures the standard output.
It then checks if the string "nanobind: leaked" appears in the output, which would
indicate a memory leak in nanobind code.

Usage:
    python pytest_memory_leak_checker.py [pytest_args]

Example:
    python pytest_memory_leak_checker.py tests/test_memory_leak.py -v

Exit codes:
    0: Tests passed and no memory leaks detected
    1: Tests failed or memory leaks detected
"""

import subprocess
import sys
import re


def run_pytest_and_check_for_leaks(pytest_args):
    # Construct the pytest command
    command = ["uv", "run", "pytest"] + pytest_args

    # Run pytest and capture the output
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        universal_newlines=True,
    )

    # Variables to track test status and memory leaks
    test_failed = False
    memory_leak_detected = False
    output_lines = []

    # Process the output line by line
    if process.stdout:
        for line in process.stdout:
            # Print the line to the console
            print(line, end="")
            output_lines.append(line)

            # Check for test failures
            if "FAILED" in line:
                test_failed = True

            # Check for memory leaks
            if "nanobind: leaked" in line:
                memory_leak_detected = True

    # Wait for the process to complete
    process.wait()

    # Determine the exit code
    if memory_leak_detected:
        print("\n\033[91mERROR: Memory leak detected in nanobind code!\033[0m")
        return 1
    elif test_failed or process.returncode != 0:
        return process.returncode
    else:
        print("\n\033[92mSUCCESS: No memory leaks detected.\033[0m")
        return 0


if __name__ == "__main__":
    # Get the pytest arguments from the command line
    pytest_args = sys.argv[1:]

    # If no arguments are provided, show usage information
    if not pytest_args:
        print("Usage: python pytest_memory_leak_checker.py [pytest_args]")
        print("Example: python pytest_memory_leak_checker.py tests/test_memory_leak.py -v")
        sys.exit(1)

    # Run pytest and check for memory leaks
    exit_code = run_pytest_and_check_for_leaks(pytest_args)

    # Exit with the appropriate code
    sys.exit(exit_code)
