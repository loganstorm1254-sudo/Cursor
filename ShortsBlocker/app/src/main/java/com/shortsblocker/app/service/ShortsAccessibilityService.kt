package com.shortsblocker.app.service

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.shortsblocker.app.Prefs
import com.shortsblocker.app.ui.BlockOverlayActivity

/**
 * Watches YouTube + TikTok and only interrupts short-form feeds.
 * TikTok: covers just the video area (top tabs + bottom nav stay usable).
 * YouTube Shorts: backs out of the Shorts player (regular watch stays open).
 */
class ShortsAccessibilityService : AccessibilityService() {

    private val handler = Handler(Looper.getMainLooper())
    private var lastActionAt = 0L
    private var lastPackage: String? = null
    private var feedCover: FeedCoverOverlay? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        feedCover = FeedCoverOverlay(this)
        // Listen broadly so we can hide the TikTok cover when the user leaves the app.
        startForegroundGuard()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return

        if (!Prefs.isEnabled(this)) {
            feedCover?.hide()
            return
        }

        val pkg = event.packageName?.toString() ?: return
        lastPackage = pkg

        when {
            isYoutube(pkg) && Prefs.blockYoutube(this) -> {
                feedCover?.hide()
                maybeBlockYoutube()
            }
            isTiktok(pkg) && Prefs.blockTiktok(this) -> maybeBlockTiktok()
            else -> feedCover?.hide()
        }
    }

    override fun onInterrupt() {
        feedCover?.hide()
    }

    override fun onDestroy() {
        feedCover?.hide()
        feedCover = null
        super.onDestroy()
    }

    private fun maybeBlockYoutube() {
        val root = rootInActiveWindow ?: return
        try {
            if (looksLikeYoutubeShorts(root)) {
                bounceOut(reason = "youtube_shorts")
            }
        } finally {
            root.recycle()
        }
    }

    private fun maybeBlockTiktok() {
        val root = rootInActiveWindow ?: return
        try {
            // Only clear the cover when the user clearly leaves the short feed
            // (Inbox / Profile / Friends / etc.). Do NOT hide on flaky "not feed"
            // readings — those happen when tapping and were dismissing the cover.
            if (isTiktokAllowedSurface(root)) {
                feedCover?.hide()
                return
            }
            if (looksLikeTiktokShortFeed(root) || feedCover?.isShowing() == true) {
                // Show once; if already up, show() is a no-op and it stays put.
                feedCover?.show("Short feed blocked")
            }
        } finally {
            root.recycle()
        }
    }

    private fun bounceOut(reason: String) {
        val now = SystemClock.elapsedRealtime()
        if (now - lastActionAt < COOLDOWN_MS) return
        lastActionAt = now

        Prefs.incrementBlocks(this)

        // YouTube Shorts: back out of the short player; if still trapped, leave to our screen.
        performGlobalAction(GLOBAL_ACTION_BACK)
        handler.postDelayed({
            val pkg = lastPackage ?: return@postDelayed
            if (isYoutube(pkg) && Prefs.blockYoutube(this)) {
                val still = rootInActiveWindow
                try {
                    if (still != null && looksLikeYoutubeShorts(still)) {
                        val intent = Intent(this, BlockOverlayActivity::class.java).apply {
                            addFlags(
                                Intent.FLAG_ACTIVITY_NEW_TASK or
                                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                                    Intent.FLAG_ACTIVITY_SINGLE_TOP
                            )
                            putExtra(BlockOverlayActivity.EXTRA_REASON, reason)
                        }
                        startActivity(intent)
                    }
                } finally {
                    still?.recycle()
                }
            }
        }, 350)
    }

    private fun looksLikeYoutubeShorts(root: AccessibilityNodeInfo): Boolean {
        val idHits = listOf(
            "com.google.android.youtube:id/reel_recycler",
            "com.google.android.youtube:id/reel_player_page_container",
            "com.google.android.youtube:id/reel_player_underlay",
            "com.google.android.youtube:id/shorts_player",
            "com.google.android.youtube:id/reel_watch_fragment_root",
            "app.revanced.android.youtube:id/reel_recycler",
            "app.revanced.android.youtube:id/reel_player_page_container"
        )
        if (idHits.any { root.findAccessibilityNodeInfosByViewId(it).isNotEmpty() }) {
            return true
        }

        if (hasTextOrDesc(root, "shorts", exactWord = true)) {
            val chrome = hasTextOrDesc(root, "subscribe") ||
                hasTextOrDesc(root, "like this video") ||
                hasTextOrDesc(root, "dislike this video") ||
                (hasTextOrDesc(root, "share") && hasTextOrDesc(root, "remix"))
            if (chrome) return true
        }

        if (hasSelectedTab(root, "Shorts")) return true

        return false
    }

    private fun looksLikeTiktokShortFeed(root: AccessibilityNodeInfo): Boolean {
        val feedIds = listOf(
            "com.zhiliaoapp.musically:id/viewpager",
            "com.zhiliaoapp.musically:id/feed_video",
            "com.ss.android.ugc.trill:id/viewpager",
            "com.ss.android.ugc.trill:id/feed_video"
        )
        val feedHit = feedIds.any { root.findAccessibilityNodeInfosByViewId(it).isNotEmpty() }

        val forYouSelected = hasSelectedTab(root, "For You") ||
            hasSelectedTab(root, "Home") ||
            hasSelectedTab(root, "Following")

        if (forYouSelected) return true
        if (feedHit && !isTiktokAllowedSurface(root)) return true

        val shortChrome = hasTextOrDesc(root, "Like") &&
            hasTextOrDesc(root, "Comment") &&
            hasTextOrDesc(root, "Share") &&
            (hasTextOrDesc(root, "For You") || hasTextOrDesc(root, "Following"))
        return shortChrome
    }

    private fun isTiktokAllowedSurface(root: AccessibilityNodeInfo): Boolean {
        if (hasSelectedTab(root, "Inbox") ||
            hasSelectedTab(root, "Profile") ||
            hasSelectedTab(root, "Friends") ||
            hasSelectedTab(root, "Shop")
        ) {
            return true
        }

        val allowHints = listOf(
            "Messages", "Activity", "Notifications", "Settings", "Edit profile",
            "Add friends", "Search", "LIVE", "Go LIVE", "Create", "Drafts",
            "Balance", "Creator tools", "Privacy", "Security"
        )
        if (allowHints.any { hasTextOrDesc(root, it) } &&
            !hasSelectedTab(root, "For You") &&
            !hasSelectedTab(root, "Home")
        ) {
            return true
        }
        return false
    }

    private fun hasSelectedTab(root: AccessibilityNodeInfo, label: String): Boolean {
        val nodes = mutableListOf<AccessibilityNodeInfo>()
        collectByTextOrDesc(root, label, nodes)
        return nodes.any { it.isSelected || it.isChecked || it.isAccessibilityFocused }
    }

    private fun hasTextOrDesc(
        node: AccessibilityNodeInfo,
        needle: String,
        exactWord: Boolean = false
    ): Boolean {
        val n = needle.lowercase()
        val text = sequenceOf(node.text, node.contentDescription)
            .mapNotNull { it?.toString()?.lowercase() }
        val hit = text.any { t ->
            if (exactWord) Regex("""\b${Regex.escape(n)}\b""").containsMatchIn(t)
            else t.contains(n)
        }
        if (hit) return true
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            try {
                if (hasTextOrDesc(child, needle, exactWord)) return true
            } finally {
                child.recycle()
            }
        }
        return false
    }

    private fun collectByTextOrDesc(
        node: AccessibilityNodeInfo,
        needle: String,
        out: MutableList<AccessibilityNodeInfo>
    ) {
        val n = needle.lowercase()
        val text = node.text?.toString()?.lowercase().orEmpty()
        val desc = node.contentDescription?.toString()?.lowercase().orEmpty()
        if (text == n || desc == n || text.contains(n) || desc.contains(n)) {
            out.add(AccessibilityNodeInfo.obtain(node))
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            try {
                collectByTextOrDesc(child, needle, out)
            } finally {
                child.recycle()
            }
        }
    }

    private fun startForegroundGuard() {
        val intent = Intent(this, ShortsGuardService::class.java)
        try {
            startForegroundService(intent)
        } catch (_: Exception) {
            startService(intent)
        }
    }

    companion object {
        private const val COOLDOWN_MS = 900L

        fun isYoutube(pkg: String) =
            pkg == "com.google.android.youtube" || pkg == "app.revanced.android.youtube"

        fun isTiktok(pkg: String) =
            pkg == "com.zhiliaoapp.musically" || pkg == "com.ss.android.ugc.trill"
    }
}
