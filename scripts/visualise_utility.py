import matplotlib.pyplot as plt
import numpy as np
import json
import argparse
from datetime import datetime

def time(e):
    return datetime.fromtimestamp(float(e["time"]) / 1000.0)

arg_parser = argparse.ArgumentParser(
                    prog='visualise_utility.py',
                    description='Visualises TCPLog formatted JSON.',
                    epilog='TCPLog Visualisation Utility (C) Peter Warrington 2026')

arg_parser.add_argument("input", type=str)
args = arg_parser.parse_args()

f = open(args.input)
data = json.loads(f.read())

fig, ax1 = plt.subplots()

cwnd_points = np.array([(time(e), e["data"]["state_variables"]["cwnd"]) for e in data])
ax1.plot(cwnd_points[:,0], cwnd_points[:,1], marker = 'o', color="#00F")

ax1.set_xlabel("Time")
ax1.set_ylabel("cwnd")
ax1.yaxis.label.set_color("#00F")

ax2 = ax1.twinx()

ssthr_points = np.array([(time(e), e["data"]["state_variables"]["ssthresh"]) for e in data])
ax2.plot(ssthr_points[:,0], ssthr_points[:,1], marker = 'o', color="#0F0")

ax2.set_ylabel("ssthresh")
ax2.set_ylim(ax1.get_ylim())
ax2.yaxis.label.set_color("#0F0")

for e in data:
    if e["name"] == "tcplog:packet_dropped":
        plt.axvline(time(e), color="#F00")

plt.show()