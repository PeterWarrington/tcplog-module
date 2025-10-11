# TCPlog format

This document describes the syntax and format of TCPlog output.

TCPlog will implement the 'qlog: Structured Logging for Network Protocols' RFC[^1], currently in late draft stage. This format is designed to be independent of specific network protocols, though has been designed around and was first developed solely for QUIC. Having examined the standard, the qlog standard is flexible enough to be selected for implementation without being onerous or limiting in scope. 

This is because the qlog format is designed around only a few simple base classes required for implementation: 
    `LogFile` -> `Trace` -> `Event`

The draft spec gives an example of a qlog event:
```json
Example qlog event:

{
    "time": 1553986553572,

    "name": "quic:packet_sent",
    "data": { ... },

    "group_id": "127ecc830d98f9d54a42c4f0842aa87e181a",

    "time_format": "relative_to_epoch",

    "ODCID": "127ecc830d98f9d54a42c4f0842aa87e181a"
}

                        Figure 15: Event example
```

Events can have 'any amount of custom fields' according to the specification, for example 'ODCID' for QUIC's Original Destination Connection ID, with group_id being an optional way or grouping related events.

As shown in this example, qlog may use JSON as a logging format, and though the specification is format independent, almost all QUIC qlog implementations use this format. JSON is also trivial to implement, as such I will focus on implementation in this format.

The data field uses the formal specified 'data field definitions' found in standard, though we can be much more relaxed about this in early implementation stages. The spec gives an example of an event with data:
```json
...
{
    "time": 123456,
    "name": "quic:packet_sent",
    "data": {
        "packet_size": 1280,
        "header": {
            "packet_type": "1RTT",
            "packet_number": 123
        },
        "frames": [
            {
                "frame_type": "stream",
                "length": 1000,
                "offset": 456
            },
            {
                "frame_type": "padding"
            }
        ],
        additional_field: true
    }
}

    Figure 29: Example of an extended 'data' field for a conceptual
                        QUIC packet_sent event
```

## TCPlog event types

The following event types are relevant to TCPlog, ordered by approximate development priority: `tcp:in_ack_event`, `tcp:tx_start`, `tcp:cwnd_restart`, `tcp:packet_lost`, `tcp:packet_sent`.

### `tcp:in_ack_event`

This event is called whenever an ack arrives, triggered by the `in_ack_event` callback by the TCP Congestion Control handler. With this information, we are passed the congestion window (`cwnd`) and some flags.

#### Flags

```c
// net/tcp.h
/* Information about inbound ACK, passed to cong_ops->in_ack_event() */
enum tcp_ca_ack_event_flags {
	CA_ACK_SLOWPATH		= (1 << 0),	/* In slow path processing */
	CA_ACK_WIN_UPDATE	= (1 << 1),	/* ACK updated window */
	CA_ACK_ECE		= (1 << 2),	/* ECE bit is set on ack */
};
```

which relate to these internal `net/tcp_input.c` flags:
```c
#define FLAG_SLOWPATH		0x100 /* Do not skip RFC checks for window update.*/
#define FLAG_WIN_UPDATE		0x02 /* Incoming ACK was a window update.	*/
#define FLAG_ECE		0x40 /* ECE in this ACK				*/
```

These flags are very useful in understanding why changes to the congestion window take place.

##### `CA_ACK_SLOWPATH`

`CA_ACK_SLOWPATH` will be flagged if the kernel determines extra processing is needed on an incoming ACK packet to determine if the sending window should be updated. This includes whether the window has been updated in an incoming TCP packet, which is defined in RFC9293 as follows

```
Window:  16 bits

The number of data octets beginning with the one indicated in the acknowledgment field that the sender of this segment is willing to accept. The value is shifted when the window scaling extension is used [47].
```
<https://datatracker.ietf.org/doc/html/rfc9293#section-3.1-6.16.1>

The TCP implementation in the kernel does appear to use the 'window scaling extension' as a way to set its own sending window proportionate to the advertised window, as handled by the `tcp_ack_update_window()` funttion.

The flag should also be set under other conditions where the sending window may be changed, such as when a ECN flag is set, or a duplicate ACK is received.

This is useful to log in TCPlog as it determines if more time is required to process a packet, and helps to understand under what conditions the sending window changes.

##### `CA_ACK_WIN_UPDATE`

A flag that is set whenever the sending window is changed as a result of the reciept of an ACK.

##### `CA_ACK_ECE`

A flag that is set if the ECN Echo bit in the TCP header is set, notifying of congestion.

```c
static bool tcp_ecn_rcv_ecn_echo(const struct tcp_sock *tp, const struct tcphdr *th)
{
	if (th->ece && !th->syn && tcp_ecn_mode_rfc3168(tp))
		return true;
	return false;
}
```

The process of handling this is described in RFC3168:

```
Thus, ECN uses the ECT and CE flags in the IP header (as shown in
Figure 1) for signaling between routers and connection endpoints, and
uses the ECN-Echo and CWR flags in the TCP header (as shown in Figure
4) for TCP-endpoint to TCP-endpoint signaling.  For a TCP connection,
a typical sequence of events in an ECN-based reaction to congestion
is as follows:

    * An ECT codepoint is set in packets transmitted by the sender to
    indicate that ECN is supported by the transport entities for
    these packets.

    * An ECN-capable router detects impending congestion and detects
    that an ECT codepoint is set in the packet it is about to drop.
    Instead of dropping the packet, the router chooses to set the CE
    codepoint in the IP header and forwards the packet.

    * The receiver receives the packet with the CE codepoint set, and
    sets the ECN-Echo flag in its next TCP ACK sent to the sender.

    * The sender receives the TCP ACK with ECN-Echo set, and reacts to
    the congestion as if a packet had been dropped.

    * The sender sets the CWR flag in the TCP header of the next
    packet sent to the receiver to acknowledge its receipt of and
    reaction to the ECN-Echo flag.
```
<https://datatracker.ietf.org/doc/html/rfc3168#section-6.1>

The kernel reacts to the ECN-Echo flag by calling its Content Window Reduce routine:

```c
static void tcp_try_to_open(struct sock *sk, int flag)
{
	...

	if (flag & FLAG_ECE)
		tcp_enter_cwr(sk);

	...
}
```
<https://github.com/torvalds/linux/blob/0739473694c4878513031006829f1030ec850bc2/net/ipv4/tcp_input.c#L2829>

`tcp_init_cwnd_reduction` then reduces the `ssthresh` by multiplative decrease.

`tcp_end_cwnd_reduction` then sets the cwnd to this ssthresh, multiplative decreasing (often halving) the cwnd.



---

[^1]: <https://datatracker.ietf.org/doc/html/draft-ietf-quic-qlog-main-schema-12>