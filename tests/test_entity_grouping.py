from src.wiki_generation.group_records_by_entity import cluster_names, normalize_name


def test_normalize_name_strips_suffixes_and_punctuation():
    assert normalize_name("Ascend Elements, Inc.") == "ascend elements"
    assert normalize_name("Ascend Elements LLC") == "ascend elements"
    assert normalize_name("SK Battery America") == "sk battery america"


def test_cluster_merges_close_names():
    cluster_of, _ = cluster_names(["ascend elements", "ascend element"], 90, 80)
    assert cluster_of["ascend elements"] == cluster_of["ascend element"]


def test_cluster_keeps_distinct_names_apart():
    cluster_of, _ = cluster_names(["ascend elements", "sk battery america"], 90, 80)
    assert cluster_of["ascend elements"] != cluster_of["sk battery america"]


def test_near_miss_flagged_for_review():
    _, review_pairs = cluster_names(["hyundai mobis georgia", "hyundai mobis alabama"], 95, 70)
    assert review_pairs, "similar-but-under-threshold names should be flagged"


def test_conflicting_locations_downgrade_to_review_not_automerge():
    location_of = {"acme plant": "Jackson County", "acme plants": "Coweta County"}
    cluster_of, review_pairs = cluster_names(
        ["acme plant", "acme plants"], 90, 80, location_of=location_of
    )
    assert cluster_of["acme plant"] != cluster_of["acme plants"]
    assert review_pairs, "same name/high similarity but conflicting locations should be flagged"


def test_matching_or_missing_locations_still_automerge():
    location_of = {"acme plant": "Jackson County", "acme plants": ""}
    cluster_of, _ = cluster_names(["acme plant", "acme plants"], 90, 80, location_of=location_of)
    assert cluster_of["acme plant"] == cluster_of["acme plants"]


def test_reposted_duplicate_merges_by_name_not_source_url():
    # Two reposts of the same project from different source URLs (e.g. Hyundai
    # Mobis: gov.georgia.gov page_000013 and Savannah JDA page_000014) normalize
    # to one name + same county, so they cluster into a single entity — the merge
    # keys on entity+location, never on the differing source URL.
    location_of = {"hyundai mobis": "Bryan County"}
    cluster_of, review_pairs = cluster_names(
        ["hyundai mobis", "hyundai mobis"], 90, 80, location_of=location_of
    )
    assert len(set(cluster_of.values())) == 1
    assert not review_pairs
