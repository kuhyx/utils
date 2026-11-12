part of 'sync_settings_screen.dart';

/// The screen's glyph vocabulary, in place of written headings and status
/// sentences (kuhy's textgate rule). Every old sentence survives as the
/// spoken label, so screen readers and widget tests still find it.

/// A result: a glyph, the old sentence (spoken only), and whether it is a
/// failure. Colour is the second channel: danger hue for failures.
class _Cue {
  const new(this.icon, this.spoken) : error = false;

  const new error(this.icon, this.spoken) : error = true;

  final IconData icon;
  final String spoken;
  final bool error;
}

/// Paints a [_Cue] as a large glyph.
class _CueView extends StatelessWidget {
  const new(this.cue);

  final _Cue cue;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Align(
      alignment: Alignment.centerLeft,
      child: Icon(
        cue.icon,
        size: 32,
        color: cue.error ? scheme.error : scheme.primary,
        semanticLabel: cue.spoken,
      ),
    );
  }
}

/// A section heading as a glyph, spoken as [spoken].
class _Heading extends StatelessWidget {
  const new(this.icon, this.spoken);

  final IconData icon;
  final String spoken;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerLeft,
    child: Icon(
      icon,
      color: Theme.of(context).colorScheme.primary,
      semanticLabel: spoken,
    ),
  );
}
