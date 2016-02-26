progress.pl - Simple progressbar
================================

Usage:
------

progress.pl _pid_
progress.pl _command_ _and_ _arguments_

Description:
------------

Most programs do their operations sequentially over whole file. This tool reads
/proc/_pid_/fdinfo/\* to get position in file or device, and displays this position
as well as percentage and estimated time to finish operation. (Start of operation
is considered to be the start of the proccess.)
