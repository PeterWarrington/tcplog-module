# Test design

- It is important to design and list the tests to perform using TCPlog and Mininet to demonstrate this project's utility and effectiveness.
- These tests should demonstrate as broad a range of real-world congestion-control behaviour as possible.
- These tests should be designed as unit tests **[U]** (i.e. with clear parameter and result specifications) or as experimental tests **[E]** (without clear result expectations, collected for analysis - may later be transformed to unit tests).

## Test outline

1. **[U]** Test to verify that congestion events are recorded. Existence of `packet_dropped` events in capture with 1% loss.
2. **[U]** Test for Timeout-Retransmission loss. Will require an interrupt parameter of some kind. Vary delay?
3. **[U]** Test for Triple-Duplicate-Ack caused by aggressive reordering. Reordering can be set with Mininet tc options: <https://www.man7.org/linux/man-pages/man8/tc-netem.8.html>.
4. **[U]** Test for Triple-Duplicate-Ack caused by loss.
5. **[E]** Test how cross-traffic affects results.
6. **[E]** Test over multiple middle-boxes and links.
7. **[U]** Test for PRR behaviour on Triple-Duplicate-Ack.
8. **[U]** Test for multiplicative decrease on Triple-Duplicate-Ack.
9. **[U]** Test for cwnd reset on Timeout-Retransmission loss.
10. **[U]** Test that ssthresh is reached, and not immediately, during PRR.