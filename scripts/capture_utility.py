import os
import sys
import stat
import json
import argparse

TCPLOG_DEVICE = "/dev/tcplog"

arg_parser = argparse.ArgumentParser(
                    prog='capture_utility.py',
                    description='Collects and filters data from the TCPLog system device.',
                    epilog='TCPLog Capture Utility (C) Peter Warrington 2026')

arg_parser.add_argument("-p", "--port", type=int, help="Filter events to those whose source port OR destination port is set to this value.")
arg_parser.add_argument("-s", "--source-port", type=int, help="Filter events to those whose source port is set to this value.")
arg_parser.add_argument("-d", "--destination-port", type=int, help="Filter events to those whose destination port is set to this value.")

args = arg_parser.parse_args()

if not os.path.exists(TCPLOG_DEVICE):
    print("TCPLog device not initialised. Run `make install` to initiate it.")
    sys.exit(-1)

if not stat.S_ISCHR(os.stat(TCPLOG_DEVICE).st_mode):
    print(f"{TCPLOG_DEVICE} is not a valid device.")
    sys.exit(-1)

device = os.open("/dev/tcplog", os.O_RDONLY)

events = []

print("Collecting events... Press CTRL+C to stop.")
while True:
    try:
        data_in = bytearray()
        while True:
            new_data_in = os.read(device, 2048)
            if b'\x04' in new_data_in:
                data_in += new_data_in[:new_data_in.index(b'\x04')]
                break
            else:
                data_in += new_data_in
                offset += len(new_data_in)
        str_in = str(data_in, encoding="utf-8")
        try:
            json_in = json.loads(str_in)
        except json.JSONDecodeError as e:
            continue

        # Filter checks
        if (args.port is not None and 
            int(json_in["data"]["destination_port"]) != args.port and
            int(json_in["data"]["source_port"]) != args.port):
            pass
        elif (args.source_port is not None and
            int(json_in["data"]["source_port"]) != args.source_port):
            pass
        elif (args.destination_port is not None and
            int(json_in["data"]["destination_port"]) != args.destination_port):
            pass
        else:
            events.append(json_in)
    except KeyboardInterrupt:
        break

print(events)

os.close(device)
        