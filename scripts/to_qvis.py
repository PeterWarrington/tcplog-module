import json
import sys
import copy

def tcp_log_to_qvis(tcp_log):
    tcp_log = copy.deepcopy(tcp_log)
    tcp_log["qlog_version"] = "0.3"
    tcp_log["qlog_format"] = "JSON"

    trace = tcp_log["traces"][0]
    events = trace["events"]

    base_time = events[0]["time"]

    new_events = []

    packet_counter = 0

    for e in events:
        e["time"] = e["time"] - base_time

        for k, v in e["data"]["state_variables"].items():
            if k == "cwnd":
                e["data"]["cwnd"] = v
            elif k == "ssthresh":
                e["data"]["ssthresh"] = v
            elif k == "rtt":
                e["data"]["latest_rtt"] = v
            elif k == "in_flight":
                e["data"]["bytes_in_flight"] = v

        if e["name"] == "tcplog:packets_acked":
            e["name"] = "recovery:metrics_updated"

        if e["name"] == "tcplog:packet_dropped":
            e["name"] = "recovery:packet_lost"

        e["data"]["header"] = {
            "packet_number": packet_counter,
            "packet_type": "1RTT"
        }

        new_events.append(e)

        if e["name"] == "recovery:metrics_updated":
            packet_counter += 1
            new_events.append({
                "name": "transport:packet_sent",
                "time": e["time"],
                "data": {
                    "header": {
                        "packet_number": packet_counter,
                        "packet_type": "1RTT"
                    },
                    "raw": {
                        "length": 1500
                    }
                }
            })
            new_events.append({
                "name": "transport:packet_received",
                "time": e["time"],
                "data": {
                    "header": {
                        "packet_number": packet_counter,
                        "packet_type": "1RTT"
                    },
                    "raw": {
                        "length": 1500
                    }
                }
            })

    trace["events"] = new_events
    return tcp_log


def write_qvis(tcp_log, outputfilename):
    qvis = tcp_log_to_qvis(tcp_log)
    with open(outputfilename, "w") as f:
        json.dump(qvis, f)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python to_qvis.py <tcp_log.json> <qvis.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        tcp_log = json.load(f)

    write_qvis(tcp_log, sys.argv[2])