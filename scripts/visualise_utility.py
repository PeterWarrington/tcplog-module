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

points = np.array([(time(e), e["data"]["state_variables"]["cwnd"]) for e in data])
plt.plot(points[:,0], points[:,1], marker = 'o')

for e in data:
    if e["name"] == "tcplog:packet_dropped":
        plt.axvline(time(e), color="#F00")

plt.xlabel("Time")
plt.ylabel("cwnd")

plt.show()