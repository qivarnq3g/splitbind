# Git Bash on Windows: path conversion and native process control

Verified behaviours of the MSYS2 layer that Git Bash runs on, and of controlling native Windows processes from it. These bite whenever an agent drives Windows tooling through a POSIX shell. For PowerShell-side quoting and patching, see `powershell-and-patch-portability.md`.

## MSYS path conversion rewrites arguments that are not paths

MSYS converts any argument that *looks* like a POSIX path into a Windows path before the child process sees it, including strings that were never meant to be paths.

- `curl -s -o /dev/null -w "/login -> %{http_code}\n" "$URL"` printed `C:/Program Files/Git/login -> 404/n`. The format string's leading `/login` was rewritten to the Git installation prefix, and `\n` was mangled to `/n`.
- Remedy: `export MSYS_NO_PATHCONV=1` for the command, or keep a leading `/` out of non-path arguments. Verify by echoing the argument the child actually received before concluding the tool itself is broken.

## `$(pwd)` produces a path native Windows binaries cannot resolve

In Git Bash `$(pwd)` yields the MSYS form (`/d/courses/project/dist`). Passing it to `python.exe`, `node.exe` or any non-MSYS binary silently fails - a static file server handed that value as its document root returned 404 for every path while still appearing to start normally.

Pass the Windows form (`D:/courses/project/dist`) to native interpreters. Forward slashes are fine; the drive letter is what matters.

The same mismatch hits `/tmp`. A Git Bash heredoc writing to `/tmp/x.md` lands under the Windows user temp directory, but a native `python.exe` opening `/tmp/x.md` resolves it against the current drive root and raises `FileNotFoundError: [Errno 2] No such file or directory: '/tmp/x.md'`. Stage scratch files in the session scratchpad using its Windows-form path and hand that same string to the native interpreter.

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

## Backslash escapes in a heredoc become real control characters

Writing Python source through a shell heredoc silently corrupts backslash escapes. A regex written as `r"<w:tblLook\b[^/]*/>"` inside a `<<'PYEOF'` block reached disk as `r"<w:tblLook\x08[^/]*/>"` - the `\b` had been turned into an actual backspace byte. The file still parsed, the script still ran, and the substitution simply never matched. Nothing failed loudly; a document just came out wrong.

Two things made this expensive to find:

- The corrupted byte is invisible in every normal view. `grep`, `sed -n`, and the editor all render `\x08` as nothing at all, so the line looked exactly right.
- A repair script that searched for the two-character sequence `\b` found nothing and reported success, because the file contained one byte, not two.

Diagnose it by printing `repr()` of the suspect line, or by scanning for control characters:

```python
[hex(ord(c)) for c in open(path, encoding="utf-8").read() if ord(c) < 32 and c not in "\n\t"]
```

Prefer the harness's own file-write tool for source files. Where a heredoc is unavoidable, keep backslashes out of the content, and verify with `repr()` afterwards rather than trusting that the text looks correct.


## Sự xuất hiện của một file không có nghĩa là trình cài đặt đã xong

Chờ một cài đặt MSI kết thúc bằng `until [ -f ".../soffice.exe" ]; do sleep 5; done` bắn
sớm: MSI chép file theo từng bước, nên file đích tồn tại từ giữa quá trình cài trong khi
trình cài vẫn đang chạy. Chạy binary ở thời điểm đó trả về `0xC0000135`
(`STATUS_DLL_NOT_FOUND`, hiện dưới dạng `ERRORLEVEL=-1073741515`), rất dễ bị chẩn đoán
nhầm thành thiếu Visual C++ Runtime.

Chờ theo tiến trình `msiexec` cũng sai: Windows luôn giữ một thể hiện dịch vụ
`msiexec.exe /V` chạy thường trực, nên điều kiện "không còn tiến trình msiexec nào"
không bao giờ thoả.

Hai điều kiện chờ đúng, theo thứ tự ưu tiên:

1. **Chờ chính lệnh cài thoát.** Chạy `winget install` ở nền rồi đợi tiến trình đó kết
   thúc. Đây là tín hiệu chính xác nhất vì do chính trình cài phát ra.
2. **Hỏi sổ đăng ký gói**, không hỏi hệ thống tệp:

```bash
until winget list --id <PackageId> --exact >/dev/null 2>&1; do sleep 10; done
```

`winget list` chỉ báo có gói sau khi cài hoàn tất và đăng ký xong.

Nguyên tắc chung: chờ theo **tín hiệu hoàn tất do chính tác nhân phát ra**, không chờ theo
một tác dụng phụ trung gian mà tác nhân đó tạo ra dọc đường.
