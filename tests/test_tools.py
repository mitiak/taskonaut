from taskrunner.tools import AddInput, EchoInput, add, echo


def test_echo_tool_returns_same_text() -> None:
    result = echo(EchoInput(text="abc"))
    assert result.text == "abc"


def test_add_tool_returns_sum() -> None:
    result = add(AddInput(a=2, b=3))
    assert result.sum == 5
