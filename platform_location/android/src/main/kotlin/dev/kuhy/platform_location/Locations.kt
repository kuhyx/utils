package dev.kuhy.platform_location

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.Build
import androidx.core.content.ContextCompat
import androidx.core.location.LocationCompat
import androidx.core.location.LocationManagerCompat

/** Permission, provider and fix helpers shared by the plugin and [FixStream]. */
internal object Locations {
    fun locationManager(ctx: Context): LocationManager =
        ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    fun locationEnabled(ctx: Context): Boolean =
        LocationManagerCompat.isLocationEnabled(locationManager(ctx))

    fun hasFine(ctx: Context): Boolean = ContextCompat.checkSelfPermission(
        ctx,
        Manifest.permission.ACCESS_FINE_LOCATION,
    ) == PackageManager.PERMISSION_GRANTED

    fun hasAny(ctx: Context): Boolean = hasFine(ctx) ||
        ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_COARSE_LOCATION) ==
        PackageManager.PERMISSION_GRANTED

    /**
     * Enabled providers, best first: GPS when fine location is granted, then
     * the platform fused provider (AOSP, Android 12+), network, and GPS for a
     * coarse-only app (Android 12+ coarsens it). Empty without permission.
     */
    fun candidates(ctx: Context, lm: LocationManager): List<String> {
        if (!hasAny(ctx)) return emptyList()
        val enabled = lm.getProviders(true)
        return buildList {
            if (hasFine(ctx)) add(LocationManager.GPS_PROVIDER)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                add(LocationManager.FUSED_PROVIDER)
            }
            add(LocationManager.NETWORK_PROVIDER)
            add(LocationManager.GPS_PROVIDER)
        }.distinct().filter { it in enabled }
    }

    /** The provider a fix stream uses; null when none fits. */
    fun pickProvider(ctx: Context, lm: LocationManager): String? =
        candidates(ctx, lm).firstOrNull()

    fun toMap(l: Location): Map<String, Any> = mapOf(
        "time" to l.time,
        "latitude" to l.latitude,
        "longitude" to l.longitude,
        "altitude" to if (l.hasAltitude()) l.altitude else 0.0,
        "accuracy" to if (l.hasAccuracy()) l.accuracy.toDouble() else 0.0,
        "isMock" to LocationCompat.isMock(l),
    )
}
