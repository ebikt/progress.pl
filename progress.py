#!/usr/bin/env python
import os, sys, re, time, argparse, stat

MYPY = False
if MYPY:
    """
        mypy --strict --disallow-any-expr    progress.py
        mypy --strict --disallow-any-expr -2 progress.py
    """
    from typing import NoReturn, List, Union, Callable, NamedTuple

    # MyPy says that Python 2 does not have `st_rdev` in type of stat_result.
    # But Python 2.7 contains this field in posix.stat_result
    stat_result = NamedTuple('stat_result',[('st_rdev', int), ('st_size', int), ('st_mode', int)])
    def statfn(x): # type: (str) -> stat_result
        return None # type: ignore
else:
    statfn = os.stat

INTERVAL=0.5

class Config: # {{{
    output  = 1
    pid     = -1
    wait    = False
    start   = time.time()
    HZ      = os.sysconf(os.sysconf_names['SC_CLK_TCK']) * 1.0
    running = lambda self: False # type: Callable[[Config],bool]
    retstat = None # type: Union[None,int,str]

    def __init__(self): # type: () -> None # {{{
        parser = argparse.ArgumentParser(description="Show progress on open filedescriptors of program.")
        parser.add_argument('-p','--pid', action="store_true", help="interpret CMD as process id")
        parser.add_argument('-c','--command', action="store_true", help="do not interpret CMD as process id")
        parser.add_argument('-o','--output', default=1, type=int, help="filedescriptor where to output progress (default 1, i.e. stderr)")
        parser.add_argument('cmd', metavar='CMD', nargs='+', help="process id or command and its arguments")
        args = parser.parse_args()
        self.output = int(args.output) #type: ignore
        assert(self.output >= 0)
        if MYPY:
            cmd = ["x", "y"] # typing hack
        cmd = args.cmd
        assert(len(cmd) > 0)

        if not args.pid and not args.command: # type: ignore
            if re.match(r'^\s*\d+\s*$', cmd[0]):
                args.pid = True
            else:
                args.command = True
        elif args.pid and args.command: # type: ignore
            sys.stderr.write("--pid and --command are mutually exclusive\n")
            sys.exit(1)

        if args.pid: # type: ignore
            if len(cmd) > 1:
                sys.stderr.write("Cannot accept any arguments after process id\n")
                sys.exit(1)
            self.pid = int(cmd[0])
            assert(self.pid > 0)
            self.wait = False
            self.start -= self.get_start(os.getpid()) - self.get_start(self.pid)
            self.running = self.kill0 # type: ignore

        if args.command: # type: ignore
            try:
                self.spawn(cmd)
            except Exception as e:
                sys.stderr.write("Cannot launch {}: {}\n".format(" ".join(cmd), str(e)))
                sys.exit(1)
            self.wait = True
            self.running = self.waitfor # type: ignore
    # }}}

    def spawn(self, cmdline): # type: (List[str]) -> None # {{{
        """ Just spawn a command """
        self.pid = os.fork()
        if self.pid == 0:
            os.execvp(cmdline[0], cmdline)
            sys.stderr.write("Cannot execute {}\n".format(" ".join(cmdline)))
            sys.exit(99)
    # }}}

    def get_start(self, pid): # type: (int) -> float # {{{
        """ Get start of programs in seconds of system running since boot """
        with open("/proc/{}/stat".format(pid)) as f:
            return int(f.readline().rsplit(')', 1)[-1].split()[19]) / self.HZ
    # }}}

    def kill0(self): # type: () -> bool # {{{
        try:
            os.kill(self.pid, 0)
            return True
        except Exception:
            return False
    # }}}

    def waitfor(self): # type: () -> bool # {{{
        if self.retstat is not None:
            return False
        retpid, retstat = os.waitpid(self.pid, os.WNOHANG)
        if retpid == 0:
            return True
        assert retpid == self.pid
        if os.WIFEXITED(retstat):
            self.retstat = os.WEXITSTATUS(retstat)
        elif os.WIFSIGNALED(retstat):
            self.retstat = "signal {}".format(os.WTERMSIG(retstat))
        else:
            self.retstat = "unknown return code"
        return False
    # }}}

