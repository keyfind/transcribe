from yt_channel_transcriber.utils import channel_slug, normalize_channel, safe_filename


def test_normalize_handle():
    assert normalize_channel("@OpenAI") == "https://www.youtube.com/@OpenAI/videos"
    assert normalize_channel("OpenAI") == "https://www.youtube.com/@OpenAI/videos"


def test_channel_url():
    assert normalize_channel("https://www.youtube.com/@OpenAI") == "https://www.youtube.com/@OpenAI/videos"


def test_slug_and_filename():
    assert channel_slug("@My.Channel") == "my.channel"
    assert safe_filename("Hello: World / Test") == "hello-world-test"
