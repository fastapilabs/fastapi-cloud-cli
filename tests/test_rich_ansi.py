from fastapi_cloud_cli.utils.rich_ansi import text_from_ansi


def test_text_from_ansi_preserves_newlines() -> None:
    assert text_from_ansi("").plain == ""
    assert text_from_ansi("\n").plain == "\n"
    assert text_from_ansi("\n\n").plain == "\n\n"
    assert text_from_ansi("Hello").plain == "Hello"
    assert text_from_ansi("Hello\n").plain == "Hello\n"
    assert text_from_ansi("Hello\n\n").plain == "Hello\n\n"
    assert text_from_ansi("Hello\n World").plain == "Hello\n World"
    assert text_from_ansi("Hello\n\n World").plain == "Hello\n\n World"
    assert text_from_ansi("Hello\n World\n").plain == "Hello\n World\n"


def test_text_from_ansi_handles_carriage_returns_per_line() -> None:
    assert text_from_ansi("start\rend").plain == "end"
    assert text_from_ansi("start\rend\n").plain == "end\n"
    assert text_from_ansi("one\rtwo\nthree").plain == "two\nthree"
    assert text_from_ansi("one\ntwo\rthree\n").plain == "one\nthree\n"
