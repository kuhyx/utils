extends GutTest
## Bundle folder names must stay importable by utils feedback_inbox, even when
## two saves land in the same millisecond.

const FeedbackSaver = preload("res://addons/dev_tools/feedback_saver.gd")
const TmpDir = preload("res://tests/tmp_dir.gd")

## Copied from feedback_inbox/feedback_inbox/_bundle.py (_STAMP): the only
## folder names the inbox imports.
const INBOX_STAMP := "^\\d{4}-\\d{2}-\\d{2}T\\d{2}-\\d{2}-\\d{2}-\\d{3}$"

var _root := TmpDir.path("feedback_saver")


func after_each() -> void:
	TmpDir.remove_tree(_root)


func test_same_millisecond_gives_two_inbox_names() -> void:
	var pattern := RegEx.create_from_string(INBOX_STAMP)
	var unix := 1760000000.123
	var first := FeedbackSaver.bundle_dir(_root, unix)
	DirAccess.make_dir_recursive_absolute(first)
	var second := FeedbackSaver.bundle_dir(_root, unix)
	assert_ne(first, second, "a clash must pick another folder")
	assert_not_null(pattern.search(first.get_file()), first)
	assert_not_null(pattern.search(second.get_file()), second)
