# WiFi Notify Protocol

Both apps talk over the local LAN only (same Wi‑Fi). No internet or accounts required.

## Ports

| Purpose            | Transport | Port |
|--------------------|----------|------|
| Device discovery   | UDP      | 9876 |
| Notification send  | TCP      | 9877 |

## Discovery

**Sender → broadcast (UDP 9876):**

```text
WIFI_NOTIFY_DISCOVER
```

**Receiver → reply to sender (UDP):**

```text
WIFI_NOTIFY_HERE|<deviceName>
```

Example: `WIFI_NOTIFY_HERE|Kitchen Phone`

## Notification payload

Sender opens a TCP connection to the receiver at port **9877** and writes one UTF‑8 line of JSON, then closes:

```json
{"title":"Hello","message":"Dinner is ready","from":"Living Room"}
```

| Field     | Required | Description                |
|-----------|----------|----------------------------|
| `title`   | yes      | Notification title         |
| `message` | yes      | Notification body text     |
| `from`    | no       | Display name of the sender |

Receiver shows this as a system notification on the phone.
