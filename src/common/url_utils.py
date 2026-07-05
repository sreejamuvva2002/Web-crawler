"""URL normalization (the spec's exact rules) and domain extraction."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import tldextract

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}

# suffix_list_urls=() -> use the bundled public-suffix snapshot, never the network
_extractor = tldextract.TLDExtract(suffix_list_urls=())


def normalize_url(url: str) -> str:
    """Normalize for dedup identity: strip tracking params, lowercase host, drop
    fragment, drop unnecessary trailing slash, standardize on https, dedupe and
    sort query params. The original URL is kept elsewhere for crawling."""
    url = url.strip()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    scheme, netloc, path, query, _fragment = urlsplit(url)

    scheme = "https" if scheme in ("http", "https") else scheme
    netloc = netloc.lower()
    if netloc.endswith(":443") or netloc.endswith(":80"):
        netloc = netloc.rsplit(":", 1)[0]

    seen = set()
    params = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        if key.lower() in TRACKING_PARAMS or (key, value) in seen:
            continue
        seen.add((key, value))
        params.append((key, value))
    query = urlencode(sorted(params))

    if path != "/":
        path = path.rstrip("/")
    else:
        path = ""

    return urlunsplit((scheme, netloc, path, query, ""))


def get_domain(url: str) -> str:
    """Registered domain (example.com), falling back to the raw host."""
    host = urlsplit(url if "://" in url else "https://" + url).netloc.lower()
    host = host.split(":")[0]
    ext = _extractor(host)
    # attribute renamed across tldextract versions
    registered = getattr(ext, "top_domain_under_public_suffix", None) or getattr(
        ext, "registered_domain", None
    )
    return registered or host


def get_host(url: str) -> str:
    """Full lowercased hostname (sub.example.com), used for site-pattern matching."""
    host = urlsplit(url if "://" in url else "https://" + url).netloc.lower()
    return host.split(":")[0]
