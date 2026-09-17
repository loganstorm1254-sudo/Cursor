package com.shortsblocker.app.ui

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.shortsblocker.app.R

/**
 * Brief interstitial shown when a short feed is interrupted.
 * Auto-finishes so the user lands back at the launcher / previous app.
 */
class BlockOverlayActivity : AppCompatActivity() {

    private val handler = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_block_overlay)

        val reason = intent.getStringExtra(EXTRA_REASON).orEmpty()
        val label = when {
            reason.contains("youtube") -> "YouTube Shorts blocked"
            reason.contains("tiktok") -> "TikTok short feed blocked"
            else -> "Short feed blocked"
        }
        findViewById<TextView>(R.id.blockTitle).text = label
        findViewById<TextView>(R.id.blockBody).text =
            "Take a breath. Full videos, messages, and profile still work — just not the endless short scroll."

        findViewById<TextView>(R.id.blockOk).setOnClickListener { goHome() }

        handler.postDelayed({ goHome() }, 1800)
    }

    private fun goHome() {
        val home = Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_HOME)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        startActivity(home)
        finish()
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    companion object {
        const val EXTRA_REASON = "reason"
    }
}
