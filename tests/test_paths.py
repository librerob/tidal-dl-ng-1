from pathlib import PureWindowsPath

from tidal_dl_ng.helper.path import check_media_exists, truncate_windows_stem


def test_windows_stems_fit_and_keep_distinct_names():
    directory = PureWindowsPath("C:/Music") / ("a" * 100)
    stem = "🎵" * 130
    first = truncate_windows_stem(directory, stem + "1", ".flac")
    second = truncate_windows_stem(directory, stem + "2", ".flac")
    assert first != second
    assert first == truncate_windows_stem(directory, stem + "1", ".flac")
    filename = directory / (first + ".flac")
    assert len(str(filename).encode("utf-16-le")) // 2 <= 259


def test_zero_byte_media_is_missing(tmp_path):
    filename = tmp_path / "track.flac"
    assert not check_media_exists(filename)
    filename.touch()
    assert not check_media_exists(filename)
    filename.write_bytes(b"audio")
    assert check_media_exists(filename)
