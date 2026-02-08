import unittest
import mininet_tester
from collections import Counter
import os
import sys

def setup_mininet(test, mininet_args):
    print("Setup: Running mininet tester...")
    test.mininet_results = mininet_tester.run(mininet_args)
    test.mininet_events = test.mininet_results["traces"][0]["events"]
    test.event_counter = Counter([e["name"] for e in test.mininet_events])
    print("Setup: Mininet tester output gathered.")

class TestFieldVerification(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        setup_mininet(self, {
            "loss": 1
        })
    
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