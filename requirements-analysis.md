# Requirements analysis

This document lists the requirements that the TCPlog project must meet. Minor changes and additions are to be expected as work continues.

\* = Non-core

## Design

- [ ] Have sustainable work plan
- [ ] Create design of logging format
- [ ] Logging compatability with qlog specification, where desirable.
- [ ] Tolerance in logging format for network stack implementation differences, including support for specifically logging individual implementation quirks where relevant.
- [ ] \* Design for how visualisation tools would utilise TCPlog output.

## Module

- [ ] Logs information in a way that an admin user can access.
    To the kernel log ring is fine in the short term but eventually:
    - [ ] Log information to a character device file
- [ ] Log all `cwnd` changes
- [ ] Log TCP standard state changes
- [ ] \* Log kernel implementation state changes
- [ ] \* Log packet sent and received events

## \* Visualisation

- [ ] Web-app visualisation implementation
- [ ] Interactive graph of how `cwnd` changes
- [ ] Graphically represent packets, RTT, and packet loss

## Dissertation

*Beyond the obvious required sections*

- [ ] Description of TCP states
- [ ] Diagrams showing core TCP state changes and Sender-Receiver interactions
    - [ ] Slow start
    - [ ] Congestion Avoidance
- [ ] Description of TCP variables
- [ ] Summarisation of format design, and crucially the choices made
    *Formal specification of specifics best placed elsewhere*
- [ ] Detail of any differences between implementation and standard (little literature on this as yet)

More to be added.