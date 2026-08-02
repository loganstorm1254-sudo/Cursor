package com.nova.ai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import kotlin.math.abs
import kotlin.random.Random

/**
 * Runs the real encrypted model that ships in the APK on the host JVM and
 * checks the Kotlin engine reproduces the PyTorch reference logits.
 */
class NovaEngineTest {

    private fun file(path: String): File {
        val f = File(path)
        return if (f.exists()) f else File("app/$path")
    }

    private fun masterKeys(): List<String> =
        file("../MASTER_KEY.txt").readLines()
            .map { it.trim() }
            .filter { it.isNotEmpty() && !it.startsWith("#") }

    private fun loadEngine(key: String? = null): NovaEngine {
        val k = key ?: masterKeys().first()
        val enc = file("src/main/assets/nova_model.enc").readBytes()
        val weights = ModelCrypto.decrypt(k, enc)
        val config = file("src/main/assets/nova_config.txt").readText()
        return NovaEngine(config, weights)
    }

    @Test
    fun wrongKeyIsRejected() {
        val enc = file("src/main/assets/nova_model.enc").readBytes()
        try {
            ModelCrypto.decrypt("sk-nova-wrong-key", enc)
            throw AssertionError("wrong key must not decrypt the model")
        } catch (e: ModelCrypto.WrongKeyException) {
            // expected
        }
    }

    @Test
    fun everyMasterKeyUnlocks() {
        val enc = file("src/main/assets/nova_model.enc").readBytes()
        val keys = masterKeys()
        assertTrue("need at least 2 master keys", keys.size >= 2)
        val first = ModelCrypto.decrypt(keys[0], enc)
        for (k in keys) {
            val w = ModelCrypto.decrypt(k, enc)
            assertEquals("key $k must unwrap the same weights", first.size, w.size)
            assertTrue(first.contentEquals(w))
        }
    }

    @Test
    fun logitsMatchPyTorchReference() {
        val engine = loadEngine()
        val tv = file("src/test/resources/testvector.txt").readLines()
        val promptIds = tv[0].trim().split(" ").map { it.toInt() }
        val refLogits = tv[1].trim().split(" ").map { it.toFloat() }
        val refArgmax = tv[2].trim().toInt()

        val logits = engine.prefill(promptIds)

        var maxDiff = 0f
        for (i in refLogits.indices) {
            maxDiff = maxOf(maxDiff, abs(logits[i] - refLogits[i]))
        }
        assertTrue("logits diverge from PyTorch (maxDiff=$maxDiff)", maxDiff < 0.02f)

        var argmax = 0
        for (i in logits.indices) if (logits[i] > logits[argmax]) argmax = i
        assertEquals("argmax token differs from PyTorch", refArgmax, argmax)
    }

    @Test
    fun generatesSensibleReplies() {
        val engine = loadEngine()
        val prompts = listOf("hello", "tell me a joke", "who are you", "what is 3 plus 4")
        for (p in prompts) {
            val ids = ArrayList<Int>()
            ids.add(engine.tokenId("<user>"))
            ids.addAll(engine.encode(p))
            ids.add(engine.tokenId("<bot>"))
            val out = engine.generate(ids, rng = Random(42))
            val reply = engine.decode(out)
            println("USER: $p\nNOVA: $reply\n")
            assertTrue("empty reply for '$p'", reply.isNotBlank())
        }
    }
}
