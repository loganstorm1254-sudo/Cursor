package com.tapshare.app.nfc

import android.nfc.cardemulation.HostApduService
import android.os.Bundle
import com.tapshare.app.transfer.MediaPipe
import com.tapshare.app.transfer.PeerHandshake
import com.tapshare.app.util.PeerIdentity
import com.tapshare.app.util.ShareSession
import java.util.UUID

/**
 * Presents this phone as an NFC tag even when TapShare is "closed".
 * Another phone in reader mode (gallery open) reads our handshake on tap.
 */
class TapShareHceService : HostApduService() {

    override fun processCommandApdu(commandApdu: ByteArray?, extras: Bundle?): ByteArray {
        if (commandApdu == null || commandApdu.size < 4) return SW_FAIL
        // SELECT AID
        if (commandApdu[1] == INS_SELECT) {
            return SW_OK
        }
        // GET DATA — return peer handshake JSON
        if (commandApdu[1] == INS_GET_DATA) {
            val role = if (ShareSession.get() != null) {
                PeerHandshake.ROLE_HAS_MEDIA
            } else {
                PeerHandshake.ROLE_READY
            }
            val handshake = PeerHandshake(
                peerId = PeerIdentity.id(this),
                displayName = PeerIdentity.displayName(this),
                bluetoothAddress = MediaPipe(this).bluetoothAddress(),
                role = role,
                sessionToken = UUID.randomUUID().toString().take(8)
            )
            val payload = handshake.toBytes()
            return payload + SW_OK
        }
        return SW_FAIL
    }

    override fun onDeactivated(reason: Int) = Unit

    companion object {
        private const val INS_SELECT: Byte = 0xA4.toByte()
        private const val INS_GET_DATA: Byte = 0xCA.toByte()
        private val SW_OK = byteArrayOf(0x90.toByte(), 0x00)
        private val SW_FAIL = byteArrayOf(0x6F.toByte(), 0x00)
    }
}
