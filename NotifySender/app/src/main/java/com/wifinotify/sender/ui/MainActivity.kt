package com.wifinotify.sender.ui

import android.os.Build
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.wifinotify.sender.R
import com.wifinotify.sender.databinding.ActivityMainBinding
import com.wifinotify.sender.net.DiscoveredReceiver
import com.wifinotify.sender.net.NotifyClient
import com.wifinotify.sender.net.WifiLan

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val receivers = mutableListOf<DiscoveredReceiver>()
    private var selected: DiscoveredReceiver? = null
    private lateinit var adapter: ReceiverAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        adapter = ReceiverAdapter(receivers) { item ->
            selected = item
            binding.selectedText.text = getString(R.string.selected_receiver, item.name, item.host)
            adapter.selectedHost = item.host
            adapter.notifyDataSetChanged()
        }

        val prefs = getSharedPreferences("sender_prefs", MODE_PRIVATE)
        binding.fromInput.setText(
            prefs.getString("from_name", null) ?: (Build.MODEL ?: "Sender")
        )

        binding.receiverList.layoutManager = LinearLayoutManager(this)
        binding.receiverList.adapter = adapter

        binding.scanButton.setOnClickListener { scan() }
        binding.useIpButton.setOnClickListener { useManualIp() }
        binding.testButton.setOnClickListener { testConnection() }
        binding.sendButton.setOnClickListener { send() }
    }

    private fun useManualIp() {
        val ip = WifiLan.sanitizeIp(binding.manualIpInput.text?.toString().orEmpty())
        if (!IPV4.matches(ip)) {
            Toast.makeText(this, R.string.invalid_ip, Toast.LENGTH_SHORT).show()
            return
        }
        binding.manualIpInput.setText(ip)
        val item = DiscoveredReceiver(name = "Manual", host = ip)
        selected = item
        adapter.selectedHost = ip
        if (receivers.none { it.host == ip }) {
            receivers += item
        }
        adapter.notifyDataSetChanged()
        binding.selectedText.text = getString(R.string.selected_receiver, item.name, item.host)
    }

    private fun testConnection() {
        val target = selected
        if (target == null) {
            Toast.makeText(this, R.string.pick_receiver_first, Toast.LENGTH_SHORT).show()
            return
        }
        binding.testButton.isEnabled = false
        binding.statusText.text = getString(R.string.testing)
        NotifyClient.testReachable(this, target.host) { ok, message ->
            runOnUiThread {
                binding.testButton.isEnabled = true
                binding.statusText.text = message
                if (ok) {
                    Toast.makeText(this, R.string.test_ok, Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun scan() {
        binding.scanButton.isEnabled = false
        binding.statusText.text = getString(R.string.scanning)
        receivers.clear()
        selected = null
        adapter.selectedHost = null
        adapter.notifyDataSetChanged()
        binding.selectedText.text = getString(R.string.no_receiver_selected)

        NotifyClient.discover(
            context = this,
            onFound = { item ->
                runOnUiThread {
                    if (receivers.none { it.host == item.host }) {
                        receivers += item
                        adapter.notifyItemInserted(receivers.lastIndex)
                        if (selected == null) {
                            selected = item
                            adapter.selectedHost = item.host
                            binding.selectedText.text =
                                getString(R.string.selected_receiver, item.name, item.host)
                            adapter.notifyDataSetChanged()
                        }
                    }
                }
            },
            onDone = { list ->
                runOnUiThread {
                    binding.scanButton.isEnabled = true
                    binding.statusText.text = if (list.isEmpty()) {
                        getString(R.string.scan_none)
                    } else {
                        getString(R.string.scan_found, list.size)
                    }
                }
            },
            onError = { err ->
                runOnUiThread {
                    binding.scanButton.isEnabled = true
                    binding.statusText.text = err
                }
            }
        )
    }

    private fun send() {
        val target = selected
        if (target == null) {
            Toast.makeText(this, R.string.pick_receiver_first, Toast.LENGTH_SHORT).show()
            return
        }
        val title = binding.titleInput.text?.toString()?.trim().orEmpty()
        val message = binding.messageInput.text?.toString()?.trim().orEmpty()
        val from = binding.fromInput.text?.toString()?.trim().orEmpty()
            .ifBlank { Build.MODEL ?: "Sender" }

        if (title.isEmpty() || message.isEmpty()) {
            Toast.makeText(this, R.string.fill_title_message, Toast.LENGTH_SHORT).show()
            return
        }

        getSharedPreferences("sender_prefs", MODE_PRIVATE)
            .edit()
            .putString("from_name", from)
            .apply()

        binding.sendButton.isEnabled = false
        binding.statusText.text = getString(R.string.sending)

        NotifyClient.send(
            context = this,
            host = target.host,
            title = title,
            message = message,
            from = from,
            onSuccess = {
                runOnUiThread {
                    binding.sendButton.isEnabled = true
                    binding.statusText.text = getString(R.string.sent_ok, target.name)
                    Toast.makeText(this, R.string.sent_toast, Toast.LENGTH_SHORT).show()
                }
            },
            onError = { err ->
                runOnUiThread {
                    binding.sendButton.isEnabled = true
                    binding.statusText.text = err
                }
            }
        )
    }
}

private class ReceiverAdapter(
    private val items: List<DiscoveredReceiver>,
    private val onClick: (DiscoveredReceiver) -> Unit
) : RecyclerView.Adapter<ReceiverAdapter.Holder>() {

    var selectedHost: String? = null

    class Holder(view: View) : RecyclerView.ViewHolder(view) {
        val name: TextView = view.findViewById(R.id.itemName)
        val host: TextView = view.findViewById(R.id.itemHost)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Holder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_receiver, parent, false)
        return Holder(view)
    }

    override fun onBindViewHolder(holder: Holder, position: Int) {
        val item = items[position]
        holder.name.text = item.name
        holder.host.text = item.host
        holder.itemView.isSelected = item.host == selectedHost
        holder.itemView.setOnClickListener { onClick(item) }
    }

    override fun getItemCount(): Int = items.size
}

private val IPV4 = Regex(
    """^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$"""
)
