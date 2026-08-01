# Notify Protocol (Bluetooth)

The apps talk over **Bluetooth Classic RFCOMM**. No Wi‑Fi, mobile data, hotspot, or IP addresses.

## Service

| Field | Value |
|-------|-------|
| SDP name | `NotifyReceiver` |
| UUID | `8f2a6c1e-4b9d-4e7a-9c31-0d5f2b8a7e44` |
| Socket | Insecure RFCOMM |

## Payload

Sender writes one UTF‑8 JSON line, then closes:

```json
{"title":"Hello","message":"Dinner is ready","from":"Living Room"}
```

Receiver shows this as a system notification.
