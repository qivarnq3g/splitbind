# Git Bash on Windows: path conversion and native process control

Verified behaviours of the MSYS2 layer that Git Bash runs on, and of controlling native Windows processes from it. These bite whenever an agent drives Windows tooling through a POSIX shell. For PowerShell-side quoting and patching, see `powershell-and-patch-portability.md`.

## MSYS path conversion rewrites arguments that are not paths

MSYS converts any argument that *looks* like a POSIX path into a Windows path before the child process sees it, including strings that were never meant to be paths.

- `curl -s -o /dev/null -w "/login -> %{http_code}\n" "$URL"` printed `C:/Program Files/Git/login -> 404/n`. The format string's leading `/login` was rewritten to the Git installation prefix, and `\n` was mangled to `/n`.
- Remedy: `export MSYS_NO_PATHCONV=1` for the command, or keep a leading `/` out of non-path arguments. Verify by echoing the argument the child actually received before concluding the tool itself is broken.

## `$(pwd)` produces a path native Windows binaries cannot resolve

In Git Bash `$(pwd)` yields the MSYS form (`/d/courses/project/dist`). Passing it to `python.exe`, `node.exe` or any non-MSYS binary silently fails — a static file server handed that value as its document root returned 404 for every path while still appearing to start normally.

Pass the Windows form (`D:/courses/project/dist`) to native interpreters. Forward slashes are fine; the drive letter is what matters.

## Flag syntax depends on whether conversion is active

- With `MSYS_NO_PATHCONV=1` in effect, use single-slash flags: `taskkill /PID 1234 /F`.
- The `//FLAG` double-slash escape is only needed while conversion is active. With conversion disabled it is passed through literally and the tool rejects it: `ERROR: Invalid argument/option - '//PID'`.
- `cmd //c "some command"` started an interactive shell and discarded the command, printing the Windows banner and a prompt. Invoke the native tool directly rather than routing through `cmd`.

## `pkill -f` does not terminate native Windows processes

A process launched from Git Bash as `nohup python script.py &` is a native Windows process. `pkill -f script.py` reports success and leaves it running.

Get the Windows PID, then kill it:

```sh
ps -W | grep -i python          # 4th column is the WINPID
netstat -ano | grep "5199 "     # last column is the WINPID of the listener
taskkill /PID <winpid> /F
```

## Several processes can listen on the same loopback port at once

This is the non-obvious one. Windows permits multiple processes to bind `127.0.0.1:<port>` simultaneously without `SO_REUSEADDR` gymnastics and without either one erroring. Incoming connections are then distributed between them **nondeterministically**.

The symptom is contradictory evidence from identical probes: within one batch of requests, `/` returned 200 while `/login` returned 404, then a rebuild changed nothing, because a stale server and the new one were both listening and each request landed on whichever won. Restarting "the" server does not help, because the restart adds a third listener.

Before debugging any local server's behaviour, assert that exactly one listener exists:

```sh
netstat -ano | grep "<port> " | grep LISTENING   # must print exactly one row
```

If it prints more than one row, `taskkill /PID <each> /F` them all and start a single instance. Treat contradictory responses from one local port as a duplicate-listener symptom until that check disproves it, rather than as an application bug.
