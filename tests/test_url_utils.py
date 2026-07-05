from src.common.url_utils import get_domain, get_host, normalize_url


def test_strips_tracking_params():
    url = "https://example.com/news/plant?utm_source=x&utm_medium=y&fbclid=abc&id=7"
    assert normalize_url(url) == "https://example.com/news/plant?id=7"


def test_removes_fragment_and_trailing_slash():
    assert normalize_url("https://example.com/a/b/#section") == "https://example.com/a/b"
    assert normalize_url("https://example.com/") == "https://example.com"


def test_lowercases_host_and_upgrades_http():
    assert normalize_url("http://Example.COM/Path") == "https://example.com/Path"


def test_dedupes_and_sorts_query_params():
    url = "https://example.com/p?b=2&a=1&b=2"
    assert normalize_url(url) == "https://example.com/p?a=1&b=2"


def test_identical_after_normalization():
    a = "https://www.georgia.org/press-release/x?utm_source=newsletter"
    b = "https://www.georgia.org/press-release/x/"
    assert normalize_url(a) == normalize_url(b)


def test_get_domain_and_host():
    assert get_domain("https://gov.georgia.gov/press/x") == "georgia.gov"
    assert get_host("https://Gov.Georgia.GOV/press/x") == "gov.georgia.gov"
