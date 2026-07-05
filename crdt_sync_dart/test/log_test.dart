import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

Hlc _make(int wallTimeMs, {int counter = 0, String nodeId = 'node-a'}) =>
    Hlc(wallTimeMs: wallTimeMs, counter: counter, nodeId: nodeId);

(Log, Log) _sampleLogs() {
  final a = <String, Record>{
    'shared': Record(id: 'shared', fields: {'text': ('a-version', _make(100))}),
    'only-in-a': Record(id: 'only-in-a', fields: {'text': ('a', _make(50))}),
  };
  final b = <String, Record>{
    'shared': Record(id: 'shared', fields: {'text': ('b-version', _make(200))}),
    'only-in-b': Record(id: 'only-in-b', fields: {'text': ('b', _make(50))}),
  };
  return (a, b);
}

void main() {
  group('mergeLogs', () {
    test('returns the union of disjoint ids', () {
      final local = <String, Record>{
        'a': Record(id: 'a', fields: {'text': ('a', _make(100))}),
      };
      final remote = <String, Record>{
        'b': Record(id: 'b', fields: {'text': ('b', _make(100))}),
      };
      expect(mergeLogs(local, remote), {...local, ...remote});
    });

    test('merges a shared id field by field', () {
      final local = <String, Record>{
        'a': Record(id: 'a', fields: {'text': ('old', _make(100))}),
      };
      final remote = <String, Record>{
        'a': Record(id: 'a', fields: {'text': ('new', _make(200))}),
      };
      final merged = mergeLogs(local, remote);
      expect(merged['a']!.fields['text'], equals(('new', _make(200))));
    });

    test('a delete on one side survives the merge', () {
      final local = <String, Record>{
        'a': Record(id: 'a', fields: {}, deleted: true, deletedHlc: _make(200)),
      };
      final remote = <String, Record>{
        'a': Record(id: 'a', fields: {'text': ('still here', _make(100))}),
      };
      expect(mergeLogs(local, remote)['a']!.deleted, isTrue);
    });

    test('does not mutate either input', () {
      final local = <String, Record>{
        'a': Record(id: 'a', fields: {'text': ('a', _make(100))}),
      };
      final remote = <String, Record>{
        'b': Record(id: 'b', fields: {'text': ('b', _make(100))}),
      };
      final localBefore = Map<String, Record>.from(local);
      final remoteBefore = Map<String, Record>.from(remote);
      mergeLogs(local, remote);
      expect(local, equals(localBefore));
      expect(remote, equals(remoteBefore));
    });
  });

  group('convergence properties', () {
    test('is commutative', () {
      final (a, b) = _sampleLogs();
      expect(mergeLogs(a, b), equals(mergeLogs(b, a)));
    });

    test('is idempotent', () {
      final (a, _) = _sampleLogs();
      expect(mergeLogs(a, a), equals(a));
    });

    test('repeated merge of the same remote is a no-op', () {
      final (a, b) = _sampleLogs();
      final once = mergeLogs(a, b);
      final twice = mergeLogs(once, b);
      expect(once, equals(twice));
    });
  });
}
