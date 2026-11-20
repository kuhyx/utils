part of 'kuhy_credit.dart';

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
