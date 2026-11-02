package com.tapshare.app.transfer

import org.json.JSONObject

/**
 * Compact identity blob exchanged over NFC when two phones touch.
 * MAC + RFCOMM UUID lets the other side open a Bluetooth socket and pull the file.
 */
data class PeerHandshake(
    val peerId: String,
    val displayName: String,
    val bluetoothAddress: String,
    val role: String,
    val sessionToken: String
) {
    fun toBytes(): ByteArray = JSONObject()
        .put("v", 1)
        .put("id", peerId)
        .put("name", displayName)
        .put("bt", bluetoothAddress)
        .put("role", role)
        .put("tok", sessionToken)
        .toString()
        .toByteArray(Charsets.UTF_8)

    companion object {
        const val ROLE_READY = "ready"
        const val ROLE_HAS_MEDIA = "media"

        fun fromBytes(bytes: ByteArray): PeerHandshake? {
            return try {
                val json = JSONObject(String(bytes, Charsets.UTF_8))
                PeerHandshake(
                    peerId = json.getString("id"),
                    displayName = json.optString("name", "Phone"),
                    bluetoothAddress = json.getString("bt"),
                    role = json.optString("role", ROLE_READY),
                    sessionToken = json.optString("tok", "")
                )
            } catch (_: Exception) {
                null
            }
        }
    }
}
