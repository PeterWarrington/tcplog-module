import unittest
import mininet_tester
from collections import Counter
import os
import sys

class TestFieldVerification(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        mininet_args = mininet_tester.args_init({
            "loss": 1
        })
        print("Setup: Running mininet tester...")
        self.mininet_results = mininet_tester.run(mininet_args)
        self.mininet_events = self.mininet_results["traces"][0]["events"]
        self.event_counter = Counter([e["name"] for e in self.mininet_events])
        print("Setup: Mininet tester output gathered.")
    
    def test_is_packets_acked(self):
        self.assertGreater(self.event_counter["tcplog:packets_acked"], 0, "Verify packets have been acked.")
    
    def test_is_packet_drop(self):
        self.assertGreater(self.event_counter["tcplog:packet_dropped"], 0, "Verify packets have been dropped.")
    
    def test_is_state_update(self):
        self.assertGreater(self.event_counter["tcplog:state_updated"], 0, "Verify state updates present.")

if __name__ == '__main__':
    if os.getuid() != 0:
        print("Must be ran as root.")
        sys.exit(-1)

    unittest.main()