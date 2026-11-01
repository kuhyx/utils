import 'dart:math' as math;

import 'package:design_system/src/tokens.dart';
import 'package:flutter/material.dart';

/// A grid of square cells that always fits its box, so it never scrolls
/// vertically.
///
/// Rows per page come from the height the parent gives it; the overflow moves
/// to further pages in a horizontal [PageView], marked by dots once there is
/// more than one. [itemBuilder] gets the global item index and must fill the
/// cell it is given: a square of up to column width plus [labelHeight], the
/// rows stretching to use up the leftover height.
class FitGrid extends StatefulWidget {
  /// Creates the grid.
  const FitGrid({
    required this.itemCount,
    required this.itemBuilder,
    this.columns = 3,
    this.labelHeight = 0,
    this.minSquare = 1,
    this.spacing = AppSpacing.sm,
    this.padding = const EdgeInsets.symmetric(horizontal: AppSpacing.md),
    super.key,
  });

  /// Number of items across all pages.
  final int itemCount;

  /// Builds item `index`, counted over all pages.
  final IndexedWidgetBuilder itemBuilder;

  /// Cells per row.
  final int columns;

  /// Height reserved under each square, for a caption.
  final double labelHeight;

  /// Least square side, as a fraction of the column width. Below 1 the
  /// builder may be given a cell too short for a full-width square, and must
  /// shrink its square to the cell height minus [labelHeight].
  final double minSquare;

  /// Gap between cells, both ways.
  final double spacing;

  /// Space around the cells.
  final EdgeInsets padding;

  @override
  State<FitGrid> createState() => _FitGridState();
}

const double _dotSize = AppSpacing.sm;
const double _dotsHeight = AppSpacing.md + AppSpacing.xs;

class _FitGridState extends State<FitGrid> {
  final _controller = PageController();
  var _page = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  int _rowsFor(double height, double cellHeight) => math.max(
    1,
    ((height + widget.spacing) / (cellHeight + widget.spacing)).floor(),
  );

  int _pagesFor(int perPage) =>
      math.max(1, (widget.itemCount / perPage).ceil());

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, box) {
      final w = widget;
      final inner = box.maxWidth - w.padding.horizontal;
      final cellW = (inner - w.spacing * (w.columns - 1)) / w.columns;
      final height = box.maxHeight - w.padding.vertical;
      final minCellH = cellW * w.minSquare + w.labelHeight;
      var rows = _rowsFor(height, minCellH);
      final pages = _pagesFor(rows * w.columns);
      if (pages > 1) {
        rows = _rowsFor(height - _dotsHeight, minCellH);
      }
      final perPage = rows * w.columns;
      final count = _pagesFor(perPage);
      final pageHeight = height - (count > 1 ? _dotsHeight : 0);
      final cellH = math.max(
        minCellH,
        (pageHeight + w.spacing) / rows - w.spacing,
      );
      return Column(
        children: [
          Expanded(
            child: PageView.builder(
              controller: _controller,
              itemCount: count,
              onPageChanged: (p) => setState(() => _page = p),
              itemBuilder: (context, p) => Padding(
                padding: w.padding,
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.topCenter,
                  child: _pageOf(
                    context,
                    p * perPage,
                    rows,
                    Size(cellW, cellH),
                  ),
                ),
              ),
            ),
          ),
          if (count > 1)
            _Dots(count: count, current: math.min(_page, count - 1)),
        ],
      );
    },
  );

  Widget _pageOf(BuildContext context, int first, int rows, Size cell) {
    final w = widget;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var r = 0; r < rows; r++) ...[
          if (r > 0) SizedBox(height: w.spacing),
          Row(
            children: [
              for (var c = 0; c < w.columns; c++) ...[
                if (c > 0) SizedBox(width: w.spacing),
                SizedBox.fromSize(
                  size: cell,
                  child: first + r * w.columns + c < w.itemCount
                      ? w.itemBuilder(context, first + r * w.columns + c)
                      : null,
                ),
              ],
            ],
          ),
        ],
      ],
    );
  }
}

class _Dots extends StatelessWidget {
  const _Dots({required this.count, required this.current});

  final int count;
  final int current;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ExcludeSemantics(
      child: SizedBox(
        height: _dotsHeight,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            for (var i = 0; i < count; i++)
              Container(
                key: ValueKey<String>('fit-grid-dot-$i'),
                width: _dotSize,
                height: _dotSize,
                margin: const EdgeInsets.symmetric(horizontal: AppSpacing.xs),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i == current ? scheme.primary : scheme.outlineVariant,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
