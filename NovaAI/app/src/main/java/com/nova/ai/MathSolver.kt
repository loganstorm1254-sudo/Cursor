package com.nova.ai

/**
 * Deterministic arithmetic for the questions Nova's tiny network cannot
 * reliably invent. Handles plus/minus/times/divided, +, -, *, /, x, double,
 * half, and squared. Returns a spoken answer string, or null if the text
 * is not a math question we can solve.
 */
object MathSolver {

    private val WORD = mapOf(
        "zero" to 0, "one" to 1, "two" to 2, "three" to 3, "four" to 4,
        "five" to 5, "six" to 6, "seven" to 7, "eight" to 8, "nine" to 9,
        "ten" to 10, "eleven" to 11, "twelve" to 12, "thirteen" to 13,
        "fourteen" to 14, "fifteen" to 15, "sixteen" to 16, "seventeen" to 17,
        "eighteen" to 18, "nineteen" to 19, "twenty" to 20,
        "thirty" to 30, "forty" to 40, "fifty" to 50, "sixty" to 60,
        "seventy" to 70, "eighty" to 80, "ninety" to 90, "hundred" to 100)

    private val TO_WORD = WORD.entries
        .filter { it.value <= 20 }
        .associate { it.value to it.key }

    private val PREFIX = Regex(
        "^(?:what is|whats|what's|how much is|calculate|solve|compute)\\s+")
    private val BINARY = Regex(
        """^(-?\d+)\s*(plus|\+|minus|-|times|x|\*|multiplied by|divided by|/|÷)\s*(-?\d+)\s*$""")
    private val DOUBLE = Regex("""^(?:double|twice)\s+(-?\d+)\s*$""")
    private val HALF = Regex("""^(?:half of|half)\s+(-?\d+)\s*$""")
    private val SQUARED = Regex("""^(-?\d+)\s+squared\s*$""")

    fun trySolve(message: String): String? {
        var t = message.trim().lowercase().trimEnd('?', '!', '.', ' ')
        if (t.isEmpty()) return null
        t = PREFIX.replaceFirst(t, "")
        t = wordsToDigits(t)

        DOUBLE.find(t)?.let {
            val n = it.groupValues[1].toLong()
            return "double $n is ${say(n * 2)}."
        }
        HALF.find(t)?.let {
            val n = it.groupValues[1].toLong()
            if (n % 2L != 0L) return "half of $n is ${say(n / 2)} (with a remainder)."
            return "half of $n is ${say(n / 2)}."
        }
        SQUARED.find(t)?.let {
            val n = it.groupValues[1].toLong()
            return "$n squared is ${say(n * n)}."
        }
        BINARY.find(t)?.let {
            val a = it.groupValues[1].toLong()
            val op = it.groupValues[2]
            val b = it.groupValues[3].toLong()
            val (name, r) = when (op) {
                "plus", "+" -> "plus" to a + b
                "minus", "-" -> "minus" to a - b
                "times", "x", "*", "multiplied by" -> "times" to a * b
                "divided by", "/", "÷" -> {
                    if (b == 0L) return "you can not divide by zero."
                    if (a % b != 0L) return "$a divided by $b is ${a.toDouble() / b}."
                    "divided by" to a / b
                }
                else -> return null
            }
            return "$a $name $b is ${say(r)}."
        }
        return null
    }

    private fun say(n: Long): String =
        if (n in 0..20) TO_WORD[n.toInt()] ?: n.toString() else n.toString()

    /** Replace standalone number-words with digits so the regexes stay simple. */
    private fun wordsToDigits(s: String): String {
        val parts = s.split(Regex("\\s+")).toMutableList()
        var i = 0
        while (i < parts.size) {
            val w = parts[i]
            if (w in WORD) {
                var total = 0
                var current = 0
                var j = i
                while (j < parts.size && parts[j] in WORD) {
                    val v = WORD[parts[j]]!!
                    if (v == 100) {
                        current = (if (current == 0) 1 else current) * 100
                    } else {
                        current += v
                    }
                    total = current
                    j++
                }
                parts[i] = total.toString()
                for (k in j - 1 downTo i + 1) parts.removeAt(k)
            }
            i++
        }
        return parts.joinToString(" ")
    }
}
