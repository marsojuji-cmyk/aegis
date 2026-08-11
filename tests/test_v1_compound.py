"""v1.1 compound engine + Intelligence Layer version surface."""

from aegis import __version__
from aegis.cli import main
from aegis.compound import compound_status, language_matrix
from aegis.doctor import doctor_report


def test_version_is_1_1():
    assert __version__.startswith("1.1.")


def test_compound_matrix_has_core_langs():
    langs = {r["lang"] for r in language_matrix()}
    for need in (
        "python",
        "javascript",
        "typescript",
        "tsx",
        "java",
        "kotlin",
        "go",
        "rust",
    ):
        assert need in langs


def test_compound_status_pipeline():
    st = compound_status()
    assert "preflight" in st["pipeline"]
    assert "router" in st["pipeline"]
    assert "cursor" in st["pipeline"]


def test_doctor_epoch_1_1():
    rep = doctor_report()
    assert rep["epoch"] == "1.1"
    assert str(rep.get("version", "")).startswith("1.1.")
    assert rep["ok"] is True


def test_cli_version_and_langs():
    assert main(["version"]) == 0
    assert main(["langs"]) == 0
