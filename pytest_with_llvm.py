# 以下のコマンドで LLVM 付きでテストを実行できる
# lldb-18 --batch -o 'command script import pytest_with_llvm.py' -o 'test'
import sys
import time

import lldb


def test(debugger, command, result, internal_dict):
    debugger.HandleCommand("settings set target.process.follow-fork-mode child")

    target = debugger.CreateTargetWithFileAndArch("uv", lldb.LLDB_ARCH_DEFAULT)
    process = target.LaunchSimple(["run", "pytest", "tests/test_capability.py", "-s"], None, None)

    if not process:
        print("Error: could not launch process")
        return

    while True:
        time.sleep(1.0)
        state = process.GetState()

        if state == lldb.eStateExited:
            exit_status = process.GetExitStatus()
            # debugger.HandleCommand(f"exit {exit_status}")
            # sys.exit(exit_status)
            debugger.HandleCommand("exit 0")
            sys.exit(0)
        elif state == lldb.eStateStopped:
            thread = process.GetSelectedThread()
            if thread.GetStopReason() == lldb.eStopReasonExec:
                process.Continue()
                continue
            debugger.HandleCommand("bt all")
            debugger.HandleCommand("exit 1")
            sys.exit(1)


# LLDBにスクリプトを初期化してコマンドを追加
def __lldb_init_module(debugger, internal_dict):
    debugger.HandleCommand("command script add -f pytest_with_llvm.test test")
