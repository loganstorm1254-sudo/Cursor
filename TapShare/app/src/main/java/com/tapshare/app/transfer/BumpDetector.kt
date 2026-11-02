package com.tapshare.app.transfer

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import kotlin.math.sqrt

/**
 * Detects a firm phone-to-phone tap (tops knocking) via accelerometer spike.
 */
class BumpDetector(
    context: Context,
    private val onBump: () -> Unit
) : SensorEventListener {

    private val sensorManager = context.getSystemService(SensorManager::class.java)
    private val accelerometer = sensorManager?.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private var lastBumpAt = 0L
    private var lastMagnitude = 0f

    fun start() {
        val sensor = accelerometer ?: return
        sensorManager?.registerListener(this, sensor, SensorManager.SENSOR_DELAY_GAME)
    }

    fun stop() {
        try {
            sensorManager?.unregisterListener(this)
        } catch (_: Exception) {
        }
    }

    override fun onSensorChanged(event: SensorEvent?) {
        if (event?.sensor?.type != Sensor.TYPE_ACCELEROMETER) return
        val x = event.values[0]
        val y = event.values[1]
        val z = event.values[2]
        val magnitude = sqrt(x * x + y * y + z * z)
        val delta = kotlin.math.abs(magnitude - lastMagnitude)
        lastMagnitude = magnitude
        // Quiet gravity ~9.8; a knock spikes hard. Threshold tuned for phone tops tapping.
        if (delta < 14f) return
        val now = System.currentTimeMillis()
        if (now - lastBumpAt < 1600L) return
        lastBumpAt = now
        onBump()
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
}
