# freedays

One shared pool of pre-declared days on which **every** gate app stands down.

Mark a day. Nothing locks, nothing rings, nothing asks you for a photo, and
nothing mentions it afterwards.

## For a gate app

The entire integration is one call:

```python
import freedays

if freedays.is_free_day():
    return  # no lock, no dialog, no alarm -- and say nothing
```

`is_free_day()` reads one local JSON file. It never touches the network, so
it cannot block a systemd-fired gate, and it returns `False` for anything it
cannot parse — an unreadable pool means *the normal rules apply*, never that
everything is switched off.

## For a person

```console
$ freedays status
2026: 33 of 35 free days left
booked ahead: 2026-12-24

$ freedays mark 2026-12-24 --reason "travelling"
$ freedays mark today
$ freedays release 2026-12-24
$ freedays check tomorrow      # exit 0 if free, 1 if not -- for scripts
$ freedays sync                # pull and push now
```

## The rules

| | |
|---|---|
| **Budget** | 35 per calendar year, resetting Jan 1. Unused days do not carry over. |
| **One pool** | A free day is free for *every* app at once. There is nothing per-app to mark, and nothing per-app to forget. |
| **Declared, not backdated** | Today or later. A past day cannot be marked, so a gate you already failed cannot be erased afterwards. |
| **Consecutive is fine** | Take a fortnight in a row if you want. Nothing here rate-limits you. |
| **No reason required** | `--reason` is stored if given and never asked for. |
| **Releasing refunds only the future** | Give back a day that has not arrived and it returns to the pool. Give back today, and it does not: those hours were already unguarded. |
| **Silent** | No notification, no low-budget warning, no prompt when a gate fires. You find out by asking. |

## Free days are not sick days

screen-locker's sick days stay exactly where they are, with their rolling
windows, their 120-character justifications and their escalating countdown.
They are *designed to be hard to take*.

These are the opposite, and merging the two would have to ruin one of them:
rolling windows forbid consecutive days, which is the entire point of a
holiday. So the policies stay separate. Only the storage is shared.

## How it syncs

Firebase RTDB, one directory per device under `freedays-sync/devices/`, the
same shape every other app in this fleet uses. No two devices write the same
node, so nothing can conflict; convergence is the CRDT layer's job.

Marking is a last-writer-wins flip of a `state` field rather than a create
and a delete, because crdt-sync tombstones are monotonic — deleting the
record would burn that date permanently, and a released day has to be
markable again.

`consumed` is a deliberately sticky flag: once a day has arrived while free
it stays spent, even if two devices disagree about what "today" is across a
midnight boundary.

## Timezone

Local, everywhere, decided in `_day.today()` and nowhere else.

This package exists partly because the apps disagreed about it: screen-locker
computed the day in UTC in its lock chain while the tool that wrote its skip
file used local time, so a skip added near midnight could name a date the
chain never matched. A free day is a human calendar day — if it is Tuesday
where you are standing, it is Tuesday.

## Development

```console
$ pip install ../crdt-sync
$ pip install -r requirements.txt && pip install --no-deps -e .
$ python -m pytest              # 100% branch coverage is enforced
$ pre-commit run --config .pre-commit-config.yaml --all-files
```
