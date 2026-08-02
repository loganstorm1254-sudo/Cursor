package com.nova.ai

import android.content.Context
import android.os.Bundle
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {

    private lateinit var lockView: View
    private lateinit var chatView: View
    private lateinit var keyInput: EditText
    private lateinit var unlockBtn: Button
    private lateinit var lockError: TextView
    private lateinit var lockProgress: ProgressBar
    private lateinit var messages: LinearLayout
    private lateinit var scroll: ScrollView
    private lateinit var msgInput: EditText
    private lateinit var sendBtn: ImageButton

    private var engine: NovaEngine? = null
    private val historyIds = ArrayList<Int>()
    @Volatile private var generating = false

    private val prefs by lazy { getSharedPreferences("nova", Context.MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        lockView = findViewById(R.id.lockView)
        chatView = findViewById(R.id.chatView)
        keyInput = findViewById(R.id.keyInput)
        unlockBtn = findViewById(R.id.unlockBtn)
        lockError = findViewById(R.id.lockError)
        lockProgress = findViewById(R.id.lockProgress)
        messages = findViewById(R.id.messages)
        scroll = findViewById(R.id.scroll)
        msgInput = findViewById(R.id.msgInput)
        sendBtn = findViewById(R.id.sendBtn)

        unlockBtn.setOnClickListener { tryUnlock(keyInput.text.toString()) }
        sendBtn.setOnClickListener { onSend() }
        findViewById<ImageButton>(R.id.lockBtn).setOnClickListener { confirmLock() }
        findViewById<ImageButton>(R.id.clearBtn).setOnClickListener { clearChat() }

        val saved = prefs.getString("master_key", null)
        if (saved != null) {
            tryUnlock(saved, silent = true)
        }
    }

    private fun tryUnlock(key: String, silent: Boolean = false) {
        if (key.isBlank()) {
            lockError.text = getString(R.string.err_empty_key)
            lockError.visibility = View.VISIBLE
            return
        }
        lockError.visibility = View.GONE
        lockProgress.visibility = View.VISIBLE
        unlockBtn.isEnabled = false
        thread {
            try {
                val enc = assets.open("nova_model.enc").readBytes()
                val weights = ModelCrypto.decrypt(key, enc)
                val config = assets.open("nova_config.txt")
                    .readBytes().toString(Charsets.UTF_8)
                val eng = NovaEngine(config, weights)
                runOnUiThread {
                    engine = eng
                    prefs.edit().putString("master_key", key.trim()).apply()
                    lockProgress.visibility = View.GONE
                    unlockBtn.isEnabled = true
                    showChat()
                }
            } catch (e: ModelCrypto.WrongKeyException) {
                runOnUiThread {
                    lockProgress.visibility = View.GONE
                    unlockBtn.isEnabled = true
                    if (!silent) {
                        lockError.text = getString(R.string.err_wrong_key)
                        lockError.visibility = View.VISIBLE
                    } else {
                        prefs.edit().remove("master_key").apply()
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    lockProgress.visibility = View.GONE
                    unlockBtn.isEnabled = true
                    lockError.text = getString(R.string.err_load, e.message ?: "?")
                    lockError.visibility = View.VISIBLE
                }
            }
        }
    }

    private fun showChat() {
        lockView.visibility = View.GONE
        chatView.visibility = View.VISIBLE
        if (messages.childCount == 0) {
            addBubble(getString(R.string.welcome), fromUser = false)
        }
    }

    private fun confirmLock() {
        AlertDialog.Builder(this)
            .setTitle(R.string.lock_title)
            .setMessage(R.string.lock_msg)
            .setPositiveButton(R.string.lock_yes) { _, _ ->
                prefs.edit().remove("master_key").apply()
                engine = null
                historyIds.clear()
                messages.removeAllViews()
                keyInput.setText("")
                chatView.visibility = View.GONE
                lockView.visibility = View.VISIBLE
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun clearChat() {
        historyIds.clear()
        messages.removeAllViews()
        addBubble(getString(R.string.welcome), fromUser = false)
    }

    private fun onSend() {
        val eng = engine ?: return
        if (generating) return
        val text = msgInput.text.toString().trim()
        if (text.isEmpty()) return
        msgInput.setText("")
        hideKeyboard()
        addBubble(text, fromUser = true)

        historyIds.add(eng.tokenId("<user>"))
        historyIds.addAll(eng.encode(text))
        historyIds.add(eng.tokenId("<bot>"))

        val bubble = addBubble("…", fromUser = false)
        generating = true
        sendBtn.isEnabled = false
        thread {
            val words = ArrayList<String>()
            val outIds = eng.generate(ArrayList(historyIds), onToken = { word ->
                words.add(word)
                val ids = words.map { eng.tokenId(it) }
                runOnUiThread {
                    bubble.text = eng.decode(ids)
                    scrollDown()
                }
            })
            runOnUiThread {
                historyIds.addAll(outIds)
                historyIds.add(eng.tokenId("<end>"))
                // keep history bounded (context window is small anyway)
                while (historyIds.size > 512) historyIds.removeAt(0)
                if (outIds.isEmpty()) bubble.text = getString(R.string.fallback_reply)
                else bubble.text = eng.decode(outIds)
                generating = false
                sendBtn.isEnabled = true
                scrollDown()
            }
        }
    }

    private fun addBubble(text: String, fromUser: Boolean): TextView {
        val tv = TextView(this)
        tv.text = text
        tv.textSize = 16f
        tv.setTextColor(ContextCompat.getColor(
            this, if (fromUser) R.color.bubble_user_text else R.color.bubble_bot_text))
        tv.background = ContextCompat.getDrawable(
            this, if (fromUser) R.drawable.bubble_user else R.drawable.bubble_bot)
        val pad = (12 * resources.displayMetrics.density).toInt()
        tv.setPadding(pad, pad * 3 / 4, pad, pad * 3 / 4)
        val lp = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        val m = (8 * resources.displayMetrics.density).toInt()
        lp.setMargins(m, m / 2, m, m / 2)
        lp.gravity = if (fromUser) android.view.Gravity.END else android.view.Gravity.START
        tv.layoutParams = lp
        tv.maxWidth = (resources.displayMetrics.widthPixels * 0.78).toInt()
        messages.addView(tv)
        scrollDown()
        return tv
    }

    private fun scrollDown() {
        scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
    }

    private fun hideKeyboard() {
        val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
        imm.hideSoftInputFromWindow(msgInput.windowToken, 0)
    }
}
