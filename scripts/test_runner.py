import unittest
import mininet_tester
from collections import Counter
import os
import sys
import time
from mininet import topo
import json
from datetime import datetime

out_dir = "./automated_test_results"

def setup_mininet(test, mininet_args, wait_func=None):
    print("Setup: Running mininet tester...")
    test.mininet_results = mininet_tester.run(mininet_args, wait_func)
    test.mininet_events = test.mininet_results["traces"][0]["events"]
    test.event_counter = Counter([e["name"] for e in test.mininet_events])
    print("Setup: Mininet tester output gathered.")

class TestFieldVerification(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        setup_mininet(self, {
            "loss": 1
        })
        with open(f"{out_dir}/test_loss_1percent.json", "w") as f:
            f.write(json.dumps(self.mininet_results, indent=4))
    
    def test_is_packets_acked(self):
        self.assertGreater(self.event_counter["tcplog:packets_acked"], 0, "Verify packets have been acked.")
    
    def test_is_packet_drop(self):
        self.assertGreater(self.event_counter["tcplog:packet_dropped"], 0, "Verify packets have been dropped.")
    
    def test_is_state_update(self):
        self.assertGreater(self.event_counter["tcplog:state_updated"], 0, "Verify state updates present.")

class TestTimeoutRetransmission(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        def wait_func(duration):
            time.sleep(duration*(1/3))
            os.system(f"tc qdisc change dev s1-eth1 root netem delay 1000ms")
            time.sleep(duration*(1/3))
            os.system(f"tc qdisc change dev s1-eth1 root netem delay 5ms")
            time.sleep(duration*(1/3))
        setup_mininet(self, {"delay": 5, "host_count": 2}, wait_func=wait_func)
        with open(f"{out_dir}/test_retransmission.json", "w") as f:
            f.write(json.dumps(self.mininet_results, indent=4))
    
    def test_is_retransmission(self):
        retransmission_events = [e for e in self.mininet_events if (
            e["name"] == "tcplog:packet_dropped"
            and
            "cause" in e["data"]
            and
            e["data"]["cause"] == "RETRANSMISSION_TIMEOUT"
        )]
        self.assertGreater(len(retransmission_events), 0, "Verify retransmission timeout observed with mid-connection delay change")

class TestAggressiveReorder(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        def wait_func(duration):
            time.sleep(duration*(1/3))
            os.system(f"tc qdisc change dev s1-eth1 root netem delay 50ms reorder 10% 75%")
            time.sleep(duration*(1/3))
            os.system(f"tc qdisc change dev s1-eth1 root netem delay 50ms reorder 0% 0%")
            time.sleep(duration*(1/3))
        setup_mininet(self, {"delay": 50, "host_count": 2, "loss": 0}, wait_func=wait_func)
        with open(f"{out_dir}/test_reorder.json", "w") as f:
            f.write(json.dumps(self.mininet_results, indent=4))
    
    def test_is_dupack(self):
        dupack_events = [e for e in self.mininet_events if (
            e["name"] == "tcplog:packet_dropped"
            and
            "cause" in e["data"]
            and
            e["data"]["cause"] == "TRIPLE_DUPLICATE_ACKS"
        )]
        self.assertGreater(len(dupack_events), 0, "Verify Triple-Duplicate-Acks observed with mid-connection reordering")

if __name__ == '__main__':
    if os.getuid() != 0:
        print("Must be ran as root.")
        sys.exit(-1)

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    unix_timestamp = int((datetime.now() - datetime(1970, 1, 1)).total_seconds())
    out_dir += f"/{unix_timestamp}"
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    unittest.main()