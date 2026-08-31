import random

from maica.reasoning.models import FactorLabel

from synthetic.generator import FactorKind, generate_diagnosis


def test_generated_ranks_are_contiguous_from_one() -> None:
    rng = random.Random(1)
    diagnosis, targets, specs = generate_diagnosis(rng, num_factors=5)

    assert [f.rank for f in diagnosis.factors] == [1, 2, 3, 4, 5]
    assert [t.factor_rank for t in targets] == [1, 2, 3, 4, 5]
    assert [s.rank for s in specs] == [1, 2, 3, 4, 5]


def test_target_citations_are_always_a_subset_of_supporting_ids() -> None:
    rng = random.Random(2)
    for num_factors in range(1, 11):
        diagnosis, targets, _specs = generate_diagnosis(rng, num_factors=num_factors)
        for factor, target in zip(diagnosis.factors, targets, strict=True):
            assert target.factor_rank == factor.rank
            assert set(target.cited_source_ids).issubset(set(factor.supporting_source_ids))


def test_change_factor_summary_matches_rules_py_shape() -> None:
    rng = random.Random(3)
    found_change = False
    for _ in range(50):
        diagnosis, _targets, specs = generate_diagnosis(rng, num_factors=1)
        spec = specs[0]
        if spec.kind is not FactorKind.CHANGE:
            continue
        found_change = True
        summary = diagnosis.factors[0].summary
        assert "changed from" in summary
        if spec.actor and spec.actor.strip().lower() == "system":
            assert "not a specific person" in summary
        if spec.context:
            assert f"context: {spec.context}" in summary
    assert found_change, "expected at least one CHANGE-kind factor across 50 draws"


def test_shared_value_factor_summary_matches_rules_py_shape() -> None:
    rng = random.Random(4)
    found_shared = False
    for _ in range(50):
        diagnosis, _targets, specs = generate_diagnosis(rng, num_factors=1)
        spec = specs[0]
        if spec.kind is not FactorKind.SHARED_VALUE:
            continue
        found_shared = True
        summary = diagnosis.factors[0].summary
        assert "Shares" in summary
        assert all(sid in summary for sid in spec.shared_ids)
    assert found_shared, "expected at least one SHARED_VALUE-kind factor across 50 draws"


def test_eval_mode_can_draw_eval_only_fields() -> None:
    rng = random.Random(5)
    seen_fields: set[str] = set()
    for _ in range(200):
        diagnosis, _targets, _specs = generate_diagnosis(rng, num_factors=1, eval_mode=True)
        summary = diagnosis.factors[0].summary
        if "exchange_rate" in summary or "tax_code" in summary:
            seen_fields.add("eval_only")
    assert seen_fields, "expected eval-only field names to appear when eval_mode=True"


def test_all_four_labels_are_reachable() -> None:
    rng = random.Random(6)
    seen_labels: set[FactorLabel] = set()
    for _ in range(200):
        diagnosis, _targets, _specs = generate_diagnosis(rng, num_factors=1)
        seen_labels.add(diagnosis.factors[0].label)
    assert seen_labels == set(FactorLabel)


def test_deterministic_given_same_seed() -> None:
    diagnosis_a, targets_a, _ = generate_diagnosis(random.Random(42), num_factors=4)
    diagnosis_b, targets_b, _ = generate_diagnosis(random.Random(42), num_factors=4)

    assert [f.summary for f in diagnosis_a.factors] == [f.summary for f in diagnosis_b.factors]
    assert [t.explanation for t in targets_a] == [t.explanation for t in targets_b]
