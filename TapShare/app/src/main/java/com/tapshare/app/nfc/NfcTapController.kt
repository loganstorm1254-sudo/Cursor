package com.tapshare.app.nfc

import android.app.Activity
import android.nfc.NfcAdapter
import android.nfc.Tag
import android.nfc.tech.IsoDep
import android.os.Bundle
import com.tapshare.app.transfer.PeerHandshake

/**
 * While Gallery / PhotoViewer is on screen, enable NFC reader mode so tapping
 * another TapShare phone (HCE) triggers a share.
 */
class NfcTapController(
    private val activity: Activity,
    private val onPeer: (PeerHandshake) -> Unit
) : NfcAdapter.ReaderCallback {

    private val adapter: NfcAdapter? = NfcAdapter.getDefaultAdapter(activity)

    fun isAvailable(): Boolean = adapter != null

    fun isEnabled(): Boolean = adapter?.isEnabled == true

    fun start() {
        val nfc = adapter ?: return
        val extras = Bundle().apply {
            putInt(NfcAdapter.EXTRA_READER_PRESENCE_CHECK_DELAY, 250)
        }
        nfc.enableReaderMode(
            activity,
            this,
            NfcAdapter.FLAG_READER_NFC_A or
                NfcAdapter.FLAG_READER_NFC_B or
                NfcAdapter.FLAG_READER_SKIP_NDEF_CHECK,
            extras
        )
    }

    fun stop() {
        adapter?.disableReaderMode(activity)
    }

    override fun onTagDiscovered(tag: Tag?) {
        if (tag == null) return
        val iso = IsoDep.get(tag) ?: return
        try {
            iso.connect()
            iso.timeout = 3000
            // SELECT TapShare AID F05441505348523031
            val select = hexToBytes("00A4040009F05441505348523031")
            val selectResp = iso.transceive(select)
            if (!endsWithOk(selectResp)) return
            val getData = hexToBytes("00CA000000")
            val dataResp = iso.transceive(getData)
            if (!endsWithOk(dataResp) || dataResp.size <= 2) return
            val payload = dataResp.copyOfRange(0, dataResp.size - 2)
            val peer = PeerHandshake.fromBytes(payload) ?: return
            activity.runOnUiThread { onPeer(peer) }
        } catch (_: Exception) {
        } finally {
            try {
                iso.close()
            } catch (_: Exception) {
            }
        }
    }

    private fun endsWithOk(bytes: ByteArray): Boolean {
        return bytes.size >= 2 &&
            bytes[bytes.size - 2] == 0x90.toByte() &&
            bytes[bytes.size - 1] == 0x00.toByte()
    }

    private fun hexToBytes(hex: String): ByteArray {
        val clean = hex.replace(" ", "")
        return ByteArray(clean.length / 2) { i ->
            clean.substring(i * 2, i * 2 + 2).toInt(16).toByte()
        }
    }
}
