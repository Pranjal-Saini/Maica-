"""Phrasing-variant banks and value pools for synthetic factor generation.

Field names and paraphrase templates are each split into a train set and an
eval-only set. Eval generation may draw from either; train generation only
draws from the train set. This means the eval set genuinely tests
generalization to unseen field names and phrasings, not just memorized
surface forms from training.
"""

from maica.reasoning.models import FactorLabel

TRAIN_FIELD_NAMES = [
    "account",
    "amount",
    "memo",
    "entity",
    "class",
    "department",
    "location",
    "posting_period",
]

# Reserved exclusively for eval generation — never sampled during train
# generation, so a model that only memorized train-time fields is exposed.
EVAL_ONLY_FIELD_NAMES = ["exchange_rate", "tax_code"]

FIELD_NAMES = TRAIN_FIELD_NAMES + EVAL_ONLY_FIELD_NAMES

VALUE_POOLS: dict[str, list[str]] = {
    "account": [
        "4000 - Revenue",
        "2100 - AP",
        "6000 - COGS",
        "1000 - Cash",
        "5000 - Payroll Expense",
        "2000 - AR",
    ],
    "amount": ["1500.00", "-1500.00", "2200.50", "900.00", "10.00", "375.25", "48210.00"],
    "memo": [
        "Monthly accrual",
        "Reversal",
        "Q1 invoice",
        "Correction",
        "Manual adjustment",
        "Auto-generated",
    ],
    "entity": ["Acme Corp", "Beta LLC", "Globex Inc", "Initech", "Umbrella Corp"],
    "class": ["Retail", "Wholesale", "Online", "Consulting"],
    "department": ["Sales", "Finance", "Operations", "Engineering"],
    "location": ["HQ", "Warehouse 1", "East Region", "West Region"],
    "posting_period": ["Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026"],
    "exchange_rate": ["1.0", "0.92", "1.35", "0.81"],
    "tax_code": ["VAT-STD", "VAT-ZERO", "GST-5", "EXEMPT"],
}

ACTOR_NAMES = ["jsmith", "mgarcia", "awong", "rpatel"]
CONTEXTS = ["UIF", "SCH", "UES", "SLT", "RST"]

# --- Certainty phrasing per label -------------------------------------------
# rules.py today only ever emits UNCERTAIN. These other three are synthesized
# so the narrator model has seen every label's tone at least once, in case a
# future ranking rule starts emitting them — the narrator must never
# strengthen or weaken the given label's confidence regardless.

CHANGE_CERTAINTY_TAIL: dict[FactorLabel, str] = {
    FactorLabel.CONFIRMED: "This change is directly confirmed by the record's own audit trail.",
    FactorLabel.LIKELY: (
        "This change closely precedes the issue and is a strong candidate, though "
        "not yet fully confirmed as the cause."
    ),
    FactorLabel.UNCERTAIN: (
        "A field change alone does not confirm it caused the outcome — check the "
        "timing against when this transaction posted and whether {field_name} "
        "affects downstream processing."
    ),
    FactorLabel.INSUFFICIENT_EVIDENCE: (
        "There isn't enough surrounding evidence to say whether this change is significant."
    ),
}

SHARED_VALUE_CERTAINTY_TAIL: dict[FactorLabel, str] = {
    FactorLabel.CONFIRMED: (
        "This shared value is directly confirmed across both records' stored data."
    ),
    FactorLabel.LIKELY: (
        "This shared value strongly suggests the records are related, though not "
        "yet fully confirmed."
    ),
    FactorLabel.UNCERTAIN: (
        "This is a correlation, not a confirmed cause — investigate whether "
        "something affecting this {field_name} value explains the issue."
    ),
    FactorLabel.INSUFFICIENT_EVIDENCE: (
        "There isn't enough evidence to say whether this shared value is meaningful."
    ),
}

# --- Paraphrase target templates --------------------------------------------
# {field_name}, {old_value}, {new_value}, {actor_clause}, {context_clause},
# {other_ids}, {certainty} are filled in by the generator.

CHANGE_PARAPHRASE_TEMPLATES_TRAIN = [
    "The {field_name} field moved from {old_value!r} to {new_value!r}{actor_clause}"
    "{context_clause}. {certainty}",
    "{field_name} was updated from {old_value!r} to {new_value!r}{actor_clause}"
    "{context_clause} — {certainty_lower}",
    "A change to {field_name} (from {old_value!r} to {new_value!r}) was recorded"
    "{actor_clause}{context_clause}. {certainty}",
]

CHANGE_PARAPHRASE_TEMPLATES_EVAL_ONLY = [
    "Between {old_value!r} and {new_value!r} is the shift seen in {field_name}"
    "{actor_clause}{context_clause}; {certainty_lower}",
]

SHARED_VALUE_PARAPHRASE_TEMPLATES_TRAIN = [
    "This record shares {field_name} = {new_value!r} with {other_ids}. {certainty}",
    "Records {other_ids} also have {field_name} set to {new_value!r} — {certainty_lower}",
    "The same {field_name} value ({new_value!r}) appears on {other_ids}, worth "
    "checking. {certainty}",
]

SHARED_VALUE_PARAPHRASE_TEMPLATES_EVAL_ONLY = [
    "{other_ids} line up with this record on {field_name} = {new_value!r}; {certainty_lower}",
]
