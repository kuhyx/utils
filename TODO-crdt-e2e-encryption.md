# Encrypt crdt_sync payloads end to end

## what
Firebase RTDB stores every crdt_sync record in plaintext, so Google can read
all app data. Encrypt record payloads on the device before push and decrypt
after pull, so RTDB stays a blind relay (the "ownership" meaning of
local-first: hologram.page/blog/local-first-means-three-different-things).

## open decisions (ask kuhy before coding)
- Key source: derived from the shared crdt-sync password (Argon2id) or a
  random key stored in the OS keystore and copied to new devices.
- Migration: re-encrypt existing logs in place, or new prefix + one-time copy.
- Scope: payload only (keep HLC/ids clear for merge) or whole record.
- diet_guard's `export_keys` document (random data-export keys, synced as a
  keyring) sits in plaintext in RTDB, so Firebase can read them: it must move
  under E2E too, with its key source decided here first.
- tutor uses its own RTDB client (`~/src/tutor/app/lib/sync/rtdb_client.dart`):
  in or out of scope.

## steps
1. Add an encrypt/decrypt seam in `crdt_sync_dart/lib/src/remote_store.dart`
   (push/pull), AEAD (XChaCha20-Poly1305), version byte per record.
2. Property test: decrypt(encrypt(r)) == r; merge result identical with and
   without encryption (see property-and-differential-tests skill).
3. Read path accepts plaintext and v1 records during migration.
4. Roll out app by app (todo first), bump pins, verify on the phone.

## done
`dart test` in `crdt_sync_dart` passes, and
`firebase database:get /<prefix> | grep -c '"title"'` returns 0 for every
migrated app.

## verify
Pixel 6a + desktop todo: edit on one, see it on the other; raw RTDB JSON shows
only ciphertext.

## read first
- `crdt_sync_dart/lib/src/sync.dart`, `log.dart`, `remote_store.dart`
- `crdt_sync_flutter/lib/src/bootstrap.dart`

REMOVE ME AFTER FINISH
