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
import tempfile
import webbrowser
import os

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

root.resizable(0, 0)

# root.tk.call("::tk::unsupported::MacWindowStyle", "appearance", root._w, "aqua") # Force mac light mode
is_dark = bool(root.tk.call("tk::unsupported::MacWindowStyle", "isdark", root._w))

if is_dark:
    mpl_style = './scripts/styles/mac-dark.mplstyle'
else:
    mpl_style = "ggplot"

# Set up event detail (json) display
event_detail = tk.Text(root, height=15, borderwidth=1, relief="solid")

# set up right frame (event list and filter box)
right_frame = tk.Frame(root)
right_frame.rowconfigure(1, weight = 1)

# Set up event list
eventv = ttk.Treeview(master=right_frame, selectmode="browse", columns=("time", "name", "cwnd", "extra"))

eventv.grid(column=0, row=1, sticky="nsew")

eventv.heading("#0", text="Event")
eventv.column('#0', width=60, stretch="no")
eventv.heading("time", text="Time")
eventv.column('time', stretch="no", width=(200 if args.timestamp_display else 60))
eventv.heading("name", text="Event type")
eventv.column('name', stretch="no", width=130)
eventv.heading("cwnd", text="cwnd")
eventv.column('cwnd', stretch="no", width=60)
eventv.heading("extra", text="Extra")

eventv.tag_configure('congestion', background="#FF0000", foreground="#FFFFFF")

filter_on_graph_bool = tk.BooleanVar()
example_select_line = plt.axvline(0, color="#0095FF", linestyle="dotted") # for the legend preview
example_select_line.remove()
last_select_line = None

def event_select_index(i):
    global last_select_line

    event_json = json.dumps(data[i], indent=4)
    event_detail.delete(1.0, tk.END)
    event_detail.insert(tk.END, event_json)

    if last_select_line is not None:
        last_select_line.remove()

    last_select_line = plt.axvline(time(data[i]), color="#0095FF", linestyle="-.")
    canvas.draw_idle()


def event_select_list(*args):
    focus_id = eventv.focus()
    if len(focus_id) > 0:
        index_selected = int(eventv.item(eventv.focus())["text"].replace("#",""))
        event_select_index(index_selected)

eventv.bind_all("<<TreeviewSelect>>", event_select_list)

data_matrix = None

# Populate data structures
def populate_data(filter_terms=[]):
    global data_matrix
    global canvas
    global draw_plot

    # clear event list
    eventv.delete(*eventv.get_children())

    num_data = [] # data of numeric type only for numpy
    for i, e in enumerate(data):
        # determine if should filter out this item
        filtered_out = False
        for t in filter_terms:
            if "=" in t and len(t.split("=")) == 2:
                (k, v) = t.split("=")
                if k == "port":
                    if not (e["data"]["source_port"] == int(v) or e["data"]["destination_port"] == int(v)):
                        filtered_out = True
                        break
                if k == "source_port":
                    if not (e["data"]["source_port"] == int(v)):
                        filtered_out = True
                        break
                if k == "destination_port":
                    if not (e["data"]["destination_port"] == int(v)):
                        filtered_out = True
                        break
                if k == "source_ip":
                    if not (e["data"]["source_ip"] == v):
                        filtered_out = True
                        break
                if k == "destination_ip":
                    if not (e["data"]["destination_ip"] == v):
                        filtered_out = True
                        break
            else:
                # keyword filter
                if not (t in json.dumps(e)):
                    filtered_out = True
                    break
        if filtered_out:
            continue

        # append data
        num_data.append((time(e), e["data"]["state_variables"]["cwnd"], e["data"]["state_variables"]["rtt"], e["data"]["state_variables"]["ssthresh"], e["name"] == "tcplog:packet_dropped"))

        # compute extra field
        extra_fields = ["to", "from", "acked", "cause", "ca_event"]
        extra_text = ", ".join([f"{f}={e["data"][f]}" for f in extra_fields if f in e["data"]])

        # add to event list
        eventv.insert(f"", tk.END, text=f"#{i}", values=(time(e),
            e["name"].replace("tcplog:", ""),
            e["data"]["state_variables"]["cwnd"],
            extra_text),
            tags=(("congestion") if e["name"] == "tcplog:packet_dropped" else ()))

    data_matrix = np.array(num_data)

    if filter_on_graph_bool.get():
        canvas = draw_plot()

populate_data()

# set up filter box
filter_str_var=tk.StringVar()

def filter(e=None):
    filter_terms = filter_str_var.get().split(" ")
    populate_data(filter_terms)

filter_box = ttk.Entry(right_frame, textvariable=filter_str_var)
filter_box.grid(column=0, row=0, sticky="nsew", ipady=5)
filter_box.bind('<Return>', filter)

# set up graph view checkbox
options_frame = ttk.Frame(root)

filter_graph_checkbox = ttk.Checkbutton(options_frame, text="Only show filtered events on graph", variable=filter_on_graph_bool, command=filter)
filter_graph_checkbox.grid(column=0, row=0, sticky="w")

