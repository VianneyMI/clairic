import clairic


def test_package_docstring_states_it_is_unofficial() -> None:
    """Should state in the package docstring that the SDK is unofficial."""
    assert clairic.__doc__ is not None
    assert "Unofficial" in clairic.__doc__
