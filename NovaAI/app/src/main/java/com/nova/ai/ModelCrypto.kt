package com.nova.ai

import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * The model weights ship AES-256-GCM encrypted. The master API key IS the
 * decryption key (via SHA-256), so without the correct key the neural network
 * literally cannot be loaded — there is no bypass.
 *
 * Encrypted blob layout: 12-byte IV || ciphertext || 16-byte GCM tag.
 */
object ModelCrypto {

    class WrongKeyException : Exception("Invalid master API key")

    fun decrypt(masterApiKey: String, blob: ByteArray): ByteArray {
        val keyBytes = MessageDigest.getInstance("SHA-256")
            .digest(masterApiKey.trim().toByteArray(Charsets.UTF_8))
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
