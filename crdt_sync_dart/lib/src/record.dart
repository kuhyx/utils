import 'hlc.dart';

/// A field value paired with the clock it was written at.
typedef Field = (Object?, Hlc);

/// One CRDT record: an id, per-field LWW values, and a sticky tombstone.
///
/// Mirrors `crdt_sync.Record` on the Python side. Deliberately
/// domain-agnostic -- translating an app's own model (a note, a food-log
/// entry, a workout entry, a wake-time value) to and from [Record] is each
/// app's job, not this library's.
class Record {
  const Record({
    required this.id,
    required this.fields,
    this.deleted = false,
    this.deletedHlc,
  });

  /// Stable identifier, unique within one `Log`.
  final String id;

  /// Field name -> `(value, Hlc)`. Concurrent edits to the same field
  /// converge to whichever side has the greater [Hlc].
  final Map<String, Field> fields;

  /// Whether this record is tombstoned. Deletion is monotonic: once true on
  /// either side of a merge, it stays true.
  final bool deleted;

  /// The clock value of the delete, if any -- informational/ordering only;
  /// it does not participate in the merge decision (see [mergeRecord]).
  final Hlc? deletedHlc;

  Map<String, dynamic> toJson() => {
    'id': id,
    'fields': fields.map(
      (name, field) => MapEntry(name, [field.$1, field.$2.toStr()]),
    ),
    'deleted': deleted,
    'deletedHlc': deletedHlc?.toStr(),
  };

  factory Record.fromJson(Map<String, dynamic> json) {
    final rawFields = json['fields'] as Map<String, dynamic>;
    final fields = rawFields.map((name, value) {
      final pair = value as List<dynamic>;
      return MapEntry(name, (pair[0], Hlc.fromStr(pair[1] as String)));
    });
    final deletedHlcStr = json['deletedHlc'] as String?;
    return Record(
      id: json['id'] as String,
      fields: fields,
      deleted: json['deleted'] as bool,
      deletedHlc: deletedHlcStr == null ? null : Hlc.fromStr(deletedHlcStr),
    );
  }

  @override
  bool operator ==(Object other) {
    if (other is! Record) return false;
    return id == other.id &&
        deleted == other.deleted &&
        deletedHlc == other.deletedHlc &&
        _fieldsEqual(fields, other.fields);
  }

  static bool _fieldsEqual(Map<String, Field> a, Map<String, Field> b) {
    if (a.length != b.length) return false;
    for (final entry in a.entries) {
      if (b[entry.key] != entry.value) return false;
    }
    return true;
  }

  @override
  int get hashCode => Object.hash(
    id,
    deleted,
    deletedHlc,
    Object.hashAllUnordered(
      fields.entries.map((e) => Object.hash(e.key, e.value)),
    ),
  );

  @override
  String toString() =>
      'Record(id: $id, fields: $fields, deleted: $deleted, '
      'deletedHlc: $deletedHlc)';
}

/// Returns whichever of [a], [b] has the greater [Hlc].
///
/// Ties (equal [Hlc]) keep [a]; two ticks never compare equal across
/// different nodes, so a tie only happens when both sides are literally the
/// same tick re-merged, in which case the value is expected to be identical
/// anyway.
Field mergeField(Field a, Field b) => a.$2 >= b.$2 ? a : b;

Hlc? _mergeDeletedHlc(Record a, Record b) {
  if (a.deleted && b.deleted) {
    if (a.deletedHlc == null) return b.deletedHlc;
    if (b.deletedHlc == null) return a.deletedHlc;
    return a.deletedHlc! >= b.deletedHlc! ? a.deletedHlc : b.deletedHlc;
  }
  if (a.deleted) return a.deletedHlc;
  if (b.deleted) return b.deletedHlc;
  return null;
}

/// Merges two versions of the same record.
///
/// Per-field last-writer-wins over the union of field names, plus a sticky
/// delete: `deleted = a.deleted || b.deleted`, never the other way around. A
/// tombstone can never be resurrected by merging in an older, non-deleted
/// copy pulled from a device that hasn't seen the delete yet.
///
/// Commutative and idempotent: `mergeRecord(a, b) == mergeRecord(b, a)` and
/// `mergeRecord(a, a) == a`.
///
/// Throws [ArgumentError] if `a.id != b.id` -- merging two different
/// records is a caller bug, not a case to silently paper over.
Record mergeRecord(Record a, Record b) {
  if (a.id != b.id) {
    throw ArgumentError(
      'cannot merge records with different ids: ${a.id} != ${b.id}',
    );
  }
  final mergedFields = Map<String, Field>.from(a.fields);
  for (final entry in b.fields.entries) {
    final existing = mergedFields[entry.key];
    mergedFields[entry.key] = existing == null
        ? entry.value
        : mergeField(existing, entry.value);
  }
  return Record(
    id: a.id,
    fields: mergedFields,
    deleted: a.deleted || b.deleted,
    deletedHlc: _mergeDeletedHlc(a, b),
  );
}
