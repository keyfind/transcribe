from yt_channel_transcriber.exporters import to_plain_text, to_srt
from yt_channel_transcriber.models import Segment


def test_plain_text():
    assert to_plain_text([Segment(0, 1, "Hello"), Segment(1, 1.5, "World")]) == "Hello\nWorld\n"


def test_srt():
    result = to_srt([Segment(1.25, 2.5, "Hello &amp; world")])
    assert "00:00:01,250 --> 00:00:03,750" in result
    assert "Hello & world" in result
