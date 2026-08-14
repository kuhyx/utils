/// The placeholder shown when a list has nothing in it.
library;

import 'package:design_system/src/tokens.dart';
import 'package:flutter/material.dart';

/// A centred icon, headline and explanation for an empty list.
///
/// Promoted from `home_inventory` — the only one of four fleet variants that
/// was already a reusable widget rather than an inlined `Column`.
class EmptyState extends StatelessWidget {
  /// Creates an empty-state placeholder.
  const EmptyState({
    required this.icon,
    required this.title,
    required this.message,
    super.key,
  });

  /// Glyph shown above the text.
  final IconData icon;

  /// Short headline, e.g. "Nothing here yet".
  final String title;

  /// One line explaining what to do about it.
  final String message;

  // Deliberately no `action` slot. No donor had one: home_inventory's three
  // call sites are pure placeholders, and kuhylog's action-bearing `_empty`
  // is a different element. Adding one here would be speculative surface --
  // the widget nobody imports, one parameter down.

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: AppSpacing.xxl,
              color: theme.colorScheme.onSurfaceVariant,
            ),
            const SizedBox(height: AppSpacing.md),
            Text(title, style: theme.textTheme.titleMedium),
            const SizedBox(height: AppSpacing.sm),
            Text(
              message,
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
