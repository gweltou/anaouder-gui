from src.utils import extract_metadata


def test_extract_metadata():
    cases = [
        ("", ("", {})),
        ("{?}", ("{?}", {})),
        ("Salud deoc'h", ("Salud deoc'h", {})),
        (" gant esaouennoù  ", ("gant esaouennoù", {})),
        (
            "{GDG}Komzoù liammet d'un anv",
            ("Komzoù liammet d'un anv", {"speaker": "GDG"}),
        ),
        ("{key:val }", ("", {"key": "val"})),
    ]

    for query, result in cases:
        assert extract_metadata(query) == result
