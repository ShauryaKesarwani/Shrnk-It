import 'package:flutter_test/flutter_test.dart';
import 'package:shrnk_it_mobile/domain/media.dart';

void main() {
  const items = [
    MediaItem(
      id: '1',
      name: 'Holiday.jpg',
      folder: 'Camera',
      sizeBytes: 100,
      isVideo: false,
    ),
    MediaItem(
      id: '2',
      name: 'holiday.mp4',
      folder: 'WhatsApp',
      sizeBytes: 500,
      isVideo: true,
    ),
    MediaItem(
      id: '3',
      name: 'cat.jpg',
      folder: 'Camera',
      sizeBytes: 200,
      isVideo: false,
    ),
  ];
  test(
    'searches names and folders case insensitively and orders largest first',
    () {
      expect(searchMedia(items, query: ' HOLIDAY ').map((e) => e.id), [
        '2',
        '1',
      ]);
      expect(searchMedia(items, query: 'camera').map((e) => e.id), ['3', '1']);
      expect(searchMedia(items, folder: 'Camera').map((e) => e.id), ['3', '1']);
    },
  );
  test('requires valid smaller output meeting threshold inclusively', () {
    expect(
      meetsSavingsThreshold(
        originalBytes: 100,
        outputBytes: 80,
        minimumPercent: 20,
      ),
      isTrue,
    );
    expect(
      meetsSavingsThreshold(
        originalBytes: 100,
        outputBytes: 81,
        minimumPercent: 20,
      ),
      isFalse,
    );
    expect(
      meetsSavingsThreshold(
        originalBytes: 100,
        outputBytes: 100,
        minimumPercent: 0,
      ),
      isFalse,
    );
    expect(
      meetsSavingsThreshold(
        originalBytes: 0,
        outputBytes: 1,
        minimumPercent: 20,
      ),
      isFalse,
    );
    expect(
      meetsSavingsThreshold(
        originalBytes: 100,
        outputBytes: 0,
        minimumPercent: 20,
      ),
      isFalse,
    );
    expect(
      meetsSavingsThreshold(
        originalBytes: 100,
        outputBytes: 10,
        minimumPercent: 101,
      ),
      isFalse,
    );
  });
}
