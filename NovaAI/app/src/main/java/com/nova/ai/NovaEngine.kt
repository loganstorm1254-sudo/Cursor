package com.nova.ai

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Locale
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.sqrt
import kotlin.math.tanh
import kotlin.random.Random

/**
 * Pure-Kotlin inference engine for Nova: a word-level GPT (decoder-only
 * transformer) trained from scratch. Runs fully on-device with a KV cache.
 *
 * Config format (nova_config.txt):
 *   line 1: "<n_layer> <n_head> <n_embd> <block_size>"
 *   remaining lines: vocabulary, one token per line (index = line number - 2)
 *
 * Weight file: raw little-endian float32 in this exact order:
 *   tok_emb [V,D], pos_emb [T,D], then per layer:
 *     ln1.w ln1.b qkv.w[3D,D] qkv.b proj.w[D,D] proj.b
 *     ln2.w ln2.b fc.w[4D,D] fc.b fc2.w[D,4D] fc2.b
 *   then lnf.w lnf.b. Output head is weight-tied to tok_emb.
 */
class NovaEngine(configText: String, weightBytes: ByteArray) {

    val nLayer: Int
    val nHead: Int
    val nEmbd: Int
    val blockSize: Int
    val vocab: List<String>
    private val stoi: Map<String, Int>
    private val w: FloatArray

    // per-tensor offsets into w
    private val offTok: Int
    private val offPos: Int
    private val layerOff: IntArray   // offset of each layer's first tensor
    private val offLnf: Int

    private val endId: Int
    private val unkId: Int

    // KV cache: [layer][pos * nEmbd + d]
    private lateinit var kCache: Array<FloatArray>
    private lateinit var vCache: Array<FloatArray>
    private var curPos = 0

    init {
        val lines = configText.trim().lines()
        val dims = lines[0].trim().split(" ").map { it.toInt() }
        nLayer = dims[0]; nHead = dims[1]; nEmbd = dims[2]; blockSize = dims[3]
        vocab = lines.drop(1).map { it.trim() }
        stoi = vocab.withIndex().associate { (i, s) -> s to i }
        endId = stoi.getValue("<end>")
        unkId = stoi.getValue("<unk>")

        val buf = ByteBuffer.wrap(weightBytes).order(ByteOrder.LITTLE_ENDIAN)
        w = FloatArray(weightBytes.size / 4)
        buf.asFloatBuffer().get(w)

        val d = nEmbd
        var o = 0
        offTok = o; o += vocab.size * d
        offPos = o; o += blockSize * d
        val perLayer = d + d + 3 * d * d + 3 * d + d * d + d +
                d + d + 4 * d * d + 4 * d + d * 4 * d + d
        layerOff = IntArray(nLayer) { i -> o + i * perLayer }
        o += nLayer * perLayer
        offLnf = o; o += 2 * d
        require(o == w.size) { "weight size mismatch: expected $o floats, got ${w.size}" }
        reset()
    }

    fun reset() {
        kCache = Array(nLayer) { FloatArray(blockSize * nEmbd) }
        vCache = Array(nLayer) { FloatArray(blockSize * nEmbd) }
        curPos = 0
    }

    val position: Int get() = curPos

    // ---- tokenizer ----

    fun encode(text: String): List<Int> {
        val cleaned = text.lowercase(Locale.US)
            .replace(Regex("([.,!?;:'+])"), " $1 ")
        return cleaned.split(Regex("\\s+")).filter { it.isNotEmpty() }
            .map { stoi[it] ?: unkId }
    }

    fun decode(ids: List<Int>): String {
        val sb = StringBuilder()
        for (id in ids) {
            val t = vocab[id]
            if (t == "<end>" || t == "<user>" || t == "<bot>") continue
            if (sb.isNotEmpty() && t.length == 1 && t[0] in ".,!?;:'") {
                sb.append(t)
            } else if (sb.isNotEmpty() && sb.last() == '\'') {
                sb.append(t)
            } else {
                if (sb.isNotEmpty()) sb.append(' ')
                sb.append(t)
            }
        }
        var s = sb.toString()
        s = s.replace(Regex("\\bi\\b"), "I")
        // capitalize sentence starts
        val out = StringBuilder(s.length)
        var capNext = true
        for (c in s) {
            out.append(if (capNext && c.isLetter()) { capNext = false; c.uppercaseChar() } else c)
            if (c == '.' || c == '!' || c == '?') capNext = true
        }
        return out.toString()
    }

    fun tokenId(word: String): Int = stoi[word] ?: unkId

    fun knowsWord(word: String): Boolean = stoi.containsKey(word)

    // ---- transformer forward pass (one token, KV cached) ----

    private fun layerNorm(x: FloatArray, wOff: Int, bOff: Int): FloatArray {
        val d = x.size
        var mean = 0f
        for (v in x) mean += v
        mean /= d
        var varr = 0f
        for (v in x) { val t = v - mean; varr += t * t }
        varr /= d
        val inv = 1f / sqrt(varr + 1e-5f)
        val out = FloatArray(d)
        for (i in 0 until d) out[i] = (x[i] - mean) * inv * w[wOff + i] + w[bOff + i]
        return out
    }

    /** y = W x + b where W is [rows, cols] row-major at wOff */
    private fun matvec(wOff: Int, bOff: Int, x: FloatArray, rows: Int): FloatArray {
        val cols = x.size
        val out = FloatArray(rows)
        for (r in 0 until rows) {
            var acc = 0f
            val base = wOff + r * cols
            for (c in 0 until cols) acc += w[base + c] * x[c]
            out[r] = acc + w[bOff + r]
        }
        return out
    }

