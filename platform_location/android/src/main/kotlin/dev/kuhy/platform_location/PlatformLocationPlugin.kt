package dev.kuhy.platform_location

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.location.LocationManagerCompat
import androidx.core.os.CancellationSignal
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.PluginRegistry

/**
 * Location through AOSP's LocationManager (androidx LocationManagerCompat).
 * No Google Play services. The Dart side is `lib/platform_location.dart`.
 *
 * Only requestPermission needs an Activity; everything else works in a
 * background engine (foreground-service isolate) too.
 */
class PlatformLocationPlugin :
    FlutterPlugin,
    ActivityAware,
    MethodChannel.MethodCallHandler,
    PluginRegistry.RequestPermissionsResultListener {

    private var context: Context? = null
    private var channel: MethodChannel? = null
    private var events: EventChannel? = null
    private var fixStream: FixStream? = null
    private var binding: ActivityPluginBinding? = null
    private var pendingPermission: MethodChannel.Result? = null

    override fun onAttachedToEngine(flutter: FlutterPlugin.FlutterPluginBinding) {
        val ctx = flutter.applicationContext
        context = ctx
        channel = MethodChannel(flutter.binaryMessenger, CHANNEL).also {
            it.setMethodCallHandler(this)
        }
        val stream = FixStream(ctx)
        fixStream = stream
        events = EventChannel(flutter.binaryMessenger, "$CHANNEL/fixes").also {
            it.setStreamHandler(stream)
        }
    }

    override fun onDetachedFromEngine(flutter: FlutterPlugin.FlutterPluginBinding) {
        channel?.setMethodCallHandler(null)
        events?.setStreamHandler(null)
        fixStream?.onCancel(null)
        channel = null
        events = null
        fixStream = null
        context = null
    }

    override fun onAttachedToActivity(activityBinding: ActivityPluginBinding) {
        binding = activityBinding
        activityBinding.addRequestPermissionsResultListener(this)
    }

    override fun onDetachedFromActivityForConfigChanges() = detach()

    override fun onReattachedToActivityForConfigChanges(
        activityBinding: ActivityPluginBinding,
    ) = onAttachedToActivity(activityBinding)

    override fun onDetachedFromActivity() {
        detach()
        pendingPermission?.error("no_activity", "activity went away", null)
        pendingPermission = null
    }

    private fun detach() {
        binding?.removeRequestPermissionsResultListener(this)
        binding = null
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        val ctx = context ?: return result.error("no_context", "detached", null)
        when (call.method) {
            "isLocationEnabled" -> result.success(Locations.locationEnabled(ctx))
            "checkPermission" -> result.success(check(ctx))
            "requestPermission" ->
                request(ctx, call.argument<Boolean>("precise") ?: true, result)
            "currentLocation" -> current(ctx, result)
            else -> result.notImplemented()
        }
    }

    /**
     * Granted, or a refusal. "Forever" needs a past request (remembered in
     * prefs) plus an Activity to ask for the rationale: without the memory,
     * the app's resume re-check would turn a fresh deniedForever back into
     * denied. Same rule geolocator used.
     */
    private fun check(ctx: Context): String {
        if (Locations.hasAny(ctx)) return GRANTED
        val activity = binding?.activity ?: return DENIED
        return if (asked(ctx) && permanentlyDenied(activity)) DENIED_FOREVER else DENIED
    }

    private fun prefs(ctx: Context) =
        ctx.getSharedPreferences("dev.kuhy.platform_location", Context.MODE_PRIVATE)

    private fun asked(ctx: Context): Boolean = prefs(ctx).getBoolean(ASKED, false)

    private fun request(ctx: Context, precise: Boolean, result: MethodChannel.Result) {
        if (Locations.hasAny(ctx)) return result.success(GRANTED)
        val activity = binding?.activity
            ?: return result.error("no_activity", "no foreground activity", null)
        if (pendingPermission != null) {
            return result.error("busy", "a permission request is in flight", null)
        }
        pendingPermission = result
        prefs(ctx).edit().putBoolean(ASKED, true).apply()
        val perms = if (precise) {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, COARSE)
        } else {
            arrayOf(COARSE)
        }
        ActivityCompat.requestPermissions(activity, perms, REQUEST_CODE)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ): Boolean {
        if (requestCode != REQUEST_CODE) return false
        val result = pendingPermission ?: return true
        pendingPermission = null
        val granted = grantResults.any { it == PackageManager.PERMISSION_GRANTED }
        result.success(
            when {
                granted -> GRANTED
                // No rationale after a refusal means "don't ask again" (or a
                // policy block): the prompt will not show any more.
                binding?.activity?.let { permanentlyDenied(it) } == true ->
                    DENIED_FOREVER
                else -> DENIED
            },
        )
        return true
    }

    private fun permanentlyDenied(activity: Activity): Boolean =
        !ActivityCompat.shouldShowRequestPermissionRationale(activity, COARSE)

    /**
     * Asks every enabled provider at once; the first fix wins and cancels
     * the rest. One provider alone can sit out its whole ~30 s timeout with
     * nothing (seen: fused indoors while GPS had a fix). When all come back
     * empty, the newest cached fix, else a no_fix error.
     */
    private fun current(ctx: Context, result: MethodChannel.Result) {
        val lm = Locations.locationManager(ctx)
        val providers = Locations.candidates(ctx, lm)
        if (providers.isEmpty()) {
            return result.error("unavailable", "no permission or provider", null)
        }
        val cancel = providers.associateWith { CancellationSignal() }
        var pending = providers.size
        var answered = false
        val reply = { location: Location? ->
            pending--
            if (!answered && (location != null || pending == 0)) {
                answered = true
                cancel.values.forEach { it.cancel() }
                val fix = location ?: lastKnown(lm, ctx)
                if (fix == null) {
                    result.error("no_fix", "no location from $providers", null)
                } else {
                    result.success(Locations.toMap(fix))
                }
            }
        }
        val main = ContextCompat.getMainExecutor(ctx)
        for (provider in providers) {
            try {
                LocationManagerCompat.getCurrentLocation(
                    lm, provider, cancel.getValue(provider), main,
                ) { reply(it) }
            } catch (_: SecurityException) {
                main.execute { reply(null) }
            }
        }
    }

    // A one-shot request can time out indoors; the newest cached fix from
    // any enabled provider is good enough for a coarse "where am I".
    private fun lastKnown(lm: LocationManager, ctx: Context): Location? {
        if (!Locations.hasAny(ctx)) return null
        return try {
            lm.getProviders(true)
                .mapNotNull { lm.getLastKnownLocation(it) }
                .maxByOrNull { it.time }
        } catch (_: SecurityException) {
            null
        }
    }

    companion object {
        const val CHANNEL = "dev.kuhy/platform_location"
        private const val REQUEST_CODE = 0x10c4
        private const val COARSE = Manifest.permission.ACCESS_COARSE_LOCATION
        private const val GRANTED = "granted"
        private const val DENIED = "denied"
        private const val DENIED_FOREVER = "deniedForever"
        private const val ASKED = "asked"
    }
}
