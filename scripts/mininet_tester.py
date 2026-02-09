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
import threading
import json
import math

import capture_utility

# Bandwidth-Delay product, converted to packet units
def get_default_queue_size(args):
    return ((args.bandwidth*1e6) / (1500*8)) * (args.delay / 1e3)

def args_init(args={}):
    if isinstance(args, argparse.Namespace):
        args = dict(vars(args))
    args = capture_utility.dotdict(args)
    args = capture_utility.dotdict({
        "bandwidth": 100 if args.bandwidth is None else args.bandwidth,
        "delay": 50 if args.delay is None else args.delay,
        "loss": 0.1 if args.loss is None else args.loss,
        "output": None,
        "duration": 10 if args.duration is None else args.duration,
        "size": 512 if args.size is None else args.size,
        "pcap": False if args.pcap is None else args.pcap,
        "host_count": 10 if args.host_count is None else args.host_count,
        "verbose": False if args.verbose is None else args.verbose
    })
    args["queue_size"] = get_default_queue_size(args)
    return args

def _get_args():
    D = args_init()

    arg_parser = argparse.ArgumentParser(
                        prog='mininet_tester.py',
                        description='Collect test TCPLog data using Mininet.',
                        epilog='TCPLog Mininet Testing Utility (C) Peter Warrington 2026')
    arg_parser.add_argument("-b", "--bandwidth", type=float, help="Bandwidth of host link (Megabits per second).", default=D["bandwidth"])
    arg_parser.add_argument("-d", "--delay", type=float, help="Delay in milliseconds.", default=D["delay"])
    arg_parser.add_argument("-l", "--loss", type=float, help="Loss as percentage.", default=D["loss"])
    arg_parser.add_argument("-o", "--output", type=str, help="File to write test log to.", required=True)
    arg_parser.add_argument("-t", "--duration", type=float, help="Length of time in which to test in seconds.", default=D["duration"])
    arg_parser.add_argument("-s", "--size", type=int, help="Maximum size of upload (mb).", default=D["size"])
    arg_parser.add_argument("-q", "--queue-size", type=int, help="Max queue size of switch.")
    arg_parser.add_argument("-p", "--pcap", action="store_true", help="Capture pcap as well as tcplog.", default=D["pcap"])
    arg_parser.add_argument("-n", "--host-count", type=int, help="Number of hosts to test", default=D["host_count"])
    arg_parser.add_argument("-v", "--verbose", action="store_true", help="Print all subprocess output to stdout (default is just errors). Output will interleave and be messy.", default=D["verbose"])

    args = arg_parser.parse_args()
    if args.queue_size is None:
        args.queue_size = get_default_queue_size(args)
    return args

def run(args, wait_func=None):
    args = args_init(args)

    class SingleSwitchTopo( Topo ):
        "Single switch connected to k hosts."

        def build( self, k=2, **_opts):
            "k: number of hosts"
            self.k = k
            switch1 = self.addSwitch('s1')
            switch2 = self.addSwitch('s2')
            switch_count = 2
            self.host_ids = {k:[] for k in range(1,switch_count+1)}
            self.addLink(switch1, switch2,  bw=args.bandwidth, delay=f"{args.delay}ms", loss=args.loss, max_queue_size=args.queue_size)
            for h in range(1, k+1):
                switch_n = math.ceil(switch_count * (h / k))
                switch = [s for s in self.switches() if s == 's%s' % switch_n][0]
                host_id = 'h%s' % h
                host = self.addHost(host_id)
                self.host_ids[switch_n].append(host_id)
                self.addLink( host, switch, bw=args.bandwidth, delay=f"0ms", loss=args.loss, max_queue_size=args.queue_size)

    topo = SingleSwitchTopo(k = args.host_count)

    subprocess.run(["mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True) # force cleanup, setting cleanup=True doesn't always work
    net = Mininet(topo=topo, link=TCLink) 
    net.start()

    # setup environment
    tempdir = tempfile.gettempdir()

    proc_stdout = stdout if args.verbose else subprocess.DEVNULL
    proc_stderr = stdout if args.verbose else subprocess.DEVNULL

    subprocess.run(["make", "install"], stdout=proc_stdout, stderr=proc_stderr, check=True)

    subprocess.run(["dd", "if=/dev/urandom", f"of={tempdir}/random", "bs=1M", f"count={args.size}", "iflag=fullblock"], stdout=proc_stdout, stderr=proc_stderr, check=True)

    # run capture
    capture_stop_flag = threading.Event()
    capture_out = {"result": None}
    capture_proc = threading.Thread(
        target=capture_utility.collect_events, 
        args=(
            capture_utility.dotdict(
                {"quiet": True}
            ),
            capture_stop_flag,
            capture_out
        )
    )
    capture_proc.start()

    if args.pcap:
        subprocess.Popen(["bash", "-c", f"sudo tcpdump -i any -w {args.output}.pcap"], stdout=proc_stdout, stderr=proc_stderr)

    host_procs = []

    switch_n_set = set(topo.host_ids.keys())
    for switch_n in switch_n_set:
        other_switch_n = list(switch_n_set - set([switch_n]))[0]
        switch_host_ids = topo.host_ids[switch_n].copy()
        other_switch_host_ids = topo.host_ids[other_switch_n].copy()
        
        while len(switch_host_ids) > 0:
            host = net.get(switch_host_ids.pop(0))
            other_host = net.get(other_switch_host_ids.pop(0))

            server_proc = host.popen(["python3", "-m", "http.server", "4444", "-d", tempdir], stdout=proc_stdout, stderr=proc_stderr)
            curl_proc = host.popen(["curl", "-v", "--http1.0", "--no-keepalive", 
                                    "--retry", "10", "--retry-all-errors", f"http://{other_host.IP()}:4444/random", 
                                    "-o", "/dev/null"], stdout=proc_stdout, stderr=proc_stderr)

            host_procs.append(server_proc)
            host_procs.append(curl_proc)

    if wait_func is not None:
        wait_func(args.duration)
    else:
        time.sleep(args.duration)
    capture_stop_flag.set()
    capture_proc.join()

    # Ensure any subprocesses created by host.popen are killed
    for p in host_procs:
        p.kill()
        p.wait()

    net.stop()

    events = capture_out["result"]
    log_obj = capture_utility.events_wrap(events, {
        "environment_type": "test",
        "test_environment": "mininet",
        "environment_vars": {
            "delay": args.delay,
            "bandwidth": args.bandwidth,
            "queue_size": args.queue_size
        },
        "file_name": args.output
    })

    return log_obj

if __name__ == '__main__':
    args = _get_args()
    log_obj = run(args)

    if args.output is not None:
        with open(args.output, "w") as f:
            f.write(json.dumps(log_obj, indent=4))
