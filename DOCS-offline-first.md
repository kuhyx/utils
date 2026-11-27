# Offline-first audit of kuhy's syncing apps

Rule: `~/.claude/rules/offline-first.instructions.md` (kuhy, 2026-11-27). Every app that syncs or shares data
is offline-first: (a) a create/save lands locally first and is readable at once; (b) sync runs by itself and a
network failure keeps the write and retries; (c) everything pulled, details included, is kept locally and shown
offline and after a restart. Apps on `crdt_sync_dart` follow its README "Offline-first contract"
(`crdt_sync_dart/test/offline_first_test.dart`).

Audit run 2026-11-27 by todoImplementer card c5ee9e59-9 (read-only sweep of `~/src/*` manifests, evidence as
`file:line` under each app root, `lib/` left out for Dart apps). A FAIL row is fixed by its own commit; the
"Fix" column names it. A new syncing app adds its row here when it ships.

| App | Sync | (a) | (b) | (c) | Verdict | Evidence | Fix |
|---|---|---|---|---|---|---|---|
| ~/src/todo | crdt_sync LogStore + Firebase/GitHub mirror | PASS | PASS | PASS | PASS | `data/note_repository.dart:59-60`, launch/pause/focus sync `ui/capture_screen.dart:118,180,187`, importLog before push `sync/sync_service.dart:171` | model app |
| ~/src/todoImplementer/app | rtdb_relay board relay | FAIL | FAIL | FAIL | FAIL | new task existed only after a relay send `ui/board/new_task_sheet.dart:121-133`; board and task details never kept `sync/rtdb_board_relay.dart:106-118`, `ui/board/detail_page.dart:88-99` | T2603 board + details kept, prefetched per sync; T2604 outbox (kuhyx/todoImplementer) |
| ~/src/home_inventory | crdt_sync LogStore + mirror | PASS | FAIL | PASS | FAIL | only the "Sync now" button syncs `screens/github_mirror_screen.dart:168` | pending |
| ~/src/lyricanki | crdt_sync LogStore + openSync | PASS | FAIL | PASS | FAIL | sync only from `onSync` `screens/song_search_screen.dart:219` | pending |
| ~/src/restaurant-rater | crdt_sync LogStore + openSync | PASS | FAIL | PASS | FAIL | no sync on launch/resume, a failed push waits for the next edit `sync/sync_bootstrap.dart:105`, `app.dart:17-26` | pending |
| ~/src/leetcode-guard/app | crdt_sync snapshot + coach relay | FAIL | FAIL | FAIL | FAIL | coach requests memory-only `coach/controller_send.dart:25-37`; chat memory-only `coach/controller.dart:216-222` | pending |
| ~/src/tutor/app | rtdb_relay | PASS | PASS | PASS | PASS | outbox for picks and reports `sync/put_outbox.dart`; archive flags queued and History kept `history/history.dart`; stats/today kept `home/remote_bits.dart`; last session kept `session/session_kept.dart`; e2e header kept so a cold start offline unlocks `sync/rtdb_client.dart`; every read/listen gated by `test/sync/offline_first_reads_test.dart` | d7f6e86, faf130a, b3df844, 0e4d7b1, 6ad66d4 (kuhyx/tutor) |
| ~/src/screen-locker/stronglift_replacement/workout_app | crdt_sync syncLog + run queue | PASS | FAIL | FAIL | FAIL | failed workout push only logged `screens/workout_screen_finish.dart:125-130`; merge thrown away `services/workout_sync_session.dart:111` | pending |
| ~/src/dufs-cloud/app | WebDAV | unverified | unverified | FAIL | FAIL | listings uncached `services/dufs_client.dart:65` | pending |
| ~/src/signal-bot/app | HTTP management API | FAIL | FAIL | FAIL | FAIL | live reads, direct edits `api.dart:63-71,95` | pending |
| ~/src/logo-review/app | HTTP review server | unverified | unverified | FAIL | FAIL | pictures session-only `ui/service_badge.dart:12`; feedback POST `api.dart:74` | pending |
| ~/src/kuhytrack | own HTTP server + watchers | PASS | PASS | FAIL | N/A: archived | readers fetch live `web/dashboard.html:119`, `cli/ktq.py:58`; repo archived on GitHub 2026-11-02 | fix kept unpushed on local branch `todo/c5ee9e59-9-kuhytrack` (30ae4a8) |
| ~/src/punchme | crdt_sync LogStore + openSync | PASS | PASS | PASS | PASS | store loads `sync/sync_bootstrap.dart:66` before openSync `:73`, push per write `:90` | none |
| ~/src/diet-guard/app | crdt_sync + RTDB relay | PASS | PASS | PASS | PASS | `services/log_storage_service.dart:108`, WorkManager backstop `services/background_tasks_io.dart:21,36` | none |
| ~/src/wake-alarm/phone_app | crdt_sync LogStore + native sync | PASS | PASS | PASS | PASS | `services/alarm_policy.dart:117-118`, `services/alarm_sync_service.dart:102-103` | none |
| ~/src/daily-limits/app | crdt_sync RTDB + request queue | PASS | PASS | PASS | PASS | `services/limits_controller.dart:102-130`, `services/sync_once.dart:68-97` | none |
| ~/src/home-guard/app | crdt_sync RTDB + upload queue | PASS | PASS | PASS | PASS | `screens/home_screen.dart:168-169`, zones cached `services/zone_sync.dart:73-87` (remote read before cache, no timeout `:105-108`) | none |
| ~/src/phone-focus-mode/focus-owner | crdt_sync push + native queue | PASS | PASS | PASS | PASS | `android/.../UninstallEvents.kt:25,112-115` | none |
| ~/src/kartka | own RTDB engine | PASS | PASS | PASS | PASS | `sync/decorators/synced_library.dart:35-42`, `sync/sync_engine.dart:127-129` | none |
| ~/src/sufler | crdt_sync + RTDB relay | PASS | PASS | PASS | PASS | `assist/ask.dart:19-20,85,99` | none |
| ~/src/book-guard/app | WebDAV outbox | PASS | PASS | PASS | PASS | `src/guard_api.dart:95,101-105,128-133` | none |
| PC sides (Python): diet-guard, wake-alarm, screen-locker, leetcode-guard, daily-limits, build-your-x, home-guard | crdt-sync / RTDB | PASS | PASS | PASS | PASS | e.g. `diet_guard/_sync.py:181,242`, `wake_alarm/_sync_transport.py:5-18`; build-your-x trigger and home-guard zone merge unverified | none |
| Relay workers: todoImplementer, tutor, sufler | rtdb_relay (PC) | ? | ? | ? | pending | not read yet | pending |

Not syncing (dropped): kuhylog, tunedeck, habit_stack (no sync wiring yet: it must meet this rule when it gets
one), umbrella, game-research, pacman-yay-gui, WUT_Computer_Science, dufs-cloud/firebase_backup.
