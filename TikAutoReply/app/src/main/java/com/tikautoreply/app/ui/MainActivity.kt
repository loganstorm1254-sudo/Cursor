package com.tikautoreply.app.ui

import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.text.TextUtils
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.android.material.button.MaterialButton
import com.tikautoreply.app.R
import com.tikautoreply.app.data.KeywordRule
import com.tikautoreply.app.data.SettingsStore
import com.tikautoreply.app.databinding.ActivityMainBinding
import com.tikautoreply.app.service.TikTokReplyService
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var store: SettingsStore
    private val timeFmt = SimpleDateFormat("HH:mm", Locale.getDefault())

    private val eventReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            renderLog()
            refreshStatus()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        store = SettingsStore(this)

        bindFromStore()
        setupClicks()
        renderRules()
        renderLog()
    }

    override fun onResume() {
        super.onResume()
        refreshStatus()
        renderLog()
        ContextCompat.registerReceiver(
            this,
            eventReceiver,
            IntentFilter(SettingsStore.ACTION_EVENT_LOGGED),
            ContextCompat.RECEIVER_NOT_EXPORTED
        )
    }

    override fun onPause() {
        super.onPause()
        runCatching { unregisterReceiver(eventReceiver) }
    }

    private fun setupClicks() {
        binding.saveLinkButton.setOnClickListener {
            val name = binding.usernameInput.text?.toString()?.trim().orEmpty().removePrefix("@")
            if (name.isBlank()) {
                binding.usernameLayout.error = getString(R.string.need_username)
                return@setOnClickListener
            }
            binding.usernameLayout.error = null
            store.username = name
            Toast.makeText(this, getString(R.string.linked_as, name), Toast.LENGTH_SHORT).show()
            refreshStatus()
            if (!isNotificationAccessEnabled()) {
                openNotificationAccess()
            }
        }

        binding.openTikTokButton.setOnClickListener {
            val name = store.username.ifBlank {
                binding.usernameInput.text?.toString()?.trim().orEmpty().removePrefix("@")
            }
            val uri = if (name.isBlank()) {
                Uri.parse("https://www.tiktok.com/")
            } else {
                Uri.parse("https://www.tiktok.com/@$name")
            }
            val view = Intent(Intent.ACTION_VIEW, uri)
            val launch = packageManager.getLaunchIntentForPackage("com.zhiliaoapp.musically")
                ?: packageManager.getLaunchIntentForPackage("com.ss.android.ugc.trill")
            try {
                startActivity(view)
            } catch (_: Exception) {
                if (launch != null) startActivity(launch)
                else Toast.makeText(this, "TikTok app / browser not available", Toast.LENGTH_SHORT).show()
            }
        }

        binding.grantAccessButton.setOnClickListener { openNotificationAccess() }

        binding.enabledSwitch.setOnCheckedChangeListener { _, checked ->
            store.enabled = checked
            refreshStatus()
            broadcastSettings()
        }

        binding.saveSettingsButton.setOnClickListener {
            val reply = binding.defaultReplyInput.text?.toString()?.trim().orEmpty()
            if (reply.isBlank()) {
                binding.defaultReplyLayout.error = getString(R.string.need_reply)
                return@setOnClickListener
            }
            binding.defaultReplyLayout.error = null
            store.defaultReply = reply
            store.cooldownSeconds = binding.cooldownInput.text?.toString()?.toIntOrNull() ?: 60
            store.enabled = binding.enabledSwitch.isChecked
            Toast.makeText(this, "Reply settings saved", Toast.LENGTH_SHORT).show()
            broadcastSettings()
            refreshStatus()
        }

        binding.addRuleButton.setOnClickListener {
            val keyword = binding.keywordInput.text?.toString()?.trim().orEmpty()
            val reply = binding.keywordReplyInput.text?.toString()?.trim().orEmpty()
            if (keyword.isBlank() || reply.isBlank()) {
                Toast.makeText(this, getString(R.string.need_keyword), Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            store.addRule(keyword, reply)
            binding.keywordInput.setText("")
            binding.keywordReplyInput.setText("")
            renderRules()
            broadcastSettings()
        }

        binding.clearLogButton.setOnClickListener {
            store.clearEvents()
            renderLog()
        }
    }

    private fun bindFromStore() {
        binding.usernameInput.setText(store.username)
        binding.enabledSwitch.isChecked = store.enabled
        binding.defaultReplyInput.setText(store.defaultReply)
        binding.cooldownInput.setText(store.cooldownSeconds.toString())
    }

    private fun refreshStatus() {
        val access = isNotificationAccessEnabled()
        binding.accessStatus.text = getString(if (access) R.string.access_on else R.string.access_off)
        binding.accessStatus.setTextColor(
            ContextCompat.getColor(this, if (access) R.color.ok else R.color.warn)
        )

        val linked = store.username.isNotBlank()
        val label = when {
            !linked -> getString(R.string.not_linked)
            !access -> getString(R.string.access_off)
            store.enabled -> getString(R.string.running)
            else -> getString(R.string.paused)
        }
        binding.statusPill.text = if (linked) {
            "${getString(R.string.linked_as, store.username)} · $label"
        } else {
            label
        }
        binding.statusPill.setTextColor(
            ContextCompat.getColor(
                this,
                when {
                    linked && access && store.enabled -> R.color.ok
                    linked && access -> R.color.warn
                    else -> R.color.coral
                }
            )
        )
    }

    private fun renderRules() {
        val container = binding.rulesContainer
        container.removeAllViews()
        val rules = store.getRules()
        if (rules.isEmpty()) {
            container.addView(simpleNote("No keyword rules yet — default reply is used for everything."))
            return
        }
        rules.forEach { rule -> container.addView(ruleRow(rule)) }
    }

    private fun ruleRow(rule: KeywordRule): LinearLayout {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, 12, 0, 4)
        }
        val label = TextView(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            typeface = resources.getFont(R.font.outfit_medium)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.ink))
            textSize = 13f
            text = "“${rule.keyword}” → ${rule.reply}"
        }
        val remove = MaterialButton(this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
            text = "Remove"
            isAllCaps = false
            setOnClickListener {
                store.removeRule(rule.id)
                renderRules()
                broadcastSettings()
            }
        }
        row.addView(label)
        row.addView(remove)
        return row
    }

    private fun simpleNote(msg: String): TextView =
        TextView(this).apply {
            setPadding(0, 8, 0, 0)
            typeface = resources.getFont(R.font.outfit_regular)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.ink_soft))
            textSize = 13f
            text = msg
        }

    private fun renderLog() {
        val events = store.getEvents()
        if (events.isEmpty()) {
            binding.logText.text = getString(R.string.empty_log)
            return
        }
        binding.logText.text = events.joinToString("\n\n") { e ->
            val whenStr = timeFmt.format(Date(e.timeMs))
            val replyPart = e.reply?.let { "\n↳ $it" }.orEmpty()
            "[$whenStr] ${e.sender}: ${e.message.ifBlank { "(no text)" }}$replyPart\n(${e.status})"
        }
    }

    private fun openNotificationAccess() {
        startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        Toast.makeText(this, "Turn on TikAuto in Notification access", Toast.LENGTH_LONG).show()
    }

    private fun isNotificationAccessEnabled(): Boolean {
        val flat = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")
        if (flat.isNullOrEmpty()) return false
        val cn = ComponentName(this, TikTokReplyService::class.java)
        val splitter = TextUtils.SimpleStringSplitter(':')
        splitter.setString(flat)
        while (splitter.hasNext()) {
            val next = ComponentName.unflattenFromString(splitter.next())
            if (next != null && next == cn) return true
        }
        return false
    }

    private fun broadcastSettings() {
        sendBroadcast(Intent(SettingsStore.ACTION_SETTINGS_CHANGED).setPackage(packageName))
    }
}
