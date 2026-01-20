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

arg_parser = argparse.ArgumentParser(
                    prog='mininet_tester.py',
                    description='Collect test TCPLog data using Mininet.',
                    epilog='TCPLog Mininet Testing Utility (C) Peter Warrington 2026')
arg_parser.add_argument("-b", "--bandwidth", type=float, help="Bandwidth of host link.", default=1000)
arg_parser.add_argument("-d", "--delay", type=float, help="Delay in milliseconds.", default=5)
arg_parser.add_argument("-l", "--loss", type=float, help="Loss as percentage.", default=0.2)
arg_parser.add_argument("-o", "--output", type=str, help="File to write test log to.", required=True)
arg_parser.add_argument("-t", "--duration", type=float, help="Length of time in which to test in seconds.", default=10)
arg_parser.add_argument("-s", "--size", type=int, help="Maximum size of upload (mb).", default=512)
arg_parser.add_argument("-q", "--queue-size", type=int, help="Max queue size of switch.", default=1e9)
arg_parser.add_argument("-p", "--pcap", action="store_true", help="Capture pcap as well as tcplog.")

args = arg_parser.parse_args()

class SingleSwitchTopo( Topo ):
    "Single switch connected to k hosts."

    def build( self, k=2, **_opts):
        "k: number of hosts"
        self.k = k
        switch = self.addSwitch( 's1' )
        for h in range(1, k+1 ):
            host = self.addHost( 'h%s' % h )
            #  https://mininet.org/api/classmininet_1_1topo_1_1Topo.html
            self.addLink( host, switch, bw=args.bandwidth, delay=f"{args.delay}ms", loss=args.loss, max_queue_size=args.queue_size)


def main():
    topo = SingleSwitchTopo()

    net = Mininet(topo=topo, link=TCLink)
    net.start()

    h1, h2 = net.get('h1', 'h2')

    tempdir = tempfile.gettempdir()

    make_proc = h1.popen(["make", "install"], stdout=stdout, stderr=stdout)
    make_proc.wait()

    dd_proc = h1.popen(["dd", "if=/dev/urandom", f"of={tempdir}/random", "bs=1M", f"count={args.size}", "iflag=fullblock"], stdout=stdout, stderr=stdout)
    dd_proc.wait()

    server_proc = h1.popen(["python3", "-m", "http.server", "4444", "-d", tempdir], stdout=stdout, stderr=stdout)

    capture_proc = h1.popen(["python3", "scripts/capture_utility.py", "-o", args.output], stdout=stdout, stderr=stdout) # port numbers won't align as tcplog is at kernel level
    
    if args.pcap:
        pcap_proc = h1.popen(["bash", "-c", f"sudo tcpdump -i any -w {args.output}.pcap port 4444"], stdout=stdout, stderr=stdout)

    curl_proc = h2.popen(["curl", "-v", "--http1.0", "--no-keepalive", "--retry", "10", "--retry-all-errors", f"http://{h1.IP()}:4444/random", "-o", "/dev/null"], stdout=stdout, stderr=stdout)

    time.sleep(args.duration)
    capture_proc.send_signal(signal.SIGINT)
    capture_proc.wait()

    net.stop()

if __name__ == '__main__':
    main()
