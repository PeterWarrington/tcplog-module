# Based on Mihail's Mininet example code (https://gist.github.com/janev94/b214e3d2fd0b7b26d1959703db115a71)

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
import argparse
import importlib
import tempfile
import time
import os
import signal
from sys import stdout
import subprocess
import random

arg_parser = argparse.ArgumentParser(
                    prog='mininet_tester.py',
                    description='Collect test TCPLog data using Mininet.',
                    epilog='TCPLog Mininet Testing Utility (C) Peter Warrington 2026')
arg_parser.add_argument("-b", "--bandwidth", type=float, help="Bandwidth of host link.", default=100)
arg_parser.add_argument("-d", "--delay", type=float, help="Delay in milliseconds.", default=50)
arg_parser.add_argument("-l", "--loss", type=float, help="Loss as percentage.", default=0.1)
arg_parser.add_argument("-o", "--output", type=str, help="File to write test log to.", required=True)
arg_parser.add_argument("-t", "--duration", type=float, help="Length of time in which to test in seconds.", default=10)
arg_parser.add_argument("-s", "--size", type=int, help="Maximum size of upload (mb).", default=512)
arg_parser.add_argument("-q", "--queue-size", type=int, help="Max queue size of switch.", default=100)
arg_parser.add_argument("-p", "--pcap", action="store_true", help="Capture pcap as well as tcplog.")
arg_parser.add_argument("-n", "--host-count", type=int, help="Number of hosts to test", default=10)

args = arg_parser.parse_args()

host_ids = []

class SingleSwitchTopo( Topo ):
    "Single switch connected to k hosts."

    def build( self, k=2, **_opts):
        "k: number of hosts"
        self.k = k
        switch1 = self.addSwitch('s1')
        switch2 = self.addSwitch('s2')
        self.addLink(switch1, switch2,  bw=args.bandwidth, delay=f"{args.delay}ms", loss=args.loss, max_queue_size=args.queue_size)
        for h in range(1, k+1):
            host_id = 'h%s' % h
            host_ids.append(host_id)
            host = self.addHost(host_id)
            switch = switch1 if h < (k+1) / 2 else switch2
            self.addLink( host, switch, bw=args.bandwidth, delay=f"{args.delay}ms", loss=args.loss, max_queue_size=args.queue_size)


def main():
    topo = SingleSwitchTopo(k = args.host_count)

    net = Mininet(topo=topo, link=TCLink, cleanup=True)
    net.start()

    # setup environment

    tempdir = tempfile.gettempdir()

    make_proc = subprocess.Popen(["make", "install"], stdout=stdout, stderr=stdout)
    make_proc.wait()

    dd_proc = subprocess.Popen(["dd", "if=/dev/urandom", f"of={tempdir}/random", "bs=1M", f"count={args.size}", "iflag=fullblock"], stdout=stdout, stderr=stdout)
    dd_proc.wait()

    # run capture
    capture_proc = subprocess.Popen(["python3", "scripts/capture_utility.py", "-o", args.output], stdout=stdout, stderr=stdout) # port numbers won't align as tcplog is at kernel level

    if args.pcap:
        pcap_proc = subprocess.Popen(["bash", "-c", f"sudo tcpdump -i any -w {args.output}.pcap"], stdout=stdout, stderr=stdout)

    for host_id in random.sample(host_ids, k=len(host_ids)):
        host = net.get(host_id)

        other_host = net.get(random.choice([h for h in host_ids if h != host_id]))

        server_proc = host.popen(["python3", "-m", "http.server", "4444", "-d", tempdir], stdout=stdout, stderr=stdout)
        curl_proc = host.popen(["curl", "-v", "--http1.0", "--no-keepalive", 
                                "--retry", "10", "--retry-all-errors", f"http://{other_host.IP()}:4444/random", 
                                "-o", "/dev/null"], 
                                stdout=stdout, stderr=stdout)

    time.sleep(args.duration)
    capture_proc.send_signal(signal.SIGINT)
    capture_proc.wait()

    net.stop()

if __name__ == '__main__':
    main()
