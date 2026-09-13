import pytest
from reprobe.cli import main

def test_rejects_missing_model(tmp_path, capsys):
    repository = tmp_path / "repo"
    repository.mkdir()

    missing_model = tmp_path / "missing.gguf"

    with pytest.raises(SystemExit) as exc_info:
        main([
            "--model",
            str(missing_model),
            str(repository)
        ])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "model" in captured.err.lower()
    assert "does not exist" in captured.err.lower()
    assert str(missing_model) in captured.err
