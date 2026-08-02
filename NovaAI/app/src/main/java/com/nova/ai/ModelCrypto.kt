package com.nova.ai

import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import kotlin.experimental.xor

/**
 * The model weights ship AES-256-GCM encrypted under a random data key (DEK).
 * Each master API key only wraps that DEK, so multiple keys can unlock the
 * same brain. Without a valid key the network literally cannot be loaded.
 *
 * Encrypted blob layout (NOVAK):
 *   "NOVAK" (5) || n_keys (1) || n_keys × wrap(80) || iv(12) || ct+tag
 * where wrap = nonce(16) || xor-ct(32) || hmac-sha256(32).
 *
 * Legacy blobs (no NOVAK magic) still decrypt as single-key AES-GCM with
 * SHA-256(api_key) as the key — kept for older APKs.
 */
object ModelCrypto {

    class WrongKeyException : Exception("Invalid master API key")

    private const val WRAP = 80

    fun decrypt(masterApiKey: String, blob: ByteArray): ByteArray {
        val key = masterApiKey.trim()
        if (blob.size > 6 && blob.copyOfRange(0, 5).contentEquals("NOVAK".toByteArray())) {
            return decryptNovak(key, blob)
        }
        return decryptLegacy(key, blob)
    }

    private fun decryptNovak(apiKey: String, blob: ByteArray): ByteArray {
        val nKeys = blob[5].toInt() and 0xff
        if (nKeys < 1 || nKeys > 32) throw WrongKeyException()
        val wrapsStart = 6
        val wrapsEnd = wrapsStart + nKeys * WRAP
        if (blob.size < wrapsEnd + 12 + 16) throw WrongKeyException()

        var dek: ByteArray? = null
        for (i in 0 until nKeys) {
            val off = wrapsStart + i * WRAP
            dek = tryUnwrap(apiKey, blob, off) ?: continue
            break
        }
        if (dek == null) throw WrongKeyException()

        val iv = blob.copyOfRange(wrapsEnd, wrapsEnd + 12)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(dek, "AES"), GCMParameterSpec(128, iv))
        return try {
            cipher.doFinal(blob, wrapsEnd + 12, blob.size - wrapsEnd - 12)
        } catch (e: Exception) {
            throw WrongKeyException()
        }
    }

    private fun tryUnwrap(apiKey: String, blob: ByteArray, off: Int): ByteArray? {
        val sha = MessageDigest.getInstance("SHA-256")
        val kEnc = sha.digest(("nova-wrap-enc$apiKey").toByteArray(Charsets.UTF_8))
        sha.reset()
        val kMac = sha.digest(("nova-wrap-mac$apiKey").toByteArray(Charsets.UTF_8))
        val nonce = blob.copyOfRange(off, off + 16)
        val ct = blob.copyOfRange(off + 16, off + 48)
        val tag = blob.copyOfRange(off + 48, off + 80)

        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(kMac, "HmacSHA256"))
        mac.update(nonce)
        mac.update(ct)
        if (!MessageDigest.isEqual(mac.doFinal(), tag)) return null

        sha.reset()
        sha.update(kEnc)
        sha.update(nonce)
        sha.update(0)
        val ks = sha.digest()
        return ByteArray(32) { i -> ct[i] xor ks[i] }
    }

    private fun decryptLegacy(masterApiKey: String, blob: ByteArray): ByteArray {
        val keyBytes = MessageDigest.getInstance("SHA-256")
            .digest(masterApiKey.toByteArray(Charsets.UTF_8))
        val iv = blob.copyOfRange(0, 12)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(
            Cipher.DECRYPT_MODE,
            SecretKeySpec(keyBytes, "AES"),
            GCMParameterSpec(128, iv)
        )
        return try {
            cipher.doFinal(blob, 12, blob.size - 12)
        } catch (e: Exception) {
            throw WrongKeyException()
        }
    }
}
