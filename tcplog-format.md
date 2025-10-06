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
```
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

The following event types are relevant to TCPlog, ordered by approximate development priority: `tcp:in_ack_event`, `tcp:tx_start`, `tcp:cwnd_restart`, `tcp:packet_lost`, `tcp:packet_sent` (we have access to the actual packets being sent via the raw socket pointer passed by the kernel).

---

[^1]: <https://datatracker.ietf.org/doc/html/draft-ietf-quic-qlog-main-schema-12>