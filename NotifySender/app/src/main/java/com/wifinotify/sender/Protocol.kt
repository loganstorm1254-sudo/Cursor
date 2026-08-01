package com.wifinotify.sender

import java.util.UUID

object Protocol {
    /** Shared RFCOMM service id — must match the receiver app. */
    val SERVICE_UUID: UUID = UUID.fromString("8f2a6c1e-4b9d-4e7a-9c31-0d5f2b8a7e44")
    const val SERVICE_NAME = "NotifyReceiver"
}
