import json

from yt_channel_transcriber.issue_input import parse_event


def test_issue_form_parser(tmp_path):
    event = {
        "issue": {
            "body": "### YouTube channel\n\n@OpenAI\n\n### Number of videos\n\n20\n\n### Preferred languages\n\nde,en\n"
        }
    }
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event), encoding="utf-8")
    parsed = parse_event(path)
    assert parsed == {"channel": "@OpenAI", "limit": "20", "languages": "de,en"}


def test_issue_form_rejects_shell_payload(tmp_path):
    event = {
        "issue": {
            "body": "### YouTube channel\n\n@OpenAI\"; echo pwned\n\n### Number of videos\n\n20\n\n### Preferred languages\n\nde,en\n"
        }
    }
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event), encoding="utf-8")
    import pytest

    with pytest.raises(ValueError):
        parse_event(path)


def test_plain_handle_is_normalized():
    from yt_channel_transcriber.issue_input import validate_channel

    assert validate_channel("OpenAI") == "@OpenAI"
