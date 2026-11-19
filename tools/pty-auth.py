#!/usr/bin/env python3
"""pty-auth.py <passfile> <cmd...> — run cmd in a pty, answer password prompts
(ssh/scp/doas/sudo) from passfile without echoing it. Output is passed through."""
import os, pty, sys, select, re
pw = open(sys.argv[1]).read().strip().encode() + b'\n'
pid, fd = pty.fork()
if pid == 0:
    os.execvp(sys.argv[2], sys.argv[2:])
answered, buf = 0, b''
stdin_open = not os.isatty(0) and False
while True:
    try: r, _, _ = select.select([fd], [], [], 1)
    except InterruptedError: continue
    if fd in r:
        try: data = os.read(fd, 4096)
        except OSError: break
        if not data: break
        buf = (buf + data)[-300:]
        os.write(1, data)
        if re.search(rb'(?i)password[^\n]*: ?$', buf) and answered < 6:
            os.write(fd, pw); answered += 1; buf = b''
_, st = os.waitpid(pid, 0)
sys.exit(os.waitstatus_to_exitcode(st))