# }}}

def pretty_time(t): # type: (float) -> str # {{{
    if t >= 3600:
        t += 59.99
        return "{h}h {m}m".format(h = int(t/3600), m = int((t % 3600)/60))
    if t >=60:
        t += 0.99
        return "{m}m {s}s".format(m = int(t/60), s = int(t % 60))
    return "{:.1f}s".format(t)
# }}}

def main(c): # type: (Config) -> int # {{{
    fd_dir     = "/proc/{}/fd/".format(c.pid)
    fdinfo_dir = "/proc/{}/fdinfo/".format(c.pid)
    infore = re.compile(r'(?:^|\n)pos:\s*(\d+)\s*\nflags:\s*(\S+)\s*\n')

    fd_start = {}
    first = True
    old_lines = 0

    widths   = [1] * 13
    dummies  = [' ' for x in widths ]
    spaces   = ' ' * 200
    skipback = ''

    if c.output == 0:
        out = sys.stdout
    elif c.output == 1:
        out = sys.stderr
    else:
        out = os.fdopen(c.output)

    if c.wait:
        time.sleep(INTERVAL)
    while c.running():
        lines      = [] # type: List[List[str]]
        lineidx = 0
        fd_seen = set()
        now = time.time()

        for fd in os.listdir(fd_dir):
            size       = None
            pos        = None
            try:
                s = statfn(fd_dir + fd)
                filename = os.readlink(fd_dir + fd)
                if (stat.S_ISREG(s.st_mode)):
                    size = s.st_size
                elif (stat.S_ISBLK(s.st_mode)):
                    try:
                        with open("/sys/dev/block/{maj}:{min}/size".format(maj = s.st_rdev / 256, min = s.st_rdev % 256)) as f:
                            size = int(f.read())
                    except Exception:
                        pass
                else:
                    continue
                with open(fdinfo_dir + fd) as f:
                    m = infore.match(f.read())
                assert(m)
                pos = int(m.group(1))
                flags = m.group(2)
            except Exception:
                continue
            if first:
                fd_start[fd] = c.start
            elif fd not in fd_start:
                fd_start[fd] = now - INTERVAL
            fd_seen.add(fd)
            if pos and size:
                pretty_pos = "{:5.1f}%".format(pos * 100.0 / size)
                duration   = now - fd_start[fd]
                total_time = duration * size / pos
                etastr     = ['in',pretty_time(total_time - duration), 'of',pretty_time(total_time)]
            elif pos == 0:
                pretty_pos = "  0.0%"
                etastr = ['','-','','-']
            else:
                pretty_pos = " --.-%"
                etastr = ['','-','','-']
            line = ( [ pretty_pos, '|',
                       str(pos) if pos is not None else '-', 'of',
                       str(size) if size is not None else '-', '|' ] +
                     etastr +
                     [ fd, '|', filename ] )
            assert (len(line) == len(widths))
            lines.append(line)
            for i in range(len(line)):
                widths[i] = max(widths[i], len(line[i]))

        fmtstr = " ".join(["{:.%ds}" % (w,) for w in widths]) + "\n"

        out.write(skipback)
        for line in lines:
            out.write(fmtstr.format(*line))
        for i in range(len(lines), old_lines):
            out.write(fmtstr.format(*dummies))

        skipback = '\033[A' * max(len(lines), old_lines)

        old_lines = len(lines)
        first = False
        time.sleep(INTERVAL)
    if c.retstat is None:
        return 0
    else:
        try:
            return int(c.retstat)
        except ValueError:
            sys.stderr.write("Program terminated abnormally ({})".format(c.retstat))
            return 1
# }}}

sys.exit(main(Config()))
