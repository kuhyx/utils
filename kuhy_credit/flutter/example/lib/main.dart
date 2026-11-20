import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:kuhy_credit/kuhy_credit.dart';

/// Demo: an empty token-coloured screen with the credit in the bottom-right
/// corner, the spot an app's about screen would give it.
void main() {
  // Builds the semantics tree on web too, so screen readers and the E2E
  // find the logo by its name.
  WidgetsFlutterBinding.ensureInitialized();
  SemanticsBinding.instance.ensureSemantics();
  runApp(const CreditDemo());
}

/// The demo app.
class CreditDemo extends StatelessWidget {
  /// Creates the demo.
  const CreditDemo({super.key});

  @override
  Widget build(BuildContext context) {
    final dark = MediaQuery.platformBrightnessOf(context) == Brightness.dark;
    return WidgetsApp(
      color: Color(dark ? kDarkBg : kLightBg),
      pageRouteBuilder: <T>(settings, builder) => PageRouteBuilder<T>(
        settings: settings,
        pageBuilder: (context, _, _) => builder(context),
      ),
      home: ColoredBox(
        color: Color(dark ? kDarkBg : kLightBg),
        child: const SafeArea(
          child: Align(
            alignment: Alignment.bottomRight,
            child: Padding(padding: EdgeInsets.all(16), child: KuhyCredit()),
          ),
        ),
      ),
    );
  }
}
