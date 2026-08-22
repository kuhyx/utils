import 'remote_store.dart';

/// Raised for a Realtime Database failure the caller must not silently
/// ignore.
class FirebaseSyncError extends RemoteSyncError {
  FirebaseSyncError(super.message);
}

/// Raised when the database itself is unreachable or the credential is not
/// authorized for it.
///
/// The Firebase counterpart of `RepoNotFoundError`: it means "the database
/// URL is wrong, or the security rules reject this uid", as opposed to
/// "nothing has been pushed to that path yet", which is benign and surfaces
/// as a null/empty result.
class DatabaseNotFoundError extends FirebaseSyncError
    implements RemoteNotFoundError {
  DatabaseNotFoundError(super.message);
}
