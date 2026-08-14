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
    this.action,
    super.key,
  });

  /// Glyph shown above the text.
  final IconData icon;

  /// Short headline, e.g. "Nothing here yet".
  final String title;

  /// One line explaining what to do about it.
  final String message;

  /// Optional call to action below the message — usually the button that
  /// creates the first item. Omit it where the empty state is a *filter*
  /// result rather than an empty collection: there is nothing to create.
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final action = this.action;
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
            if (action != null) ...[
              const SizedBox(height: AppSpacing.lg),
              action,
            ],
          ],
        ),
      ),
    );
  }
}
