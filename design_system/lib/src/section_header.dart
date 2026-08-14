/// A labelled divider between groups of controls in a long screen.
library;

import 'package:design_system/src/tokens.dart';
import 'package:flutter/material.dart';

/// A section title, optionally with a trailing action.
///
/// Reconciles the fleet's variants, which agreed on `titleMedium` and
/// differed only in what they wrapped around it: `untools`' `_SectionHeading`
/// supported a trailing action and no padding; `billsplit`'s `_SectionHeader`
/// had padding and no action. This is the union — both are opt-in, so either
/// caller can adopt it without a visual change.
class SectionHeader extends StatelessWidget {
  /// Creates a section header.
  const SectionHeader(
    this.title, {
    this.action,
    this.padding,
    super.key,
  });

  /// The section's title.
  final String title;

  /// Optional trailing control, right-aligned on the same baseline —
  /// typically an "Add" or "Clear" button scoped to this section.
  final Widget? action;

  /// Outer padding. Defaults to none, so the header inherits whatever the
  /// surrounding list already applies; pass [defaultPadding] for a header
  /// sitting directly in an unpadded `ListView`.
  final EdgeInsetsGeometry? padding;

  /// Padding for a header placed directly in an unpadded scroll view: full
  /// gutters, generous above, tight below so the title groups with the
  /// content it labels rather than floating between two sections.
  static const EdgeInsets defaultPadding = EdgeInsets.fromLTRB(
    AppSpacing.md,
    AppSpacing.md,
    AppSpacing.md,
    AppSpacing.xs,
  );

  @override
  Widget build(BuildContext context) {
    final row = Row(
      children: [
        Expanded(
          child: Text(title, style: Theme.of(context).textTheme.titleMedium),
        ),
        ?action,
      ],
    );
    final padding = this.padding;
    if (padding == null) {
      return row;
    }
    return Padding(padding: padding, child: row);
  }
}
