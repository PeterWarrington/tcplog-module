from io import TextIOBase
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
import time
import base64
from capture_utility import dotdict

class TcplogVisualiser:
    def __init__(self, **kargs):
        is_module = __name__ != '__main__'
        self.args = dotdict(kargs)
        self.file = open(self.args.input)

        self.full_data = json.loads(self.file.read())
        if isinstance(self.full_data, list):
            self.event_data = self.full_data
            self.has_trace_metadata = False
        else:
            self.has_trace_metadata = True
            
            if len(self.full_data["traces"]) == 1:
                self.event_data = self.full_data["traces"][0]["events"]
            else:
                raise ValueError(f"Expected 1 item in 'traces' field, got {len(self.full_data["traces"])}")
            
        self.last_modified = time.ctime(os.path.getmtime(self.file.name))

        self.start_time = self.event_data[0]["time"]
        def ms_from_start(e):
            return e["time"] - self.start_time

        self.get_time = ms_from_start
        self.time_label = "Time"
        if self.args.timestamp_display:
            self.get_time = self._tz_time
        else:
            self.time_label = "Time (ms since start)"

        self.COLUMNS = dict({
            "time": 0,
            "cwnd": 1,
            "rtt": 2,
            "ssthresh": 3,
            "is_loss": 4
        })

        self._setup_tk()

        self.populate_data()

    def _to_ms(self, t):
        return float(t) / 1000

    def _tz_time(self, e):
        return datetime.fromtimestamp(self._to_ms(e["time"]))

    def event_select_index(self, i):
        event_json = json.dumps(self.event_data[i], indent=4)
        self.event_detail.delete(1.0, tk.END)
        self.event_detail.insert(tk.END, event_json)

        if self.last_select_line is not None:
            self.last_select_line.remove()

        self.last_select_line = plt.axvline(self.get_time(self.event_data[i]), color="#0095FF", linestyle="dotted", zorder=30)
        self.canvas.draw_idle()

    def event_select_list(self, *args):
        focus_id = self.eventv.focus()
        if len(focus_id) > 0:
            index_selected = int(self.eventv.item(self.eventv.focus())["text"].replace("#",""))
            self.event_select_index(index_selected)

     # needs to be called in __init__ but not necessarily displayed
    def _setup_tk(self):
        # Set up window
        self.tk_root = tk.Tk()
        self.tk_root.title("TCPLog Visualisation Utility")

        if self.args.force_light:
            self.tk_root.tk.call("::tk::unsupported::MacWindowStyle", "appearance", self.tk_root._w, "aqua") # Force mac light mode
        self.is_dark = bool(self.tk_root.tk.call("tk::unsupported::MacWindowStyle", "isdark", self.tk_root._w))

        if self.is_dark:
            self.mpl_style = './scripts/styles/mac-dark.mplstyle'
        else:
            self.mpl_style = './scripts/styles/light.mplstyle'

        # Set up event detail (json) display
        self.event_detail = tk.Text(self.tk_root, height=15, borderwidth=1, relief="solid")

        # set up right frame (event list and filter box)
        self.right_frame = tk.Frame(self.tk_root)
        self.right_frame.rowconfigure(1, weight = 1)

        # Set up event list
        self.eventv = ttk.Treeview(master=self.right_frame, selectmode="browse", columns=("time", "name", "cwnd", "extra"))

        self.eventv.grid(column=0, row=1, sticky="nsew")

        self.eventv.heading("#0", text="Event")
        self.eventv.column('#0', width=60, stretch="no")
        self.eventv.heading("time", text="Time")
        self.eventv.column('time', stretch="no", width=(200 if self.args.timestamp_display else 60))
        self.eventv.heading("name", text="Event type")
        self.eventv.column('name', stretch="no", width=130)
        self.eventv.heading("cwnd", text="cwnd")
        self.eventv.column('cwnd', stretch="no", width=60)
        self.eventv.heading("extra", text="Extra")

        self.eventv.tag_configure('congestion', background="#FF0000", foreground="#FFFFFF")

        self.tk_filter_on_graph_bool = tk.BooleanVar()
        self.example_select_line = plt.axvline(0, color="#0095FF", linestyle="dotted") # for the legend preview
        self.example_select_line.remove()
        self.last_select_line = None

        self.eventv.bind_all("<<TreeviewSelect>>", self.event_select_list)

        # set up filter box
        self.tk_filter_str_var=tk.StringVar()

        self.tk_filter_box = ttk.Entry(self.right_frame, textvariable=self.tk_filter_str_var)
        self.tk_filter_box.grid(column=0, row=0, sticky="nsew", ipady=5)
        self.tk_filter_box.bind('<Return>', self.filter)

        # set up graph view checkbox
        options_frame = ttk.Frame(self.tk_root)

        self.tk_filter_graph_checkbox = ttk.Checkbutton(options_frame, text="Only show filtered events on graph", variable=self.tk_filter_on_graph_bool, command=self.filter)
        self.tk_filter_graph_checkbox.grid(column=0, row=0, sticky="w", columnspan=2)

        ttk.Label(self.tk_root, text="TCPLog Visualisation Utility", font=font.Font(weight="bold")).grid(column=0, row=0, sticky="w")
        ttk.Label(self.tk_root, text="© Peter Warrington 2026").grid(column=0, row=1, sticky="wsew")

        export_button = ttk.Button(options_frame, text="Export...", command=lambda: self.tk_export())
        export_button.grid(column=0, row=1, sticky="w")

        print_button = ttk.Button(options_frame, text="Print graph and table", command=lambda: self.html_export(print_html=True, display=True))
        print_button.grid(column=1, row=1, sticky="w", padx=10)

        options_frame.grid(column=4, row=3, columnspan=3, sticky="w")

        self.event_detail.grid(column=0, row=4, columnspan=5, sticky="sew", padx=5, pady=5)

        self.right_frame.grid(column=4, row=0, rowspan=3, sticky="nsew", padx=10)

    def is_filtered_out(self, e, filter_terms=[]):
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
        return filtered_out

    # Populate data structures
    def populate_data(self, filter_terms=[]):
        # clear event list
        self.eventv.delete(*self.eventv.get_children())

        num_data = [] # data of numeric type only for numpy
        for i, e in enumerate(self.event_data):
            # determine if should filter out this item
            if self.is_filtered_out(e, filter_terms) or self.get_time(e) < 0:
                continue

            # append data
            num_data.append((self.get_time(e), e["data"]["state_variables"]["cwnd"], e["data"]["state_variables"]["rtt"], e["data"]["state_variables"]["ssthresh"], e["name"] == "tcplog:packet_dropped"))

            # compute extra field
            extra_fields = ["to", "from", "acked", "cause", "ca_event"]
            extra_text = ", ".join([f"{f}={e["data"][f]}" for f in extra_fields if f in e["data"]])

            # add to event list
            self.eventv.insert(f"", tk.END, text=f"#{i}", values=(self.get_time(e),
                e["name"].replace("tcplog:", ""),
                e["data"]["state_variables"]["cwnd"],
                extra_text),
                tags=(("congestion") if e["name"] == "tcplog:packet_dropped" else ()))

        self.event_data_matrix = np.array(num_data)

        if self.tk_filter_on_graph_bool.get():
            self.canvas = self.draw_plot()

    def filter(self, e=None):
        filter_terms = self.tk_filter_str_var.get().split(" ")
        self.populate_data(filter_terms)

    def make_plot(self, style=None):
        if style is None:
            style = self.mpl_style

        with plt.style.context(style):
            plt.rcParams.update({"font.size": 6})
            fig, ax1 = plt.subplots()
            fig.set_layout_engine("compressed")

            ax1.plot(self.event_data_matrix[:,self.COLUMNS["time"]], self.event_data_matrix[:,self.COLUMNS["cwnd"]],
                marker = '.', label="cwnd", zorder=10)

            ax1.set_xlabel(self.time_label)
            ax1.set_ylabel("Window size (packets)")

            ax1.set_ylim(0, ax1.get_ylim()[1])

            if not self.args.timestamp_display:
                ax1.set_xlim(0, ax1.get_xlim()[1])
                ax1.xaxis.set_minor_locator(plticker.AutoMinorLocator(8))
                ax1.xaxis.set_major_locator(plticker.MaxNLocator(20))

            ssthresh_points = self.event_data_matrix[:, self.COLUMNS["ssthresh"]]

            ax1.plot(self.event_data_matrix[:,self.COLUMNS["time"]], ssthresh_points, marker = '.', label="ssthresh")

            if self.args.rtt:
                rtt_points = self.event_data_matrix[:, self.COLUMNS["rtt"]]
                ax1.plot(self.event_data_matrix[:,self.COLUMNS["time"]], rtt_points, marker = '.', label="rtt (miliseconds)")

            ax1.yaxis.set_minor_locator(plticker.AutoMinorLocator(8))
            ax1.yaxis.set_major_locator(plticker.MaxNLocator(20))

            example_congestion_line = None
            loss_matrix = self.event_data_matrix[self.event_data_matrix[:, self.COLUMNS["is_loss"]] != 0]
            for x in loss_matrix:
                example_congestion_line = plt.axvline(x[0], color="#F00", linestyle="-.", zorder=20)
                plt.plot(x[0], x[1], marker="x", color="#F00", zorder=21, markersize=9) 

            leg = ax1.legend([*ax1.lines[:2], example_congestion_line, self.example_select_line], [*[l.get_label() for l in ax1.lines[:2]], "Congestion event", "Selected event"],
                        loc='upper right')
            leg.set_zorder(100)

            return fig

    def draw_plot(self):
        plotFig = self.make_plot()
        plotFig.set_dpi(100)

        self.canvas = FigureCanvasTkAgg(plotFig, master=self.tk_root)

        def event_select_mpl(event):
            mouse_x = event.xdata
            nearest = np.abs(self.event_data_matrix[:, self.COLUMNS["time"]] - mouse_x).argmin()

            eventv_entry = self.eventv.get_children()[nearest]
            self.eventv.focus(eventv_entry)
            self.eventv.selection_set(eventv_entry) # this calls event_select_i
            self.eventv.yview_moveto(float(nearest) / float(self.event_data_matrix.shape[0]))

        plotFig.set_picker(True)

        self.canvas.mpl_connect("button_press_event", event_select_mpl)

        self.canvas.draw()
        self.canvas_w = self.canvas.get_tk_widget()
        self.canvas_w.grid(column=0, row=2, columnspan=3, sticky="nsew", padx=15)

        self.tk_toolbar = NavigationToolbar2Tk(self.canvas, self.tk_root, pack_toolbar=False)
        self.tk_toolbar.update()

        self.tk_toolbar.grid(column=0, row=3, columnspan=3, sticky="w")

        # tkinter canvas tries to change the icon of the app
        try:
            self.tk_root.iconphoto(True, tk.PhotoImage(file = 'tcplog-logo.png'))
        except:
            pass

        return self.canvas

    def html_export(self, html_file=None, print_html=False, display=False):
        with tempfile.TemporaryDirectory(delete=False) as tmp_dir:
            html_file = html_file if html_file is not None else os.path.join(tmp_dir, "tcplog_visualiser_output.html")
            img_path = os.path.join(tmp_dir, "tcplog_visualiser_output.svg")

            temp_fig = self.make_plot('./scripts/styles/light.mplstyle')
            temp_fig.savefig(img_path)

            # convert image to base64 to embed in html
            img_string = "data:image/svg+xml;base64,"
            with open(img_path, "rb") as f:
                img_string += base64.b64encode(f.read()).decode("utf-8")

            html = "<!DOCTYPE HTML><html><body>"
            html += """
                    <style>
                    table, th, td {
                        border: 1px solid black;
                    }
                    body {
                        text-align: left;
                        font-family: sans-serif;
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
            html += f"<h1>{self.args.input}</h1>"

            if self.tk_filter_on_graph_bool.get() and len(self.tk_filter_str_var.get()) > 0:
                html += f"<h2>With filter: {self.tk_filter_str_var.get()}</h2>"

            html += f"<h2>{self.last_modified}</h2>"

            html += f"<h3>TCPLog visualisation</h3>"
            html += f"<img src='{img_string}'/><br/><div style='break-after:page'></div><br/>"
            html += "<table>"
            html += "<tr>" + "".join([f"<th>{col}</th>" for col in self.eventv["columns"]]) + "</tr>"
            for event_id in self.eventv.get_children():
                event = self.eventv.item(event_id)
                html += (f"<tr{" class='loss'" if "packet_dropped" in event["values"] else ''}>"
                            + "".join([f"<td>{str(v)}</td>" for v in event["values"]])
                        + "</tr>")
            html += "</table>"

            if print_html:
                html += """
                        <script>
                        window.print()
                        </script>
                        """
            html += "</body></html>"

            def write_html(file):
                file.write(html)
                if display:
                    webbrowser.open(f"file://{os.path.abspath(file.name)}")

            if isinstance(html_file, TextIOBase):
                write_html(html_file)
            else:
                with open(html_file, "w") as f:
                    write_html(f)

    def csv_export(self, csv_file):
        csv = ""
        csv += ",".join(self.eventv["columns"]) + "\n"
        for event_id in self.eventv.get_children():
            event = self.eventv.item(event_id)
            csv += ",".join([str(v) for v in event["values"]]) + "\n"

        if isinstance(csv_file, TextIOBase):
            csv_file.write(csv)
        else:
            with open(csv_file, "w") as f:
                f.write(csv)
    
    def pdf_export(self, pdf_file):
        self.make_plot('./scripts/styles/light.mplstyle').savefig(pdf_file)

    def tk_export(self):
        file = filedialog.asksaveasfile(initialfile="tcplog_output.csv", defaultextension=".csv", filetypes=[("CSV file", "*.csv"), ("HTML file with embedded image", "*.html"), ("PDF (graph only)", "*.pdf")])
        if file is None: # user canceled
            return
        extension = file.name.split(".")[-1]
        try:
            if extension == "csv":
                self.csv_export(file)
            elif extension == "html":
                self.html_export(file)
            elif extension == "pdf":
                self.pdf_export(file)
            else:
                messagebox.showerror(title="Export failed", message="Export failed\n\nSelected filetype cannot be determined.")
        except Exception as e:
            print(e)
            messagebox.showerror(title="Export failed", message=f"Export failed\n\nAn error occurred: {e}")

    def tk_display(self):
        self.canvas = self.draw_plot()
        self.tk_root.focus_force()
        tk.mainloop()

def parse_args():
    arg_parser = argparse.ArgumentParser(
                prog='visualise_utility.py',
                description='Visualises TCPLog formatted JSON.',
                epilog='TCPLog Visualisation Utility (C) Peter Warrington 2026')

    arg_parser.add_argument("input", type=str)
    arg_parser.add_argument("-t", "--timestamp-display", help="Display time as timestamp rather than ms since start.", action='store_true')
    arg_parser.add_argument("--rtt", help="Display rtt rather than ssthresh.", action='store_true')
    arg_parser.add_argument("--html", type=str, required=False, help="Output printable HTML output to filename without GUI display.", nargs='?', const='_', default='')
    arg_parser.add_argument("--csv", type=str, required=False, help="Output data to a CSV file to filename without GUI display.", nargs='?', const='_', default='')
    arg_parser.add_argument("--pdf", type=str, required=False, help="Output graph to a PDF file without GUI display.", nargs='?', const='_', default='')
    arg_parser.add_argument("--force-light", help="Force light mode style on MacOS.", action='store_true')
    return dict(arg_parser.parse_args()._get_kwargs())

def _main(args):
    visualiser = TcplogVisualiser(**args)
    if args["html"]:
        visualiser.html_export(args["html"])
    elif args["csv"]:
        visualiser.csv_export(args["csv"])
    elif args["pdf"]:
        visualiser.pdf_export(args["pdf"])
    else:
        visualiser.tk_display()

if __name__ == '__main__':
    args = parse_args()
    if os.path.isdir(args["input"]):
        # get each json file in directory and visualise
        for f in os.listdir(args["input"]):
            if f.endswith(".json"):
                print(f"Visualising {f}...")
                if args["html"]:
                    args["html"] = os.path.join(args["input"], f.replace(".json", ".html"))
                elif args["csv"]:
                    args["csv"] = os.path.join(args["input"], f.replace(".json", ".csv"))
                elif args["pdf"]:
                    args["pdf"] = os.path.join(args["input"], f.replace(".json", ".pdf"))
                _main({**args, "input": os.path.join(args["input"], f)})
    else:
        _main(args)