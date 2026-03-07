import unittest
import mininet_tester
from collections import Counter
import os
import sys
import time
from mininet import topo
import json
from datetime import datetime
from to_qvis import write_qvis

out_dir = "./automated_test_results"

def setup_mininet(test, mininet_args, wait_func=None, capture_args={}):
    print("Setup: Running mininet tester...")
    test.mininet_results = mininet_tester.run(mininet_args, wait_func, capture_args)
    test.mininet_events = test.mininet_results["traces"][0]["events"]
    test.event_counter = Counter([e["name"] for e in test.mininet_events])
    print("Setup: Mininet tester output gathered.")

class TestFieldVerification(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        setup_mininet(self, {
            "host_count": 2, "loss": 0.1
        }, capture_args={"source_ip":"10.0.0.1", "destination_ip": "10.0.0.2", "max_connections": 1})
        with open(f"{out_dir}/test_loss_0_1percent.json", "w") as f:
            f.write(json.dumps(self.mininet_results, indent=4))
        write_qvis(self.mininet_results, f"{out_dir}/QVIS_test_loss_0_1percent.json")

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
        setup_mininet(self,
                      {"delay": 5, "host_count": 2, "loss": 0}, 
                      wait_func=wait_func,
                      capture_args={"source_ip":"10.0.0.1", "destination_ip": "10.0.0.2", "max_connections": 1})
        with open(f"{out_dir}/test_retransmission.json", "w") as f:
            f.write(json.dumps(self.mininet_results, indent=4))
        write_qvis(self.mininet_results, f"{out_dir}/QVIS_test_retransmission.json")
    
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
            os.system(f"tc qdisc change dev s1-eth1 root netem delay 50ms reorder 25% 75%")
            time.sleep(duration*(1/3))
            os.system(f"tc qdisc change dev s1-eth1 root netem delay 50ms reorder 0% 0%")
            time.sleep(duration*(1/3))
        setup_mininet(self,
                      {"delay": 50, "host_count": 2, "loss": 0},
                      wait_func=wait_func,
                      capture_args={"source_ip":"10.0.0.1", "destination_ip": "10.0.0.2", "max_connections": 1})
        with open(f"{out_dir}/test_reorder.json", "w") as f:
            f.write(json.dumps(self.mininet_results, indent=4))
        write_qvis(self.mininet_results, f"{out_dir}/QVIS_test_reorder.json")
    
    def test_is_dupack(self):
        dupack_events = [e for e in self.mininet_events if (
            e["name"] == "tcplog:packet_dropped"
            and
            "cause" in e["data"]
            and
            e["data"]["cause"] == "TRIPLE_DUPLICATE_ACKS"
        )]
        self.assertGreater(len(dupack_events), 0, "Verify Triple-Duplicate-Acks observed with mid-connection reordering")

class TestSuddenLoss(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        def wait_func(duration):
            time.sleep(duration*(0.33))
            os.system(f"tc qdisc change dev s1-eth1 root netem loss random 0.5%")
            time.sleep(duration*(0.20))
            os.system(f"tc qdisc change dev s1-eth1 root netem loss random 0%")
            time.sleep(duration*(0.47))
        setup_mininet(self, 
                      {"delay": 50, "host_count": 2, "loss": 0}, 
                      wait_func=wait_func,
                      capture_args={"source_ip":"10.0.0.1", "destination_ip": "10.0.0.2", "max_connections": 1})
        with open(f"{out_dir}/test_sudden_loss.json", "w") as f:
            f.write(json.dumps(self.mininet_results, indent=4))
        write_qvis(self.mininet_results, f"{out_dir}/QVIS_test_sudden_loss.json")
    
    def test_is_dupack(self):
        dupack_events = [e for e in self.mininet_events if (
            e["name"] == "tcplog:packet_dropped"
            and
            "cause" in e["data"]
            and
            e["data"]["cause"] == "TRIPLE_DUPLICATE_ACKS"
        )]
        self.assertGreater(len(dupack_events), 0, "Verify Triple-Duplicate-Acks observed with sudden high loss.")

    def test_is_prr(self):
        (prr_enter_i, prr_enter_e) = [(i, e) for (i, e) in enumerate(self.mininet_events) if (
            e["name"] == "tcplog:state_updated"
            and
            e["data"]["new"] == "TCP_CA_Recovery"
            and
            e["data"]["in_slow_start"] == False
        )][0]
        (prr_exit_i, prr_exit_e) = [(i, e) for (i, e) in list(enumerate(self.mininet_events))[prr_enter_i+1:] if (
            e["name"] == "tcplog:state_updated"
            and
            e["data"]["new"] == "TCP_CA_Open"
            and
            e["data"]["state_variables"]["cwnd"] == e["data"]["state_variables"]["ssthresh"]
        )][0]
        prr_decrease_events = [e for e in self.mininet_events[prr_enter_i+1:prr_exit_i] if (
            e["name"] == "tcplog:packets_acked"
        )]

        self.assertEqual(prr_enter_e["data"]["state_variables"]["cwnd"], prr_enter_e["data"]["state_variables"]["prior_cwnd"],
                         "Verify that prior_cwnd is set to cwnd on prr loss.")
        self.assertEqual(prr_exit_e["data"]["state_variables"]["cwnd"], prr_exit_e["data"]["state_variables"]["ssthresh"],
                         "Verify that cwnd is equal to ssthresh at end of prr.")
        prr_mid_decrease_e = prr_decrease_events[int(len(prr_decrease_events) / 2)]
        self.assertTrue((prr_mid_decrease_e["data"]["state_variables"]["cwnd"] < prr_enter_e["data"]["state_variables"]["cwnd"]
                         and
                         prr_mid_decrease_e["data"]["state_variables"]["cwnd"] > prr_exit_e["data"]["state_variables"]["cwnd"]
                         ),
                         "Verify that cwnd decreases during PRR.")



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
