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

arg_parser.add_argument("-i", "--input-file", type=str, help="Filter specified TCPlog file without capture.")
arg_parser.add_argument("-p", "--port", type=int, help="Filter events to those whose source port OR destination port is set to this value.")
arg_parser.add_argument("-s", "--source-port", type=int, help="Filter events to those whose source port is set to this value.")
arg_parser.add_argument("-d", "--destination-port", type=int, help="Filter events to those whose destination port is set to this value.")
arg_parser.add_argument("-S", "--source-ip", type=str, help="Filter events to those whose source IP address is set to this value.")
arg_parser.add_argument("-D", "--destination-ip", type=str, help="Filter events to those whose destination IP address is set to this value.")
arg_parser.add_argument("-e", "--event-type", type=str, help="Filter events to those with event name specified.")
arg_parser.add_argument("-o", "--output", type=str, help="File to write output to.")

args = arg_parser.parse_args()

def filter_check(json_in):
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
    elif (args.source_ip is not None and
        json_in["data"]["source_ip"] != args.source_ip):
        pass
    elif (args.destination_ip is not None and
        json_in["data"]["destination_ip"] != args.destination_ip):
        pass
    elif (args.event_type is not None and 
        json_in["name"] != args.event_type and 
        json_in["name"] != f"tcplog:{args.event_type}"):
        pass
    else:
        return True 
    return False

events = []

if args.input_file is None:
    if not os.path.exists(TCPLOG_DEVICE):
        print("TCPLog device not initialised. Run `make install` to initiate it.")
        sys.exit(-1)

    if not stat.S_ISCHR(os.stat(TCPLOG_DEVICE).st_mode):
        print(f"{TCPLOG_DEVICE} is not a valid device.")
        sys.exit(-1)

    device = os.open("/dev/tcplog", os.O_RDONLY)

    print("Collecting events... Press CTRL+C to stop.")
    while True:
        try:
            data_in = []
            last_data_item = bytearray()
            new_data_in = os.read(device, 2048)
            while True:
                if b'\x04' in new_data_in:
                    new_data_in_split = [bytearray(ndi) for ndi in new_data_in.split(b'\x04') if len(ndi) > 0]
                    last_data_item += new_data_in_split[0]
                    data_in += [last_data_item]
                    data_in += new_data_in_split[1:-1]
                    break
                else:
                    last_data_item += bytearray(new_data_in)

            for event_data in data_in:
                str_in = str(event_data, encoding="utf-8")
                try:
                    json_in = json.loads(str_in)
                except json.JSONDecodeError as e:
                    print(e)
                    print(str_in)
                    continue

                # Filter checks
                if filter_check(json_in):
                    events.append(json_in)
        except KeyboardInterrupt:
            break
    os.close(device)
else:
    with open(args.input_file) as f:
        events = [e for e in json.loads(f.read()) if filter_check(e)]

output = json.dumps(events, indent=4)

if (args.output is not None):
    with open(args.output, "w") as f:
        f.write(output)
else:
    print(output)
        