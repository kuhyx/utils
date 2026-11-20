import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:kuhy_credit/src/credit_data.g.dart';
import 'package:url_launcher/url_launcher.dart';

/// Opens [uri] in the system browser: a new tab on web, the browser app on
/// Android.
Future<void> openInBrowser(Uri uri) async {
  await launchUrl(
    uri,
    mode: LaunchMode.externalApplication,
    webOnlyWindowName: '_blank',
  );
}

/// The shared kuhy credit.
///
/// Shows the M1 logo. A tap (or Enter/Space) opens a small panel with the
/// logo and the credit text; a tap on the panel opens the website through
/// [launcher] and closes it. Escape, Back, a tap outside and a second logo
/// tap close the panel. Colours follow the platform brightness.
class KuhyCredit extends StatefulWidget {
  /// Creates the credit.
  const KuhyCredit({
    super.key,
    this.size = 48,
    this.below = false,
    this.alignStart = false,
    this.launcher = openInBrowser,
  });

  /// Finds the logo button in tests.
  static const ValueKey<String> logoKey = ValueKey('kuhy_credit.logo');

  /// Finds the open panel in tests.
  static const ValueKey<String> panelKey = ValueKey('kuhy_credit.panel');

  /// Logo edge length in logical pixels.
  final double size;

  /// Open the panel under the logo instead of above it.
  final bool below;

  /// Align the panel's start edge with the logo instead of its end edge.
  final bool alignStart;

  /// Opens the website; replace it to stub the browser in tests.
  final Future<void> Function(Uri uri) launcher;

  @override
  State<KuhyCredit> createState() => _KuhyCreditState();
}

class _KuhyCreditState extends State<KuhyCredit> {
  final _portal = OverlayPortalController();
  final _link = LayerLink();
  final _logoFocus = FocusNode();
  final _panelFocus = FocusNode();

  @override
  void dispose() {
    _logoFocus.dispose();
    _panelFocus.dispose();
    super.dispose();
  }

  void _toggle() {
    if (_portal.isShowing) {
      _close();
      return;
    }
    setState(_portal.show);
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => _panelFocus.requestFocus(),
    );
  }

  void _close() {
    if (_portal.isShowing) setState(_portal.hide);
  }

  Future<void> _activate() async {
    _close();
    await widget.launcher(Uri.parse(kCreditUrl));
  }

  KeyEventResult _onPanelKey(FocusNode _, KeyEvent event) {
    if (event is! KeyDownEvent) return KeyEventResult.ignored;
    final key = event.logicalKey;
    if (key == LogicalKeyboardKey.escape) {
      _close();
      _logoFocus.requestFocus();
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.enter || key == LogicalKeyboardKey.space) {
      unawaited(_activate());
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    final dark = MediaQuery.platformBrightnessOf(context) == Brightness.dark;
    final above = !widget.below;
    final end = !widget.alignStart;
    final logo = Semantics(
      button: true,
      expanded: _portal.isShowing,
      label: kCreditText,
      excludeSemantics: true,
      onTap: _toggle,
      child: FocusableActionDetector(
        focusNode: _logoFocus,
        mouseCursor: SystemMouseCursors.click,
        actions: {
          ActivateIntent: CallbackAction<ActivateIntent>(
            onInvoke: (_) => _toggle(),
          ),
        },
        child: GestureDetector(
          key: KuhyCredit.logoKey,
          onTap: _toggle,
          child: _Logo(size: widget.size),
        ),
      ),
    );
    return PopScope(
      canPop: !_portal.isShowing,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _close();
      },
      child: TapRegion(
        groupId: this,
        onTapOutside: (_) => _close(),
        child: CompositedTransformTarget(
          link: _link,
          child: OverlayPortal(
            controller: _portal,
            overlayChildBuilder: (context) => CompositedTransformFollower(
              link: _link,
              targetAnchor: Alignment(end ? 1 : -1, above ? -1 : 1),
              followerAnchor: Alignment(end ? 1 : -1, above ? 1 : -1),
              offset: Offset(0, above ? -kSpaceSm : kSpaceSm),
              child: Align(
                alignment: Alignment(end ? 1 : -1, above ? 1 : -1),
                child: TapRegion(
                  groupId: this,
                  child: _Panel(
                    dark: dark,
                    size: widget.size,
                    focusNode: _panelFocus,
                    onKey: _onPanelKey,
                    onTap: _activate,
                  ),
                ),
              ),
            ),
            child: logo,
          ),
        ),
      ),
    );
  }
}

class _Panel extends StatelessWidget {
  const _Panel({
    required this.dark,
    required this.size,
    required this.focusNode,
    required this.onKey,
    required this.onTap,
  });

  final bool dark;
  final double size;
  final FocusNode focusNode;
  final FocusOnKeyEventCallback onKey;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      link: true,
      label: kCreditText,
      excludeSemantics: true,
      onTap: onTap,
      child: Focus(
        focusNode: focusNode,
        onKeyEvent: onKey,
        child: MouseRegion(
          cursor: SystemMouseCursors.click,
          child: GestureDetector(
            key: KuhyCredit.panelKey,
            onTap: onTap,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: Color(dark ? kDarkSurface : kLightSurface),
                border: Border.all(
                  color: Color(dark ? kDarkBorder : kLightBorder),
                ),
                borderRadius: BorderRadius.circular(kRadius),
              ),
              child: Padding(
                padding: const EdgeInsets.all(kSpaceMd),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  spacing: kSpaceSm,
                  children: [
                    _Logo(size: size),
                    Text(
                      kCreditText,
                      textDirection: TextDirection.ltr,
                      style: TextStyle(
                        color: Color(dark ? kDarkText : kLightText),
                        fontSize: kTextBody,
                        decoration: TextDecoration.none,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Logo extends StatelessWidget {
  const _Logo({required this.size});

  final double size;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(size: Size.square(size), painter: const _LogoPainter());
  }
}

class _LogoPainter extends CustomPainter {
  const _LogoPainter();

  @override
  void paint(Canvas canvas, Size size) {
    canvas
      ..scale(size.width / kLogoSize)
      ..drawRect(
        const Rect.fromLTWH(0, 0, kLogoSize, kLogoSize),
        Paint()..color = const Color(kLogoField),
      );
    for (final (fill, points) in kLogoShapes) {
      final path = Path()..moveTo(points[0], points[1]);
      for (var i = 2; i < points.length; i += 2) {
        path.lineTo(points[i], points[i + 1]);
      }
      canvas.drawPath(path..close(), Paint()..color = Color(fill));
    }
  }

  @override
  bool shouldRepaint(_LogoPainter oldDelegate) => false;
}