# column titles
D = dict({
    "time": 0,
    "cwnd": 1,
    "rtt": 2,
    "ssthresh": 3,
    "is_loss": 4
})

ttk.Label(root, text="TCPLog Visualisation Utility", font=font.Font(weight="bold")).grid(column=0, row=0, sticky="w")
ttk.Label(root, text="© Peter Warrington 2026").grid(column=0, row=1, sticky="wsew")

def make_plot(style=mpl_style):
    with plt.style.context(style):
        plt.rcParams.update({"font.size": 6})
        fig, ax1 = plt.subplots()
        fig.set_layout_engine("compressed")

        ax1.plot(data_matrix[:,D["time"]], data_matrix[:,D["cwnd"]],
            marker = '.', label="cwnd", zorder=10)

        ax1.set_xlabel(time_label)

        ax1.set_ylim(0, ax1.get_ylim()[1])

        if not args.timestamp_display:
            ax1.set_xlim(0, ax1.get_xlim()[1])
            ax1.xaxis.set_minor_locator(plticker.AutoMinorLocator(8))
            ax1.xaxis.set_major_locator(plticker.MaxNLocator(20))

        ssthresh_points = data_matrix[:, D["ssthresh"]]

        ax1.plot(data_matrix[:,D["time"]], ssthresh_points, marker = '.', label="ssthresh")

        if args.rtt:
            rtt_points = data_matrix[:, D["rtt"]]
            ax1.plot(data_matrix[:,D["time"]], rtt_points, marker = '.', label="rtt (miliseconds)")

        ax1.yaxis.set_minor_locator(plticker.AutoMinorLocator(8))
        ax1.yaxis.set_major_locator(plticker.MaxNLocator(20))

        example_congestion_line = None
        for x in data_matrix[data_matrix[:, D["is_loss"]] != 0][:, D["time"]]:
            example_congestion_line = plt.axvline(x, color="#F00")

        ax1.legend([*ax1.lines[:2], example_congestion_line, example_select_line], [*[l.get_label() for l in ax1.lines[:2]], "Congestion event", "Selected event"],
                    loc='upper right')

        return fig

def draw_plot():
    plotFig = make_plot()
    plotFig.set_dpi(100)

    canvas = FigureCanvasTkAgg(plotFig, master=root)

    def event_select_mpl(event):
        mouse_x = event.xdata
        nearest = np.abs(data_matrix[:, D["time"]] - mouse_x).argmin()

        eventv_entry = eventv.get_children()[nearest]
        eventv.focus(eventv_entry)
        eventv.selection_set(eventv_entry) # this calls event_select_i
        eventv.yview_moveto(float(nearest) / float(data_matrix.shape[0]))

    plotFig.set_picker(True)

    canvas.mpl_connect("button_press_event", event_select_mpl)

    canvas.draw()
    canvas_w = canvas.get_tk_widget()
    canvas_w.grid(column=0, row=2, columnspan=3, sticky="nsew", padx=15)

    toolbar = NavigationToolbar2Tk(canvas, root, pack_toolbar=False)
    toolbar.update()

    toolbar.grid(column=0, row=3, columnspan=3, sticky="w")

    return canvas

def html_print():
    with tempfile.TemporaryDirectory(delete=False) as tmp_dir:
        html_path = os.path.join(tmp_dir, "tcplog_visualiser_output.html")
        img_path = os.path.join(tmp_dir, "tcplog_visualiser_output.png")

        temp_fig = make_plot("ggplot")
        temp_fig.savefig(img_path)

        html = "<!DOCTYPE HTML><html><body>"
        html += """
                <style>
                table, th, td {
                    border: 1px solid black;
                }
                body {
                    text-align: left;
                    font-family: sans-serif;
                    border: 1px solid black;
                }
                table {
                    width: 100%;
                }
                img {
                    margin: 0 auto;
                    display: block;
                }
                .loss {
                    background: red;
                    color: white;
                }
                </style>"""
        html += f"<img src='file://{img_path}'/><br/>"
        html += "<table>"
        html += "<tr>" + "".join([f"<th>{col}</th>" for col in eventv["columns"]]) + "</tr>"
        for event_id in eventv.get_children():
            event = eventv.item(event_id)
            html += (f"<tr{" class='loss'" if "packet_dropped" in event["values"] else ''}>"
                        + "".join([f"<td>{str(v)}</td>" for v in event["values"]])
                    + "</tr>")
        html += "</table>"

        html += """
                <script>
                window.print()
                </script>
                """
        html += "</body></html>"

        with open(html_path, "w") as html_file:
            html_file.write(html)
            webbrowser.open(f"file://{os.path.abspath(html_path)}")

print_button = ttk.Button(options_frame, text="Print graph and table", command=html_print)
print_button.grid(column=0, row=1, sticky="w")

options_frame.grid(column=4, row=3, columnspan=3, sticky="w")

event_detail.grid(column=0, row=4, columnspan=5, sticky="sew", padx=5, pady=5)

right_frame.grid(column=4, row=0, rowspan=3, sticky="nsew", padx=10)

canvas = draw_plot()

tk.mainloop()