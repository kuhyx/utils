import 'package:data_transfer_flutter/data_transfer_flutter.dart';

/// Records what the facade asked the platform to do.
class FakePlatform implements DataTransferPlatform {
  /// What every save/share returns; false stands for a cancelled dialog.
  bool accept = true;

  /// What [pickText] returns; null stands for a cancelled picker.
  String? picked;

  /// `(fileName, text)` of every [saveText] call.
  final saves = <(String, String)>[];

  /// `(fileName, text)` of every [shareText] call.
  final shares = <(String, String)>[];

  @override
  Future<bool> saveText({
    required String fileName,
    required String text,
  }) async {
    saves.add((fileName, text));
    return accept;
  }

  @override
  Future<bool> shareText({
    required String fileName,
    required String text,
  }) async {
    shares.add((fileName, text));
    return accept;
  }

  @override
  Future<String?> pickText() async => picked;
}
