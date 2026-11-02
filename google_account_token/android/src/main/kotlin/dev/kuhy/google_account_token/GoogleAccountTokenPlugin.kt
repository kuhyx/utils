package dev.kuhy.google_account_token

import android.accounts.Account
import android.accounts.AccountManager
import android.accounts.AccountManagerFuture
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.PluginRegistry

/**
 * System account chooser, then a Google ID token from AccountManager.
 * No browser and no Google client library. The Dart side is
 * `lib/google_account_token.dart`; apps register nothing by hand.
 */
class GoogleAccountTokenPlugin :
    FlutterPlugin,
    ActivityAware,
    MethodChannel.MethodCallHandler,
    PluginRegistry.ActivityResultListener {

    private var channel: MethodChannel? = null
    private var binding: ActivityPluginBinding? = null
    private var pending: MethodChannel.Result? = null
    private var audience: String = ""

    override fun onAttachedToEngine(flutter: FlutterPlugin.FlutterPluginBinding) {
        channel = MethodChannel(flutter.binaryMessenger, CHANNEL).also {
            it.setMethodCallHandler(this)
        }
    }

    override fun onDetachedFromEngine(flutter: FlutterPlugin.FlutterPluginBinding) {
        channel?.setMethodCallHandler(null)
        channel = null
    }

    override fun onAttachedToActivity(activityBinding: ActivityPluginBinding) {
        binding = activityBinding
        activityBinding.addActivityResultListener(this)
    }

    // A rotation recreates the Activity. The chooser result is re-delivered
    // to the new one, so a pending request is kept across the swap.
    override fun onDetachedFromActivityForConfigChanges() = detach()

    override fun onReattachedToActivityForConfigChanges(
        activityBinding: ActivityPluginBinding,
    ) = onAttachedToActivity(activityBinding)

    override fun onDetachedFromActivity() {
        detach()
        finish { it.error("no_activity", "activity went away", null) }
    }

    private fun detach() {
        binding?.removeActivityResultListener(this)
        binding = null
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        if (call.method != "idToken") {
            result.notImplemented()
            return
        }
        val activity = binding?.activity
        val clientId = call.argument<String>("serverClientId")
        when {
            activity == null ->
                result.error("no_activity", "no foreground activity", null)
            clientId.isNullOrEmpty() ->
                result.error("bad_args", "serverClientId is required", null)
            pending != null ->
                result.error("busy", "sign-in already running", null)
            else -> {
                audience = clientId
                pending = result
                val hint = call.argument<String>("accountHint")
                    ?.takeIf { it.isNotEmpty() }
                    ?.let { Account(it, ACCOUNT_TYPE) }
                // First argument only preselects `hint`; the chooser always shows.
                val chooser = AccountManager.newChooseAccountIntent(
                    hint, null, arrayOf(ACCOUNT_TYPE), null, null, null, null,
                )
                activity.startActivityForResult(chooser, REQUEST_CHOOSE)
            }
        }
    }

    override fun onActivityResult(request: Int, code: Int, data: Intent?): Boolean {
        if (request != REQUEST_CHOOSE) return false
        val name = data?.getStringExtra(AccountManager.KEY_ACCOUNT_NAME)
        val type = data?.getStringExtra(AccountManager.KEY_ACCOUNT_TYPE)
        if (code != Activity.RESULT_OK || name == null || type == null) {
            finish { it.success(null) }
        } else {
            fetchToken(Account(name, type))
        }
        return true
    }

    private fun fetchToken(account: Account) {
        val activity = binding?.activity
        if (activity == null) {
            finish { it.error("no_activity", "activity went away", null) }
            return
        }
        // Activity argument: the framework launches any consent screen itself.
        AccountManager.get(activity).getAuthToken(
            account, tokenType(audience), Bundle(), activity,
            { future -> deliver(future) },
            Handler(Looper.getMainLooper()),
        )
    }

    private fun deliver(future: AccountManagerFuture<Bundle>) {
        try {
            val bundle = future.result
            val token = bundle.getString(AccountManager.KEY_AUTHTOKEN)
            if (token != null) {
                finish { it.success(token) }
            } else {
                finish { it.error("no_token", "keys: ${bundle.keySet()}", null) }
            }
        } catch (e: Exception) {
            finish { it.error("auth_failed", e.toString(), null) }
        }
    }

    private fun finish(block: (MethodChannel.Result) -> Unit) {
        val result = pending ?: return
        pending = null
        block(result)
    }

    companion object {
        const val CHANNEL = "dev.kuhy/google_account_token"
        const val ACCOUNT_TYPE = "com.google"
        private const val REQUEST_CHOOSE = 7421

        /** The AccountManager token type that mints an ID token for [clientId]. */
        fun tokenType(clientId: String): String =
            "audience:server:client_id:$clientId"
    }
}
