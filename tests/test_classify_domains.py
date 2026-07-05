from src.common.config import load_settings
from src.url_processing.classify_domains import classify_priority


def _dp():
    return load_settings().domain_priority


def test_gov_is_high():
    assert classify_priority("https://gov.georgia.gov/press/x", _dp()) == "high"
    assert classify_priority("https://www.georgia.org/news", _dp()) == "high"


def test_news_is_medium():
    assert classify_priority("https://www.ajc.com/news/business/x", _dp()) == "medium"


def test_blog_is_low():
    assert classify_priority("https://foo.blogspot.com/2026/01/x.html", _dp()) == "low"


def test_social_is_skip():
    assert classify_priority("https://www.facebook.com/hyundaimetaplant", _dp()) == "skip"


def test_unknown_defaults_to_medium():
    assert classify_priority("https://some-unknown-site.example/x", _dp()) == "medium"
