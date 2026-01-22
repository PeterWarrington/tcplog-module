import matplotlib.pyplot as plt
import matplotlib.ticker as plticker
import numpy as np
import json
import argparse
from datetime import datetime
import tkinter as tk
from tkinter import ttk, font, filedialog, messagebox
from matplotlib.figure import Figure
from matplotlib.backend_bases import key_press_handler
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg,
                                               NavigationToolbar2Tk)

def to_ms(t):
    return float(t) / 1000

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

start_time = data[0]["time"]
def ms_from_start(e):
    return e["time"] - start_time

time = ms_from_start
time_label = "Time"
if args.timestamp_display:
    time = tz_time
else:
    time_label = "Time (ms since start)"

# Set up window
root = tk.Tk()
root.title("TCPLog Visualisation Utility")
root.resizable(False, False)
frame = ttk.Frame(root, padding=10)
frame.grid()

# root.tk.call("::tk::unsupported::MacWindowStyle", "appearance", root._w, "aqua")

# Set up event list
eventv = ttk.Treeview(master=root, selectmode="browse", columns=("time", "name", "cwnd", "extra"))
eventv.heading("#0", text="Event")
eventv.column('#0', width=60, stretch="no")
eventv.heading("time", text="Time")
eventv.column('time', stretch="no", width=(200 if args.timestamp_display else 60))
eventv.heading("name", text="Event type")
eventv.column('name', stretch="no", width=130)
eventv.heading("cwnd", text="cwnd")
eventv.column('cwnd', stretch="no", width=60)
eventv.heading("extra", text="Extra")

eventv.tag_configure('congestion', background="#FF0000")

# Populate data structures
num_data = [] # data of numeric type only for numpy
for i, e in enumerate(data):
    num_data.append((time(e), e["data"]["state_variables"]["cwnd"], e["data"]["state_variables"]["rtt"], e["data"]["state_variables"]["ssthresh"], e["name"] == "tcplog:packet_dropped"))

    # compute extra field
    extra_fields = ["to", "from", "acked", "cause", "ca_event"]
    extra_text = ", ".join([f"{f}={e["data"][f]}" for f in extra_fields if f in e["data"]])
    eventv.insert(f"", tk.END, text=f"#{i}", values=(time(e),
        e["name"].replace("tcplog:", ""),
        e["data"]["state_variables"]["cwnd"],
        extra_text),
        tags=(("congestion") if e["name"] == "tcplog:packet_dropped" else ()))
data_matrix = np.array(num_data)

# column titles
D = dict({
    "time": 0,
    "cwnd": 1,
    "rtt": 2,
    "ssthresh": 3,
    "is_loss": 4
})

def makePlot():
    plt.rcParams.update({"font.size": 6})
    fig, ax1 = plt.subplots()

    ax1.plot(data_matrix[:,D["time"]], data_matrix[:,D["cwnd"]], marker = 'o', color="#00F")

    ax1.set_xlabel(time_label)

    ax1.set_ylabel("cwnd")
    ax1.yaxis.label.set_color("#00F")

    ax1.set_ylim(0, ax1.get_ylim()[1])

    if not args.timestamp_display:
        ax1.set_xlim(0, ax1.get_xlim()[1])
        ax1.xaxis.set_minor_locator(plticker.AutoMinorLocator(8))
        ax1.xaxis.set_major_locator(plticker.MaxNLocator(20))

    ax2 = ax1.twinx()

    if args.rtt:
        data_points = data_matrix[:, D["rtt"]]
        ax2.set_ylabel("rtt (microseconds)")
    else:
        data_points = data_matrix[:, D["ssthresh"]]
        ax2.set_ylabel("ssthresh")
        ax2.set_ylim(ax1.get_ylim())

    ax2.plot(data_matrix[:,D["time"]], data_points, marker = 'o', color="#0F0")

    ax2.yaxis.label.set_color("#0F0")

    for ax in (ax1, ax2):
        ax.yaxis.set_minor_locator(plticker.AutoMinorLocator(8))
        ax.yaxis.set_major_locator(plticker.MaxNLocator(20))

    for x in data_matrix[data_matrix[:, D["is_loss"]] != 0][:, D["time"]]:
        plt.axvline(x, color="#F00")

    return fig

ttk.Label(frame, text="TCPLog Visualisation Utility", font=font.Font(weight="bold")).grid(column=0, row=0, sticky="w")
ttk.Label(frame, text="© Peter Warrington 2026").grid(column=0, row=1, sticky="w")

plotFig = makePlot()
plotFig.set_dpi(100)

canvas = FigureCanvasTkAgg(plotFig, master=root)
canvas.draw()
canvas.get_tk_widget().grid(column=0, row=2, columnspan=3, sticky="nsew")

toolbar = NavigationToolbar2Tk(canvas, root, pack_toolbar=False)
toolbar.update()

toolbar.grid(column=0, row=3, columnspan=3, sticky="w")

eventv.grid(column=4, row=2, rowspan=1, sticky="nsew", padx=10)

tk.mainloop()