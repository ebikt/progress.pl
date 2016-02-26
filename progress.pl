#!/usr/bin/perl
use strict;

use POSIX ':sys_wait_h';
use Fcntl ':mode';
use Time::HiRes;

my $start = Time::HiRes::time();

my ($child, $running, $exit);

if (not $#ARGV and $ARGV[0] =~ /^\d+/) {
  $child = 1*$ARGV[0];
  $running = sub { kill(0, $child) > 0 };
  $exit = sub { exit 0; };

  open DATA, '<', '/proc/uptime' or die;
  my @s = split(' ', <DATA>);
  close DATA;
  my $system_start = $start - $s[0];
  open DATA, '<', "/proc/$child/stat";
  my @s = split(' ', <DATA>);
  close DATA;
  my $hertz = POSIX::sysconf(POSIX::_SC_CLK_TCK());
  $start = $system_start + $s[21]/$hertz;
} else {
  $child = fork();
  if (defined($child) and not $child) {
    exec(@ARGV);
  }
  $running = sub { waitpid($child, WNOHANG) == 0; };
  $exit = sub {
    my $code = $?;
    my $sig = $? & 127;
    my $core = $? & 128;
    my $status = $? >> 8;
    if ($? & 127) {
      die "progress.pl: Child died by signal $sig".($core ? "( core dumped)":"")."\n";
    } else {
      exit $status;
    }
  };
}


sub prettytime {
  my $t = shift;
  if ($t >= 3600) {
    $t += 59.99;
    return int($t/3600)."h ".int(($t % 3600)/60)."m";
  } elsif ($t >= 60) {
    $t += 0.99;
    return int($t/60)."m ".int($t % 60)."s";
  } else  {
    return int($t+0.99)."s";
  }
}
Time::HiRes::sleep 0.1;
my @lines;
while ($running->()) {
  my @f = glob "/proc/$child/fd/*";
  my @lengths = map { length($_) } @lines;
  @lines = ();
  my $now = Time::HiRes::time();
  my $duration = $now - $start;
  map {
    my $l = readlink $_;
    my @s = stat $l;
    my $size = -1;
    if (S_ISREG($s[2])) {
      s/fd/fdinfo/;
      $size = $s[7];
    } elsif (S_ISBLK($s[2])) {
      s/fd/fdinfo/;
      if (substr($l,0,5) = '/dev/') {
      	local $_;
     	open DATA, '<', '/proc/partitions' or die;
      	while (<DATA>) {
	  my @l = split;
	  if ($l[0] == ($s[6] >> 8) and $l[1] == ($s[6]%256)) {
	    $size = $l[2]*1024;
	  }
	}
	close DATA;
      }
    }
    if ($size >= 0) {
      open DATA, '<', $_;
      my $buf;
      sysread DATA, $buf, 4096;
      close DATA;
      #warn "$buf $l $s[2] --debug--";
      if ( $buf =~ /^pos:\s*(\d+)\s+flags:\s*(\S+)\s/s ) {
	my ($p, $f) = ($1, $2);
	my ($pp, $eta);
	if ($size) {
	  $pp = $size ? sprintf("%5.1f", $p*100.0/$size) : " --.-";
	  my $totaltime = $duration * $size / $p;
	  $eta = "in ".prettytime($totaltime - $duration)." of ".prettytime($totaltime);
	} else {
	  $pp = " --.-";
	  $eta = '-';
	}
	push @lines, "$pp% | $p of $size | $eta | $f | $l";
      }
    }
  } @f;
  print STDERR map { "\e[A" } @lengths;
  for (my $i=0; $i <= $#lines or $i <= $#lengths; $i++) {
    printf STDERR "%-*s\n",$lengths[$i], $lines[$i]
  }
  Time::HiRes::sleep 0.5;
}
$exit->();
