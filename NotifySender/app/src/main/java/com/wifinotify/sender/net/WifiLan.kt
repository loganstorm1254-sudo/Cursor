package com.wifinotify.sender.net

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.Build
import java.net.DatagramSocket
import java.net.Inet4Address
import java.net.InetAddress
import java.net.NetworkInterface
import java.net.Socket

object WifiLan {

    fun wifiNetwork(context: Context): Network? {
        val cm = context.applicationContext
            .getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            ?: return null
        return cm.allNetworks.firstOrNull { network ->
            val caps = cm.getNetworkCapabilities(network) ?: return@firstOrNull false
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) &&
                caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .let { /* Wi‑Fi without internet still OK for LAN */ true } &&
                !caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)
        } ?: cm.allNetworks.firstOrNull { network ->
            val caps = cm.getNetworkCapabilities(network) ?: return@firstOrNull false
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
        }
    }

    fun bindSocket(context: Context, socket: Socket): Boolean {
        return try {
            val network = wifiNetwork(context) ?: return false
            network.bindSocket(socket)
            true
        } catch (_: Exception) {
            false
        }
    }

    fun bindSocket(context: Context, socket: DatagramSocket): Boolean {
        return try {
            val network = wifiNetwork(context) ?: return false
            network.bindSocket(socket)
            true
        } catch (_: Exception) {
            false
        }
    }

    /** Prefer routing this process over Wi‑Fi while LAN calls run. */
    fun bindProcessToWifi(context: Context): ConnectivityManager? {
        return try {
            val cm = context.applicationContext
                .getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            val network = wifiNetwork(context) ?: return null
            cm.bindProcessToNetwork(network)
            cm
        } catch (_: Exception) {
            null
        }
    }

    fun clearProcessBind(cm: ConnectivityManager?) {
        try {
            cm?.bindProcessToNetwork(null)
        } catch (_: Exception) {
        }
    }

    fun wifiIpv4Addresses(): List<String> {
        val result = mutableListOf<String>()
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces() ?: return result
            for (iface in interfaces) {
                if (!iface.isUp || iface.isLoopback) continue
                val name = iface.name.lowercase()
                // Skip cellular-looking interfaces when possible
                if (name.startsWith("rmnet") || name.startsWith("ccmni") ||
                    name.contains("dummy")
                ) continue
                for (addr in iface.inetAddresses) {
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        result += addr.hostAddress ?: continue
                    }
                }
            }
        } catch (_: Exception) {
        }
        return result
    }

    fun subnetHosts(localIp: String): List<String> {
        val parts = localIp.split(".")
        if (parts.size != 4) return emptyList()
        val prefix = "${parts[0]}.${parts[1]}.${parts[2]}."
        val self = parts[3].toIntOrNull() ?: return emptyList()
        return (1..254).filter { it != self }.map { prefix + it }
    }

    fun friendlyConnectError(raw: String?, host: String): String {
        val msg = raw.orEmpty()
        return when {
            msg.contains("EHOSTUNREACH", ignoreCase = true) ||
                msg.contains("No route to host", ignoreCase = true) ->
                "Can't reach $host on Wi‑Fi (no route).\n\n" +
                    "Try ALL of these:\n" +
                    "1. Turn OFF mobile data on BOTH phones\n" +
                    "2. On the receiver: Start is on, app stays open\n" +
                    "3. Turn off VPN on both phones\n" +
                    "4. If still failing: enable Mobile Hotspot on one phone and join it from the other — many routers block phone-to-phone traffic"

            msg.contains("ECONNREFUSED", ignoreCase = true) ||
                msg.contains("Connection refused", ignoreCase = true) ->
                "Reached $host but nothing is listening on port 9877.\n" +
                    "Open Notify Receiver on that phone and tap Start."

            msg.contains("ETIMEDOUT", ignoreCase = true) ||
                msg.contains("timed out", ignoreCase = true) ->
                "Timed out reaching $host.\n" +
                    "Turn OFF mobile data, confirm the IP, and keep Receiver listening. " +
                    "Or use one phone's hotspot."

            else -> "Send failed: ${raw ?: "unknown error"}"
        }
    }

    fun sanitizeIp(raw: String): String =
        raw.trim()
            .removePrefix("http://")
            .removePrefix("https://")
            .substringBefore("/")
            .substringBefore(":")
            .trim()
            .filter { !it.isWhitespace() }
}
