/// The kuhy logo as a Flutter widget.
///
/// Uses the canonical SVG from unified-design-system/logo/final/kuhy.svg
/// (charcoal #211D1B field, shared accent #B8862E + off-white #ECEAE9 glyphs).
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_svg/flutter_svg.dart';

/// The kuhy logo widget.
///
/// Renders the canonical kuhy logo at any size. The asset is bundled with
/// the design_system package so every app gets it from one source.
///
/// Example:
/// ```dart
/// const KLogo(size: 48)
/// ```
class KLogo extends StatelessWidget {
  /// Creates the logo.
  const KLogo({
    super.key,
    this.size = 48,
    this.color,
    this.semanticLabel = 'kuhy logo',
  });

  /// The logo size in logical pixels (width = height).
  final double size;

  /// Optional color filter — when null, uses the SVG's own colours.
  final Color? color;

  /// Semantic label for accessibility.
  final String semanticLabel;

  @override
  Widget build(BuildContext context) => Semantics(
        label: semanticLabel,
        child: SvgPicture.asset(
          'packages/design_system/assets/logo/kuhy.svg',
          package: 'design_system',
          width: size,
          height: size,
          colorFilter: color != null ? ColorFilter.mode(color!, BlendMode.srcIn) : null,
        ),
      );
}

/// Small kuhy logo — 24px, for inline use.
class KLogoSmall extends StatelessWidget {
  /// Creates the small logo.
  const KLogoSmall({
    super.key,
    this.color,
    this.semanticLabel = 'kuhy logo',
  });

  /// Optional color filter.
  final Color? color;

  /// Semantic label for accessibility.
  final String semanticLabel;

  @override
  Widget build(BuildContext context) => KLogo(
        size: 24,
        color: color,
        semanticLabel: semanticLabel,
      );
}

/// Medium kuhy logo — 32px, for headers.
class KLogoMedium extends StatelessWidget {
  /// Creates the medium logo.
  const KLogoMedium({
    super.key,
    this.color,
    this.semanticLabel = 'kuhy logo',
  });

  /// Optional color filter.
  final Color? color;

  /// Semantic label for accessibility.
  final String semanticLabel;

  @override
  Widget build(BuildContext context) => KLogo(
        size: 32,
        color: color,
        semanticLabel: semanticLabel,
      );
}

/// Large kuhy logo — 48px, for splash/about screens.
class KLogoLarge extends StatelessWidget {
  /// Creates the large logo.
  const KLogoLarge({
    super.key,
    this.color,
    this.semanticLabel = 'kuhy logo',
  });

  /// Optional color filter.
  final Color? color;

  /// Semantic label for accessibility.
  final String semanticLabel;

  @override
  Widget build(BuildContext context) => KLogo(
        size: 48,
        color: color,
        semanticLabel: semanticLabel,
      );
}

/// Extra-large kuhy logo — 96px, for splash screens.
class KLogoXLarge extends StatelessWidget {
  /// Creates the extra-large logo.
  const KLogoXLarge({
    super.key,
    this.color,
    this.semanticLabel = 'kuhy logo',
  });

  /// Optional color filter.
  final Color? color;

  /// Semantic label for accessibility.
  final String semanticLabel;

  @override
  Widget build(BuildContext context) => KLogo(
        size: 96,
        color: color,
        semanticLabel: semanticLabel,
      );
}