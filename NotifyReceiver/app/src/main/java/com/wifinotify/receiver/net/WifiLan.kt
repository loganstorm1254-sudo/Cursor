package com.wifinotify.receiver.net

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import java.net.DatagramSocket
import java.net.Inet4Address
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.ServerSocket
import java.net.Socket

object WifiLan {

    fun wifiNetwork(context: Context): Network? {
        val cm = context.applicationContext
            .getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            ?: return null
        return cm.allNetworks.firstOrNull { network ->
            val caps = cm.getNetworkCapabilities(network) ?: return@firstOrNull false
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
        }
    }

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

    fun bindSocket(context: Context, socket: DatagramSocket): Boolean {
        return try {
            val network = wifiNetwork(context) ?: return false
            network.bindSocket(socket)
            true
        } catch (_: Exception) {
            false
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

    fun wifiIpv4(): String? {
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces() ?: return null
            for (iface in interfaces) {
                if (!iface.isUp || iface.isLoopback) continue
                val name = iface.name.lowercase()
                if (name.startsWith("rmnet") || name.startsWith("ccmni") || name.contains("dummy")) {
                    continue
                }
                for (addr in iface.inetAddresses) {
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        val ip = addr.hostAddress ?: continue
                        // Prefer private LAN ranges
                        if (ip.startsWith("192.168.") || ip.startsWith("10.") ||
                            ip.startsWith("172.")
                        ) {
                            return ip
                        }
                    }
                }
            }
        } catch (_: Exception) {
        }
        return localIpv4Addresses().firstOrNull()
    }

    fun openServerSocket(port: Int, preferredIp: String?): ServerSocket {
        if (!preferredIp.isNullOrBlank()) {
            try {
                val server = ServerSocket()
                server.reuseAddress = true
                server.bind(InetSocketAddress(preferredIp, port))
                return server
            } catch (_: Exception) {
                // fall through
            }
        }
        val server = ServerSocket()
        server.reuseAddress = true
        server.bind(InetSocketAddress(port))
        return server
    }
}
