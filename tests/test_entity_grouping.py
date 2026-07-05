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
