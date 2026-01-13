import matplotlib.pyplot as plt
import matplotlib.ticker as plticker
import numpy as np
import json
import argparse
from datetime import datetime

def to_ms(t):
    return float(t) / 1000.0

def tz_time(e):
    return datetime.fromtimestamp(to_ms(e["time"]))

arg_parser = argparse.ArgumentParser(
                    prog='visualise_utility.py',
                    description='Visualises TCPLog formatted JSON.',
                    epilog='TCPLog Visualisation Utility (C) Peter Warrington 2026')

arg_parser.add_argument("input", type=str)
arg_parser.add_argument("-t", "--timestamp-display", help="Display time as timestamp rather than ms since start.", action='store_true')
arg_parser.add_argument("--rtt", help="Display rtt rather than ssthresh", action='store_true')
args = arg_parser.parse_args()

f = open(args.input)
data = json.loads(f.read())

start_time = to_ms(data[0]["time"])
def ms_from_start(e):
    return to_ms(e["time"]) - start_time

time = ms_from_start
if args.timestamp_display:
    time = tz_time

fig, ax1 = plt.subplots()

cwnd_points = np.array([(time(e), e["data"]["state_variables"]["cwnd"]) for e in data])
ax1.plot(cwnd_points[:,0], cwnd_points[:,1], marker = 'o', color="#00F")

if not args.timestamp_display:
    ax1.set_xlabel("Time (ms since start)")
else:
    ax1.set_xlabel("Time")

ax1.set_ylabel("cwnd")
ax1.yaxis.label.set_color("#00F")
ax1.set_xlim(0, ax1.get_xlim()[1])
ax1.set_ylim(0, ax1.get_ylim()[1])

ax1.xaxis.set_minor_locator(plticker.AutoMinorLocator(8))
ax1.xaxis.set_major_locator(plticker.MaxNLocator(20))

ax2 = ax1.twinx()

if args.rtt:
    ssthr_points = np.array([(time(e), e["data"]["state_variables"]["rtt"]) for e in data])
    ax2.set_ylabel("rtt (microseconds)")
else:
    ssthr_points = np.array([(time(e), e["data"]["state_variables"]["ssthresh"]) for e in data])
    ax2.set_ylabel("ssthresh")
    ax2.set_ylim(ax1.get_ylim())

ax2.plot(ssthr_points[:,0], ssthr_points[:,1], marker = 'o', color="#0F0")

ax2.yaxis.label.set_color("#0F0")

for ax in (ax1, ax2):
    ax.yaxis.set_minor_locator(plticker.AutoMinorLocator(8))
    ax.yaxis.set_major_locator(plticker.MaxNLocator(20))

for e in data:
    if e["name"] == "tcplog:packet_dropped":
        plt.axvline(time(e), color="#F00")

plt.show()