    private fun geluTanh(x: Float): Float {
        val c = 0.7978845608028654f // sqrt(2/pi)
        return 0.5f * x * (1f + tanh(c * (x + 0.044715f * x * x * x)))
    }

    /** Feed one token at the current position; returns logits over the vocab. */
    fun step(tokenId: Int): FloatArray {
        require(curPos < blockSize) { "context window full" }
        val d = nEmbd
        val hd = d / nHead
        val pos = curPos

        val x = FloatArray(d)
        for (i in 0 until d) x[i] = w[offTok + tokenId * d + i] + w[offPos + pos * d + i]

        for (l in 0 until nLayer) {
            var o = layerOff[l]
            val ln1w = o; o += d
            val ln1b = o; o += d
            val qkvW = o; o += 3 * d * d
            val qkvB = o; o += 3 * d
            val projW = o; o += d * d
            val projB = o; o += d
            val ln2w = o; o += d
            val ln2b = o; o += d
            val fcW = o; o += 4 * d * d
            val fcB = o; o += 4 * d
            val fc2W = o; o += d * 4 * d
            val fc2B = o

            val h = layerNorm(x, ln1w, ln1b)
            val qkv = matvec(qkvW, qkvB, h, 3 * d)
            val kc = kCache[l]
            val vc = vCache[l]
            for (i in 0 until d) {
                kc[pos * d + i] = qkv[d + i]
                vc[pos * d + i] = qkv[2 * d + i]
            }

            val att = FloatArray(d)
            val scale = 1f / sqrt(hd.toFloat())
            val scores = FloatArray(pos + 1)
            for (head in 0 until nHead) {
                val hb = head * hd
                var maxS = Float.NEGATIVE_INFINITY
                for (t in 0..pos) {
                    var s = 0f
                    for (j in 0 until hd) s += qkv[hb + j] * kc[t * d + hb + j]
                    s *= scale
                    scores[t] = s
                    if (s > maxS) maxS = s
                }
                var sum = 0f
                for (t in 0..pos) { scores[t] = exp(scores[t] - maxS); sum += scores[t] }
                for (t in 0..pos) {
                    val p = scores[t] / sum
                    for (j in 0 until hd) att[hb + j] += p * vc[t * d + hb + j]
                }
            }
            val attOut = matvec(projW, projB, att, d)
            for (i in 0 until d) x[i] += attOut[i]

            val h2 = layerNorm(x, ln2w, ln2b)
            val f = matvec(fcW, fcB, h2, 4 * d)
            for (i in 0 until 4 * d) f[i] = geluTanh(f[i])
            val f2 = matvec(fc2W, fc2B, f, d)
            for (i in 0 until d) x[i] += f2[i]
        }

        val hf = layerNorm(x, offLnf, offLnf + d)
        val logits = FloatArray(vocab.size)
        for (v in vocab.indices) {
            var acc = 0f
            val base = offTok + v * d
            for (i in 0 until d) acc += w[base + i] * hf[i]
            logits[v] = acc
        }
        curPos++
        return logits
    }

    /** Feed a sequence of prompt tokens; returns logits after the last one. */
    fun prefill(ids: List<Int>): FloatArray {
        var logits = FloatArray(0)
        for (id in ids) logits = step(id)
        return logits
    }

    // ---- sampling ----

    fun sample(logits: FloatArray, temperature: Float, topK: Int, rng: Random): Int {
        val scaled = FloatArray(logits.size) { logits[it] / temperature }
        val idx = scaled.indices.sortedByDescending { scaled[it] }.take(topK)
        var maxV = Float.NEGATIVE_INFINITY
        for (i in idx) if (scaled[i] > maxV) maxV = scaled[i]
        var sum = 0.0
        val probs = DoubleArray(idx.size)
        for ((n, i) in idx.withIndex()) {
            probs[n] = exp((scaled[i] - maxV).toDouble())
            sum += probs[n]
        }
        var r = rng.nextDouble() * sum
        for ((n, i) in idx.withIndex()) {
            r -= probs[n]
            if (r <= 0) return i
        }
        return idx.last()
    }

    /**
     * Generate a bot reply given tokenized conversation history
     * (already containing the trailing <bot> token). Emits words as they are
     * produced via [onToken]; returns the generated token ids.
     */
    fun generate(
        historyIds: List<Int>,
        maxNew: Int = 68,
        temperature: Float = 0.8f,
        topK: Int = 40,
        rng: Random = Random(System.nanoTime()),
        onToken: ((String) -> Unit)? = null
    ): List<Int> {
        reset()
        // keep only what fits: leave room for the reply
        val room = blockSize - maxNew
        val prompt = if (historyIds.size > room) historyIds.takeLast(room) else historyIds
        var logits = prefill(prompt)
        val out = ArrayList<Int>()
        for (n in 0 until maxNew) {
            val id = sample(logits, temperature, topK, rng)
            if (vocab[id] == "<end>") break
            // if the model drifts into a new fake user turn, stop
            if (vocab[id] == "<user>" || vocab[id] == "<bot>") break
            out.add(id)
            onToken?.invoke(vocab[id])
            if (curPos >= blockSize) break
            logits = step(id)
        }
        return out
    }

    companion object {
        /** perplexity helper for tests */
        fun logSoftmaxAt(logits: FloatArray, target: Int): Float {
            var maxV = Float.NEGATIVE_INFINITY
            for (v in logits) if (v > maxV) maxV = v
            var sum = 0.0
            for (v in logits) sum += exp((v - maxV).toDouble())
            return (logits[target] - maxV - ln(sum)).toFloat()
        }
    }
}
