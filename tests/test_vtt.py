from yt_channel_transcriber.vtt import parse_vtt, timestamp_to_seconds


def test_parse_vtt():
    text = """WEBVTT\n\n00:00:01.000 --> 00:00:03.500\nHello\nworld\n\n00:00:04.000 --> 00:00:05.000\n<b>Next</b>\n"""
    segments = parse_vtt(text)
    assert len(segments) == 2
    assert segments[0].start == 1.0
    assert segments[0].duration == 2.5
    assert segments[0].text == "Hello world"
    assert segments[1].text == "Next"


def test_parse_short_timestamp():
    assert timestamp_to_seconds("01:02.500") == 62.5
