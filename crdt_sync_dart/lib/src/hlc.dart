/// A Hybrid Logical Clock: a totally-ordered, monotonic per-node timestamp.
///
/// Combines wall-clock time with a logical counter so two ticks issued by
/// the same node in the same millisecond still get a strict order, and two
/// ticks from different nodes are always comparable (the node id breaks
/// ties), without requiring synchronized clocks across devices. Mirrors
/// `crdt_sync._hlc.Hlc` on the Python side field-for-field so the two
/// serialize to and parse the same wire format.
class Hlc implements Comparable<Hlc> {
  const Hlc({
    required this.wallTimeMs,
    required this.counter,
    required this.nodeId,
  });

  final int wallTimeMs;
  final int counter;
  final String nodeId;

  static const _isoPrefixLen = 23; // "YYYY-MM-DDTHH:MM:SS.mmm"

  /// Returns the next clock value for [nodeId].
  ///
  /// Passing [previous] (this node's last-issued clock) is what makes the
  /// clock monotonic even when the wall clock hasn't advanced (or has gone
  /// backwards). [wallTimeMsOverride] is exposed for deterministic tests.
  static Hlc newTick(String nodeId, {Hlc? previous, int? wallTimeMsOverride}) {
    final now =
        wallTimeMsOverride ?? DateTime.now().toUtc().millisecondsSinceEpoch;
    if (previous == null) {
      return Hlc(wallTimeMs: now, counter: 0, nodeId: nodeId);
    }
    final newWall = now > previous.wallTimeMs ? now : previous.wallTimeMs;
    final counter = newWall == previous.wallTimeMs ? previous.counter + 1 : 0;
    return Hlc(wallTimeMs: newWall, counter: counter, nodeId: nodeId);
  }

  /// Serializes to a lexicographically sortable string:
  /// `<iso8601-millis>Z-<counter:hex4>-<nodeId>`.
  String toStr() {
    final dt = DateTime.fromMillisecondsSinceEpoch(wallTimeMs, isUtc: true);
    String two(int n) => n.toString().padLeft(2, '0');
    final iso =
        '${dt.year.toString().padLeft(4, '0')}-${two(dt.month)}-${two(dt.day)}'
        'T${two(dt.hour)}:${two(dt.minute)}:${two(dt.second)}'
        '.${(wallTimeMs % 1000).toString().padLeft(3, '0')}';
    final counterHex = counter.toRadixString(16).padLeft(4, '0');
    return '${iso}Z-$counterHex-$nodeId';
  }

  /// Parses the format produced by [toStr]. Throws [FormatException].
  static Hlc fromStr(String text) {
    final zIndex = text.indexOf('Z-');
    if (zIndex == -1 || zIndex != _isoPrefixLen) {
      throw FormatException('not a valid Hlc string', text);
    }
    final isoPart = text.substring(0, zIndex);
    final rest = text.substring(zIndex + 2);
    final dashIndex = rest.indexOf('-');
    if (dashIndex == -1) {
      throw FormatException('not a valid Hlc string', text);
    }
    final counterHex = rest.substring(0, dashIndex);
    final nodeId = rest.substring(dashIndex + 1);
    final dt = DateTime.parse('${isoPart}Z');
    return Hlc(
      wallTimeMs: dt.millisecondsSinceEpoch,
      counter: int.parse(counterHex, radix: 16),
      nodeId: nodeId,
    );
  }

  @override
  int compareTo(Hlc other) {
    if (wallTimeMs != other.wallTimeMs) {
      return wallTimeMs.compareTo(other.wallTimeMs);
    }
    if (counter != other.counter) {
      return counter.compareTo(other.counter);
    }
    return nodeId.compareTo(other.nodeId);
  }

  bool operator >(Hlc other) => compareTo(other) > 0;
  bool operator >=(Hlc other) => compareTo(other) >= 0;
  bool operator <(Hlc other) => compareTo(other) < 0;
  bool operator <=(Hlc other) => compareTo(other) <= 0;

  @override
  bool operator ==(Object other) =>
      other is Hlc &&
      wallTimeMs == other.wallTimeMs &&
      counter == other.counter &&
      nodeId == other.nodeId;

  @override
  int get hashCode => Object.hash(wallTimeMs, counter, nodeId);

  @override
  String toString() =>
      'Hlc(wallTimeMs: $wallTimeMs, counter: $counter, nodeId: $nodeId)';
}
