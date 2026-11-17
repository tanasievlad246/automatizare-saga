import sqlite3

import pytest

from efactura.errors import EfacturaError
from efactura.store import Store

from helpers import OTHER_VALID_CUI, VALID_CUI, make_row


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data" / "efactura.db")
    yield s
    s.close()


def test_existing_ids_reports_only_saved_messages(store):
    store.insert_message(make_row(id="3001"))

    assert store.existing_ids(["3001", "3002"]) == {"3001"}


def test_existing_ids_handles_more_ids_than_one_query_allows(store):
    store.insert_message(make_row(id="7"))

    assert store.existing_ids(str(n) for n in range(5000)) == {"7"}


def test_same_message_id_cannot_be_saved_twice(store):
    store.insert_message(make_row(id="3001"))

    with pytest.raises(sqlite3.IntegrityError):
        store.insert_message(make_row(id="3001", invoice_number="OTHER"))

    assert len(store.list_messages()) == 1


def test_upload_flag_starts_cleared(store):
    store.insert_message(make_row())

    saved = store.get_message("3001")

    assert saved["uploaded_to_accounting"] is False
    assert saved["uploaded_at"] is None


def test_marking_uploaded_sets_flag_and_time(store):
    store.insert_message(make_row())

    store.set_uploaded(["3001"], True, "2026-11-11T10:00:00+02:00")

    saved = store.get_message("3001")
    assert saved["uploaded_to_accounting"] is True
    assert saved["uploaded_at"] == "2026-11-11T10:00:00+02:00"


def test_undoing_clears_flag_and_time(store):
    store.insert_message(make_row())
    store.set_uploaded(["3001"], True, "2026-11-11T10:00:00+02:00")

    store.set_uploaded(["3001"], False, "2026-11-11T11:00:00+02:00")

    saved = store.get_message("3001")
    assert saved["uploaded_to_accounting"] is False
    assert saved["uploaded_at"] is None


def test_marking_an_unknown_id_changes_nothing(store):
    store.insert_message(make_row(id="3001"))

    with pytest.raises(EfacturaError) as info:
        store.set_uploaded(["3001", "9999"], True, "2026-11-11T10:00:00+02:00")

    assert info.value.code == "not_found"
    assert "9999" in info.value.message
    assert store.get_message("3001")["uploaded_to_accounting"] is False


def test_listing_leaves_out_xml_bodies(store):
    store.insert_message(make_row())

    (listed,) = store.list_messages()

    assert "invoice_xml" not in listed
    assert "signature_xml" not in listed
    assert listed["invoice_number"] == "FV-1042"


def test_single_message_includes_xml_only_on_request(store):
    store.insert_message(make_row())

    assert "invoice_xml" not in store.get_message("3001")
    with_xml = store.get_message("3001", include_xml=True)
    assert with_xml["invoice_xml"] == "<Invoice/>"
    assert with_xml["signature_xml"] == "<Signature/>"


def test_unknown_message_is_none(store):
    assert store.get_message("nope") is None


def test_listing_filters_by_company(store):
    store.insert_message(make_row(id="1", cui=VALID_CUI))
    store.insert_message(make_row(id="2", cui=OTHER_VALID_CUI))

    assert [m["id"] for m in store.list_messages(cui=OTHER_VALID_CUI)] == ["2"]


def test_listing_pending_skips_uploaded(store):
    store.insert_message(make_row(id="1"))
    store.insert_message(make_row(id="2"))
    store.set_uploaded(["1"], True, "2026-11-11T10:00:00+02:00")

    assert [m["id"] for m in store.list_messages(pending=True)] == ["2"]


def test_listing_filters_by_message_type(store):
    store.insert_message(make_row(id="1", message_type="FACTURA PRIMITA"))
    store.insert_message(make_row(id="2", message_type="FACTURA TRIMISA"))
    store.insert_message(make_row(id="3", message_type="ERORI FACTURA"))

    assert [m["id"] for m in store.list_messages(type_prefix="FACTURA TRIMISA")] == ["2"]


def test_listing_since_a_date_uses_the_day_it_was_saved(store):
    store.insert_message(make_row(id="1", first_seen_at="2026-11-09T08:00:00+02:00"))
    store.insert_message(make_row(id="2", first_seen_at="2026-11-11T08:00:00+02:00"))

    assert [m["id"] for m in store.list_messages(since="2026-11-10")] == ["2"]


def test_listing_is_ordered_oldest_saved_first(store):
    store.insert_message(make_row(id="b", first_seen_at="2026-11-11T08:00:00+02:00"))
    store.insert_message(make_row(id="a", first_seen_at="2026-11-10T08:00:00+02:00"))

    assert [m["id"] for m in store.list_messages()] == ["a", "b"]


def test_finds_an_earlier_message_with_the_same_invoice(store):
    store.insert_message(make_row(id="1", invoice_number="FV-1", supplier_cui="87654321"))

    match = store.find_same_invoice(VALID_CUI, "FACTURA PRIMITA", "87654321", "FV-1")
    other_supplier = store.find_same_invoice(VALID_CUI, "FACTURA PRIMITA", "11111111", "FV-1")
    other_company = store.find_same_invoice(OTHER_VALID_CUI, "FACTURA PRIMITA", "87654321", "FV-1")

    assert match == "1"
    assert other_supplier is None
    assert other_company is None


def test_last_clean_run_ignores_failed_partial_and_other_companies(store):
    def run(cui, started, status):
        run_id = store.start_run(cui, 7, started)
        store.finish_run(
            run_id, started, listed=1, new=1, failed=0, status=status,
            advances_coverage=(status == "ok"),
        )

    run(VALID_CUI, "2026-11-01T09:00:00+02:00", "ok")
    run(VALID_CUI, "2026-11-05T09:00:00+02:00", "partial")
    run(VALID_CUI, "2026-11-06T09:00:00+02:00", "error")
    run(OTHER_VALID_CUI, "2026-11-08T09:00:00+02:00", "ok")

    assert store.last_clean_run_start(VALID_CUI) == "2026-11-01T09:00:00+02:00"


def test_no_clean_run_yet_is_none(store):
    assert store.last_clean_run_start(VALID_CUI) is None


def test_run_log_records_counts_and_error(store):
    run_id = store.start_run(VALID_CUI, 7, "2026-11-11T09:00:00+02:00")
    store.finish_run(
        run_id, "2026-11-11T09:01:00+02:00", listed=12, new=3, failed=1,
        status="partial", error="1 message failed",
    )

    (run,) = store.runs()
    assert (run["cui"], run["window_days"], run["listed"], run["new"], run["failed"]) == (
        VALID_CUI, 7, 12, 3, 1,
    )
    assert run["status"] == "partial"
    assert run["error"] == "1 message failed"


def test_a_second_connection_can_read_while_the_first_is_open(tmp_path):
    path = tmp_path / "efactura.db"
    writer = Store(path)
    writer.insert_message(make_row())
    reader = Store(path)

    assert [m["id"] for m in reader.list_messages()] == ["3001"]

    writer.close()
    reader.close()


def test_clean_run_that_did_not_reach_back_to_the_previous_one_is_not_an_anchor(store):
    first = store.start_run(VALID_CUI, 7, "2026-10-01T09:00:00+02:00")
    store.finish_run(first, "2026-10-01T09:01:00+02:00", listed=0, new=0, failed=0,
                     status="ok", advances_coverage=True)
    short = store.start_run(VALID_CUI, 1, "2026-11-11T09:00:00+02:00")
    store.finish_run(short, "2026-11-11T09:01:00+02:00", listed=0, new=0, failed=0,
                     status="ok", advances_coverage=False)

    assert store.last_clean_run_start(VALID_CUI) == "2026-10-01T09:00:00+02:00"


# --- classification ------------------------------------------------------------------

V1_SCHEMA = """
CREATE TABLE sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cui TEXT NOT NULL, started_at TEXT NOT NULL,
    finished_at TEXT, window_days INTEGER NOT NULL, listed INTEGER, new INTEGER, failed INTEGER,
    status TEXT NOT NULL DEFAULT 'running', error TEXT, advances_coverage INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE messages (
    id TEXT PRIMARY KEY, cui TEXT NOT NULL, message_type TEXT NOT NULL, anaf_created_at TEXT,
    id_solicitare TEXT, detalii TEXT, invoice_number TEXT, invoice_issue_date TEXT,
    invoice_due_date TEXT, invoice_type_code TEXT, supplier_cui TEXT, supplier_name TEXT,
    customer_cui TEXT, customer_name TEXT, currency TEXT, total_without_vat TEXT, total_vat TEXT,
    total_payable TEXT, invoice_xml TEXT, signature_xml TEXT, raw_metadata_json TEXT NOT NULL,
    zip_sha256 TEXT, xml_path TEXT, first_seen_at TEXT NOT NULL,
    sync_run_id INTEGER REFERENCES sync_runs(id), possible_duplicate_of TEXT,
    uploaded_to_accounting INTEGER NOT NULL DEFAULT 0 CHECK (uploaded_to_accounting IN (0, 1)),
    uploaded_at TEXT
);
"""


def test_a_database_from_before_classification_gains_the_new_columns_and_keeps_its_rows(tmp_path):
    path = tmp_path / "efactura.db"
    old = sqlite3.connect(path)
    old.executescript(V1_SCHEMA)
    old.execute(
        "INSERT INTO messages (id, cui, message_type, raw_metadata_json, first_seen_at, "
        "uploaded_to_accounting) VALUES ('3001', ?, 'FACTURA PRIMITA', '{}', '2026-11-01', 1)",
        (VALID_CUI,),
    )
    old.commit()
    old.close()

    store = Store(path)
    row = store.get_message("3001")
    store.set_classification("3001", classification_status="classified", cont="628")
    reread = store.get_message("3001")
    store.close()

    assert row["uploaded_to_accounting"] is True
    assert row["classification_status"] is None and row["cont"] is None
    assert (reread["classification_status"], reread["cont"]) == ("classified", "628")


def test_opening_the_same_database_twice_is_harmless(tmp_path):
    Store(tmp_path / "efactura.db").close()
    Store(tmp_path / "efactura.db").close()


def test_a_message_saved_without_a_status_is_not_subject_to_classification(store):
    store.insert_message(make_row())

    assert store.get_message("3001")["classification_status"] is None
    assert store.pending_classification(VALID_CUI) == []


def test_pending_messages_are_listed_per_company_oldest_first(store):
    store.insert_message(make_row(id="2", classification_status="pending", first_seen_at="2026-11-11T10:00"))
    store.insert_message(make_row(id="1", classification_status="pending", first_seen_at="2026-11-11T09:00"))
    store.insert_message(make_row(id="3", classification_status="pending", cui=OTHER_VALID_CUI))
    store.insert_message(make_row(id="4", classification_status="review"))

    assert store.pending_classification(VALID_CUI) == ["1", "2"]


def test_classification_fields_are_saved_and_listed(store):
    store.insert_message(make_row(classification_status="pending"))

    store.set_classification(
        "3001", classification_status="review", suggested_cont="371", confidence=0.41,
        confidence_threshold=0.8, classification_reason="Jev confidence 0.41 is below 0.80",
    )

    (row,) = store.list_messages(classification="review")
    assert (row["suggested_cont"], row["confidence"], row["confidence_threshold"]) == ("371", 0.41, 0.8)
    assert store.list_messages(classification="classified") == []


def test_only_classification_fields_can_be_set_that_way(store):
    store.insert_message(make_row())

    with pytest.raises(ValueError):
        store.set_classification("3001", uploaded_to_accounting=1)


def test_classifying_an_unknown_message_is_not_found(store):
    with pytest.raises(EfacturaError) as info:
        store.set_classification("nope", cont="628")

    assert info.value.code == "not_found"


def test_the_confidence_level_is_kept_between_sessions(tmp_path):
    first = Store(tmp_path / "efactura.db")
    assert first.get_setting("min_confidence") is None
    first.set_setting("min_confidence", "0.9")
    first.set_setting("min_confidence", "0.75")
    first.close()

    second = Store(tmp_path / "efactura.db")
    assert second.get_setting("min_confidence") == "0.75"
    second.close()


def jev_call(store, message_id="3001", cost=0.00002, when="2026-11-11T09:30:00+02:00", error=None,
             cui=VALID_CUI, tokens=400):
    store.add_jev_call(
        message_id=message_id, cui=cui, called_at=when, model="typesafe/jev-1.14",
        request_json='{"model": "typesafe/jev-1.14"}',
        response_json='{"answers": {"cont": {"probabilities": {"628": 0.9}}}}',
        http_status=200 if error is None else 503, input_tokens=tokens, output_tokens=12,
        cost_usd=cost, duration_ms=180, error=error,
    )


def test_every_jev_call_is_kept_with_request_response_and_cost(store):
    jev_call(store)

    (call,) = store.jev_calls()
    assert call["message_id"] == "3001"
    assert call["request_json"] == '{"model": "typesafe/jev-1.14"}'
    assert '"probabilities"' in call["response_json"]
    assert (call["input_tokens"], call["output_tokens"], call["cost_usd"]) == (400, 12, 0.00002)
    assert (call["http_status"], call["duration_ms"], call["error"]) == (200, 180, None)


def test_the_latest_call_for_a_message_can_be_read_back(store):
    jev_call(store, when="2026-11-11T09:00:00+02:00", cost=0.1)
    jev_call(store, when="2026-11-11T10:00:00+02:00", cost=0.2)
    jev_call(store, message_id="other", when="2026-11-11T11:00:00+02:00")

    assert store.last_jev_call("3001")["cost_usd"] == 0.2
    assert store.last_jev_call("nobody") is None


def test_costs_add_up_calls_tokens_and_money(store):
    jev_call(store, message_id="1", cost=0.00002)
    jev_call(store, message_id="1", cost=None, error="HTTP 503", tokens=None)
    jev_call(store, message_id="2", cost=0.00004)

    costs = store.jev_costs()

    assert (costs["calls"], costs["failed_calls"], costs["invoices"]) == (3, 1, 2)
    assert costs["input_tokens"] == 800
    assert costs["cost_usd"] == pytest.approx(0.00006)


def test_costs_are_broken_down_by_month_and_can_be_narrowed(store):
    jev_call(store, message_id="1", when="2026-10-30T09:00:00+02:00", cost=0.5)
    jev_call(store, message_id="2", when="2026-11-02T09:00:00+02:00", cost=0.25)
    jev_call(store, message_id="3", when="2026-11-03T09:00:00+02:00", cost=0.25, cui=OTHER_VALID_CUI)

    assert [(m["period"], m["calls"], m["cost_usd"]) for m in store.jev_costs()["by_period"]] == [
        ("2026-10", 1, 0.5), ("2026-11", 2, 0.5),
    ]
    assert store.jev_costs(since="2026-11-01")["cost_usd"] == 0.5
    assert store.jev_costs(cui=OTHER_VALID_CUI)["calls"] == 1
    assert store.jev_costs(until="2026-11-02")["calls"] == 2  # the last day counts in full


@pytest.mark.parametrize("group, periods", [
    ("day", ["2026-10-30", "2026-11-02", "2026-11-03"]),
    ("week", ["2026-W44", "2026-W45"]),   # Friday 30 October; Monday 2 and Tuesday 3 November
    ("month", ["2026-10", "2026-11"]),
    ("year", ["2026"]),
])
def test_costs_can_be_grouped_by_day_week_month_or_year(store, group, periods):
    jev_call(store, message_id="1", when="2026-10-30T09:00:00+02:00")
    jev_call(store, message_id="2", when="2026-11-02T09:00:00+02:00")
    jev_call(store, message_id="3", when="2026-11-03T09:00:00+02:00")

    assert [p["period"] for p in store.jev_costs(group=group)["by_period"]] == periods


def test_an_invoice_asked_twice_in_a_period_counts_once(store):
    jev_call(store, message_id="1", when="2026-11-02T09:00:00+02:00", cost=0.1)
    jev_call(store, message_id="1", when="2026-11-03T09:00:00+02:00", cost=0.1)

    (november,) = store.jev_costs()["by_period"]
    assert (november["calls"], november["invoices"], november["cost_usd"]) == (2, 1, 0.2)


def test_costs_with_no_calls_are_zero_not_missing(store):
    costs = store.jev_costs()

    assert (costs["calls"], costs["cost_usd"], costs["input_tokens"], costs["by_period"]) == (0, 0, 0, [])


def test_a_successful_call_without_a_price_is_counted_apart(store):
    jev_call(store, cost=None)

    assert store.jev_costs()["calls_without_cost"] == 1


# --- accounts and rules ----------------------------------------------------------------


def test_a_new_database_starts_with_the_example_accounts_rules_and_question(store):
    assert set(store.accounts()) == {"6022", "626", "628"}
    assert [rule["name"] for rule in store.rules()] == ["combustibil", "telecom"]
    assert store.rules()[0]["keywords"] == ["motorina", "benzina", "gpl auto"]
    assert "cont" in store.get_setting("jev_instructions")


def test_examples_are_not_put_back_after_the_user_deletes_them(tmp_path):
    first = Store(tmp_path / "efactura.db")
    for cont in list(first.accounts()):
        first.delete_account(cont)
    for rule in first.rules():
        first.delete_rule(rule["id"])
    first.close()

    second = Store(tmp_path / "efactura.db")
    assert (second.accounts(), second.rules()) == ({}, [])
    second.close()


def test_an_account_can_be_added_changed_and_removed(store):
    store.save_account("302", "Materiale consumabile.")
    store.save_account("302", "Materiale consumabile si auxiliare.")

    assert store.accounts()["302"] == "Materiale consumabile si auxiliare."
    store.delete_account("302")
    assert "302" not in store.accounts()


def test_removing_an_unknown_account_or_rule_is_not_found(store):
    for action in (lambda: store.delete_account("999"), lambda: store.delete_rule(12345),
                   lambda: store.update_rule(12345, name="x")):
        with pytest.raises(EfacturaError) as info:
            action()
        assert info.value.code == "not_found"


def new_rule(store, name="chirie", **overrides):
    fields = {
        "name": name, "cont": "612", "keywords": [], "item_codes": [], "commodity_prefixes": [],
        "supplier_cuis": ["11112222"], "client_cui": None, "enabled": True,
    }
    return store.add_rule(**{**fields, **overrides})


def test_a_rule_is_stored_with_all_its_conditions_and_goes_last(store):
    rule_id = new_rule(store, keywords=["chirie", "inchiriere*"], client_cui=VALID_CUI)

    last = store.rules()[-1]
    assert last["id"] == rule_id
    assert (last["name"], last["cont"], last["client_cui"], last["enabled"]) == (
        "chirie", "612", VALID_CUI, True
    )
    assert (last["keywords"], last["supplier_cuis"]) == (["chirie", "inchiriere*"], ["11112222"])
    assert (last["item_codes"], last["commodity_prefixes"]) == ([], [])


def test_a_rule_can_be_changed_switched_off_and_removed(store):
    rule_id = new_rule(store)

    store.update_rule(rule_id, cont="6123", enabled=False, keywords=["chirie"])
    changed = next(rule for rule in store.rules() if rule["id"] == rule_id)
    store.delete_rule(rule_id)

    assert (changed["cont"], changed["enabled"], changed["keywords"]) == ("6123", False, ["chirie"])
    assert changed["supplier_cuis"] == ["11112222"]  # untouched fields stay
    assert rule_id not in [rule["id"] for rule in store.rules()]


def test_only_rule_fields_can_be_changed(store):
    rule_id = new_rule(store)

    with pytest.raises(ValueError):
        store.update_rule(rule_id, position=1)


def test_a_rule_can_be_moved_up_and_down_the_order(store):
    rule_id = new_rule(store)  # third, after the two examples

    store.move_rule(rule_id, up=True)
    assert [rule["name"] for rule in store.rules()] == ["combustibil", "chirie", "telecom"]
    store.move_rule(rule_id, up=True)
    store.move_rule(rule_id, up=True)  # already first: stays
    assert [rule["name"] for rule in store.rules()] == ["chirie", "combustibil", "telecom"]
    store.move_rule(rule_id, up=False)
    assert [rule["name"] for rule in store.rules()] == ["combustibil", "chirie", "telecom"]


# --- what proposed rules rest on -----------------------------------------------------------


def decided(store, message_id, method="jev", cont="302", subject="{}",
            at="2026-11-10T10:00:00+02:00", **row):
    """Save a received invoice that has been given an account."""
    store.insert_message(make_row(id=message_id, classification_status="pending", **row))
    store.set_classification(
        message_id, classification_status="classified", cont=cont, classification_method=method,
        classified_at=at, rule_subject=subject,
    )


def ids_of(rows):
    return [row["id"] for row in rows]


def test_invoices_decided_without_a_rule_are_listed_newest_decision_first(store):
    decided(store, "1", method="jev", at="2026-11-01T10:00:00+02:00")
    decided(store, "2", method="rules")
    decided(store, "3", method="human", at="2026-11-05T10:00:00+02:00", cui=OTHER_VALID_CUI,
            supplier_name="Alt Furnizor SRL")
    decided(store, "4", method="jev_accepted", at="2026-11-03T10:00:00+02:00")
    decided(store, "5", method="jev", subject=None)  # given its account before subjects were kept
    store.insert_message(make_row(id="6", classification_status="review"))

    rows = store.decided_without_rule()

    assert ids_of(rows) == ["3", "4", "1"]
    assert rows[0] == {
        "id": "3", "cui": OTHER_VALID_CUI, "cont": "302", "supplier_name": "Alt Furnizor SRL",
        "rule_subject": "{}",
    }


def test_decisions_from_before_a_date_are_left_out(store):
    decided(store, "1", at="2026-08-01T10:00:00+02:00")
    decided(store, "2", at="2026-11-01T10:00:00+02:00")

    assert ids_of(store.decided_without_rule(since="2026-09-01")) == ["2"]


def test_a_turned_down_proposal_stays_away_until_the_account_changes(store):
    decided(store, "1", cont="302")

    store.dismiss_suggestions(["1"])
    turned_down = store.decided_without_rule()
    state = store.suggestion_state("1")
    store.set_classification("1", cont="371")

    assert turned_down == []
    assert state == {"rule_subject": "{}", "suggestion_dismissed_for": "302"}
    assert ids_of(store.decided_without_rule()) == ["1"]


def test_turning_down_an_unknown_invoice_changes_nothing(store):
    decided(store, "1")

    with pytest.raises(EfacturaError) as info:
        store.dismiss_suggestions(["1", "nope"])

    assert info.value.code == "not_found"
    assert ids_of(store.decided_without_rule()) == ["1"]


def test_the_subjects_of_classified_invoices_are_read_with_their_accounts(store):
    decided(store, "1", cont="302", subject="A")
    decided(store, "2", cont="371", subject="B", method="rules", cui=OTHER_VALID_CUI)
    decided(store, "3", cont="302", subject="C", at="2026-08-01T10:00:00+02:00")
    decided(store, "4", subject=None)
    store.insert_message(make_row(id="5", classification_status="review"))

    assert sorted(store.classified_subjects()) == [("302", "A"), ("302", "C"), ("371", "B")]
    assert store.classified_subjects(since="2026-09-01", cui=OTHER_VALID_CUI) == [("371", "B")]


def test_the_subject_and_the_refusal_are_not_listed_with_a_message(store):
    decided(store, "1")

    assert "rule_subject" not in store.get_message("1")
    assert "suggestion_dismissed_for" not in store.list_messages()[0]


def test_a_database_from_before_proposed_rules_gains_their_columns(tmp_path):
    path = tmp_path / "efactura.db"
    old = sqlite3.connect(path)
    old.executescript(V1_SCHEMA)
    old.execute(
        "INSERT INTO messages (id, cui, message_type, raw_metadata_json, first_seen_at) "
        "VALUES ('3001', ?, 'FACTURA PRIMITA', '{}', '2026-11-01')",
        (VALID_CUI,),
    )
    old.commit()
    old.close()

    store = Store(path)
    state = store.suggestion_state("3001")
    unknown = store.suggestion_state("nope")
    store.close()

    assert state == {"rule_subject": None, "suggestion_dismissed_for": None}
    assert unknown is None


# --- found by the review of the screen -------------------------------------------------------


def test_listing_stays_fast_when_a_client_has_thousands_of_invoices(store):
    import time

    store.save_client(VALID_CUI, "Alfa", "2026-11-01")
    run = store.start_run(VALID_CUI, 7, "2026-11-01T09:00:00+02:00")
    rows = [make_row(id=str(n), sync_run_id=run, invoice_xml="<x>" + "y" * 2000 + "</x>") for n in range(4000)]
    columns = list(rows[0])
    store._conn.executemany(
        f"INSERT INTO messages ({', '.join(columns)}) VALUES ({', '.join(':' + c for c in columns)})", rows
    )
    store._conn.commit()

    started = time.monotonic()
    listed = store.list_messages(cui=VALID_CUI)
    (client,) = store.clients()
    took = time.monotonic() - started

    assert (len(listed), client["invoices"], client["new_count"]) == (4000, 4000, 4000)
    assert took < 1.5, f"listing 4000 invoices took {took:.1f}s"


def test_many_programs_opening_a_new_database_at_once_do_not_trip_over_each_other(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    def open_and_count(path):
        opened = Store(path)
        try:
            return len(opened.rules()), len(opened.accounts())
        finally:
            opened.close()

    for attempt in range(8):
        path = tmp_path / f"fresh-{attempt}.db"
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(open_and_count, [path] * 6))
        assert results[-1] == (2, 3), results
        final = Store(path)
        assert (len(final.rules()), len(final.accounts())) == (2, 3)  # the examples once, not twice
        final.close()


def test_a_database_from_before_the_switch_gets_every_client_switched_on(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE clients (cui TEXT PRIMARY KEY, name TEXT NOT NULL, added_at TEXT NOT NULL)")
    old.execute("INSERT INTO clients VALUES ('12345674', 'Alfa', '2026-11-01T09:00:00')")
    old.commit()
    old.close()

    store = Store(path)

    assert [c["enabled"] for c in store.clients()] == [True]
    assert store.client_switch_counts() == (1, 0)


def test_a_database_from_before_per_line_gets_every_client_classified_line_by_line(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE clients (cui TEXT PRIMARY KEY, name TEXT NOT NULL, added_at TEXT NOT NULL, "
        "enabled INTEGER NOT NULL DEFAULT 1)"
    )
    old.execute("INSERT INTO clients VALUES ('12345674', 'Alfa', '2026-11-01T09:00:00', 0)")
    old.commit()
    old.close()

    store = Store(path)

    assert [(c["enabled"], c["per_line"]) for c in store.clients()] == [(False, True)]
    assert store.client_per_line("12345674") is True
    store.close()


def test_a_company_that_is_not_in_the_client_list_keeps_one_account_per_invoice(tmp_path):
    # Such a company is downloaded "as before" (README); it has no switch to turn.
    store = Store(tmp_path / "new.db")

    assert store.client_per_line("12345674") is False
    store.close()


# --- the files written for SAGA -----------------------------------------------------


def classified(store, message_id, cont="628", **row):
    store.insert_message(make_row(id=message_id, **row))
    store.set_classification(message_id, classification_status="classified", cont=cont)


def test_waiting_for_saga_are_the_classified_invoices_not_yet_imported_oldest_first(store):
    classified(store, "3002", first_seen_at="2026-11-11T10:00:00+02:00")
    classified(store, "3001", first_seen_at="2026-11-11T09:00:00+02:00", cont="6022")
    classified(store, "3003")
    store.set_uploaded(["3003"], True, "2026-11-12T08:00:00+02:00")
    store.insert_message(make_row(id="3004"))  # no account yet
    classified(store, "3005", cui=OTHER_VALID_CUI)

    waiting = store.waiting_for_saga(VALID_CUI)

    assert [(row["id"], row["cont"]) for row in waiting] == [("3001", "6022"), ("3002", "628")]
    assert waiting[0]["invoice_xml"] == "<Invoice/>" and waiting[0]["id_solicitare"] == "5001"


def test_placing_invoices_in_files_clears_the_clients_other_rows_only(store):
    classified(store, "3001")
    classified(store, "3002")
    classified(store, "3003", cui=OTHER_VALID_CUI)
    for message_id in ("3002", "3003"):
        store.set_classification(message_id, saga_xml_path=f"old/{message_id}.xml")

    store.place_in_saga_files(VALID_CUI, {"3001": "SAGA Import/a.xml"}, "2026-11-12T10:00:00+02:00")

    paths = {i: store.get_message(i)["saga_xml_path"] for i in ("3001", "3002", "3003")}
    assert paths == {"3001": "SAGA Import/a.xml", "3002": None, "3003": "old/3003.xml"}


def test_a_path_only_an_invoice_remembered_goes_on_record_before_the_invoice_forgets_it(store):
    # An earlier version kept each file's path on its invoice and nowhere else.
    classified(store, "3001")
    store.set_classification("3001", saga_xml_path="SAGA Import/earlier.xml")
    store.note_saga_file("SAGA Import/known.xml", VALID_CUI, "2026-11-11T09:00:00+02:00")

    store.place_in_saga_files(VALID_CUI, {}, "2026-11-12T10:00:00+02:00")

    assert store.get_message("3001")["saga_xml_path"] is None
    assert store.saga_ledger(VALID_CUI) == {
        "SAGA Import/earlier.xml": "2026-11-12T10:00:00+02:00",
        "SAGA Import/known.xml": "2026-11-11T09:00:00+02:00",  # its own time is kept
    }


def test_the_ledger_knows_every_file_the_program_wrote_for_a_client(store):
    classified(store, "3001")
    store.set_classification("3001", saga_xml_path="SAGA Import/from-an-earlier-version.xml")
    store.note_saga_file("SAGA Import/b.xml", VALID_CUI, "2026-11-11T09:30:00+02:00")
    store.note_saga_file("SAGA Import/other.xml", OTHER_VALID_CUI, "2026-11-11T09:30:00+02:00")

    assert store.saga_ledger(VALID_CUI) == {
        "SAGA Import/from-an-earlier-version.xml": None,
        "SAGA Import/b.xml": "2026-11-11T09:30:00+02:00",
    }

    store.note_saga_file("SAGA Import/b.xml", VALID_CUI, "2026-11-12T10:00:00+02:00")  # written again
    store.set_classification("3001", saga_xml_path=None)
    store.forget_saga_file("SAGA Import/from-an-earlier-version.xml")

    assert store.saga_ledger(VALID_CUI) == {"SAGA Import/b.xml": "2026-11-12T10:00:00+02:00"}


def test_clients_with_saga_files_are_those_with_invoices_waiting_or_files_left(store):
    classified(store, "3001")
    store.insert_message(make_row(id="3002", cui=OTHER_VALID_CUI))  # nothing for SAGA
    store.note_saga_file("SAGA Import/left.xml", "18547290", "2026-11-11T09:30:00+02:00")
    store.set_saga_problem("27845391", "PermissionError: the file is open", "2026-11-11T09:30:00+02:00")

    assert store.clients_with_saga_files() == ["12345674", "18547290", "27845391"]


def test_the_companies_of_some_messages_are_found_however_many_are_asked_for(store):
    store.insert_message(make_row(id="3001"))
    store.insert_message(make_row(id="3002", cui=OTHER_VALID_CUI))

    assert store.cuis_of(["3001", "3002", "3001"]) == [VALID_CUI, OTHER_VALID_CUI]
    assert store.cuis_of(["3002", *(str(n) for n in range(3000))]) == [OTHER_VALID_CUI]  # more than one query holds
    assert store.cuis_of([]) == []


def test_a_saga_problem_is_kept_per_client_until_cleared(store):
    assert store.saga_problem(VALID_CUI) is None

    store.set_saga_problem(VALID_CUI, "PermissionError: the file is open", "2026-11-11T09:30:00+02:00")
    store.set_saga_problem(VALID_CUI, "PermissionError: still open", "2026-11-11T09:45:00+02:00")

    assert store.saga_problem(VALID_CUI) == {
        "message": "PermissionError: still open", "at": "2026-11-11T09:45:00+02:00"
    }
    assert store.saga_problem(OTHER_VALID_CUI) is None

    store.set_saga_problem(VALID_CUI, None, "2026-11-11T10:00:00+02:00")

    assert store.saga_problem(VALID_CUI) is None


# --- issued invoices in the process ------------------------------------------------------


def issued_row(message_id, **overrides):
    return make_row(id=message_id, message_type="FACTURA TRIMISA", supplier_cui=VALID_CUI,
                    customer_cui="87654321", customer_name="Beta Instal SRL", **overrides)


def test_issued_invoices_have_a_list_of_accounts_of_their_own(store):
    store.save_account("704", "Servicii prestate.", kind="issued")

    assert store.accounts(kind="issued")["704"] == "Servicii prestate."
    assert "704" not in store.accounts()
    store.delete_account("704", kind="issued")
    assert "704" not in store.accounts(kind="issued")


def test_a_new_database_starts_with_example_accounts_for_issued_invoices(store):
    assert list(store.accounts(kind="issued")) == ["701", "704", "707"]


def test_deleted_example_accounts_for_issued_invoices_do_not_come_back(tmp_path):
    path = tmp_path / "data" / "efactura.db"
    store = Store(path)
    for cont in ("701", "704", "707"):
        store.delete_account(cont, kind="issued")
    store.close()

    store = Store(path)
    assert store.accounts(kind="issued") == {}
    store.close()


def test_a_rule_is_for_received_invoices_unless_it_says_issued(store):
    received = store.add_rule(name="a", cont="628", keywords=["a"], client_cui=None, enabled=True)
    issued = store.add_rule(name="b", cont="704", keywords=["b"], client_cui=None, enabled=True, direction="issued")

    kinds = {rule["id"]: rule["direction"] for rule in store.rules()}
    assert (kinds[received], kinds[issued]) == ("received", "issued")


def test_a_rule_moves_only_among_the_rules_of_its_kind(store):
    first = store.add_rule(name="r1", cont="628", keywords=["a"], client_cui=None, enabled=True)
    sold = store.add_rule(name="i1", cont="704", keywords=["b"], client_cui=None, enabled=True, direction="issued")
    second = store.add_rule(name="r2", cont="626", keywords=["c"], client_cui=None, enabled=True)

    store.move_rule(second, up=True)  # passes over the issued one, before the received one above it

    received = [rule["id"] for rule in store.rules() if rule["direction"] == "received"]
    assert received[-2:] == [second, first]
    store.move_rule(sold, up=True)  # first among the issued ones already: it stays
    assert [rule["id"] for rule in store.rules() if rule["direction"] == "issued"] == [sold]


def test_issued_invoices_saved_before_they_were_classified_start_waiting_once(tmp_path):
    path = tmp_path / "data" / "efactura.db"
    store = Store(path)
    store.insert_message(issued_row("1"))
    store.insert_message(issued_row("2", invoice_number=None))  # ANAF's file could not be read as an invoice
    store.insert_message(issued_row("3"))
    store.set_uploaded(["3"], True, "2026-11-10T10:00:00")  # SAGA has it already
    store.insert_message(make_row(id="4"))  # a received one saved without classification stays so
    store.delete_setting("issued_backlog_added")  # as in a database of 0.10.0
    store.close()

    store = Store(path)
    assert {i: store.get_message(i)["classification_status"] for i in "1234"} == {
        "1": "pending", "2": None, "3": None, "4": None,
    }
    store.insert_message(issued_row("5"))
    store.close()

    store = Store(path)  # only once: an issued invoice saved outside classification later stays outside
    assert store.get_message("5")["classification_status"] is None
    store.close()


def test_proposed_rules_rest_on_received_invoices_only(store):
    subject = '{"supplier_cui": "87654321", "description": "Manopera"}'
    for message_id, row in (("1", make_row(id="1")), ("2", issued_row("2"))):
        store.insert_message(row)
        store.set_classification(message_id, classification_status="classified", cont="704",
                                 classification_method="jev", classified_at="2026-11-10T10:00:00",
                                 rule_subject=subject)

    assert [row["id"] for row in store.decided_without_rule()] == ["1"]
    assert len(store.classified_subjects()) == 1


def test_the_client_list_counts_received_and_issued_invoices_apart(store):
    store.save_client(VALID_CUI, "Alfa Construct SRL", "2026-11-01T09:00:00")
    run = store.start_run(VALID_CUI, 3, "2026-11-10T09:00:00")
    store.insert_message(make_row(id="1", sync_run_id=run))
    store.insert_message(issued_row("2", sync_run_id=run))
    store.insert_message(issued_row("3", sync_run_id=run))
    store.set_classification("3", classification_status="review")
    store.insert_message(issued_row("4", sync_run_id=run))
    store.set_classification("4", classification_status="classified", cont="704")

    (client,) = store.clients()
    assert {key: client[key] for key in (
        "invoices", "issued_count", "new_count", "issued_new_count", "review_count", "issued_review_count", "ready_count",
    )} == {"invoices": 1, "issued_count": 3, "new_count": 1, "issued_new_count": 3, "review_count": 1,
           "issued_review_count": 1, "ready_count": 1}


def test_an_issued_invoice_of_the_latest_download_that_brought_issued_ones_is_new(store):
    first = store.start_run(VALID_CUI, 3, "2026-11-09T09:00:00")
    store.insert_message(issued_row("1", sync_run_id=first))
    second = store.start_run(VALID_CUI, 3, "2026-11-10T09:00:00")
    store.insert_message(make_row(id="2", sync_run_id=second))  # this download brought no issued invoice

    shown = {row["id"]: row["is_new"] for row in store.list_messages(cui=VALID_CUI)}
    assert shown == {"1": True, "2": True}


def test_a_jev_call_about_an_issued_invoice_says_so_and_names_its_buyer(store):
    store.insert_message(issued_row("1"))
    store.add_jev_call(message_id="1", cui=VALID_CUI, called_at="2026-11-10T10:00:00", model="m", request_json="{}",
                       response_json=None, http_status=200, input_tokens=1, output_tokens=1, cost_usd=0.0001,
                       duration_ms=10, error=None)

    (call,) = store.jev_call_list()
    assert (call["message_type"], call["customer_name"]) == ("FACTURA TRIMISA", "Beta Instal SRL")


def test_new_alone_still_means_new_received_invoices_and_new_issued_ones_are_asked_for_by_kind(store):
    run = store.start_run(VALID_CUI, 3, "2026-11-10T09:00:00")
    store.insert_message(make_row(id="1", sync_run_id=run))
    store.insert_message(issued_row("2", sync_run_id=run))

    assert [row["id"] for row in store.list_messages(only_new=True)] == ["1"]
    assert [row["id"] for row in store.list_messages(only_new=True, type_prefix="FACTURA TRIMISA")] == ["2"]


def test_a_received_invoice_stays_new_when_the_latest_download_brought_only_issued_ones(store):
    first = store.start_run(VALID_CUI, 3, "2026-11-09T09:00:00")
    store.insert_message(make_row(id="1", sync_run_id=first))
    second = store.start_run(VALID_CUI, 3, "2026-11-10T09:00:00")
    store.insert_message(issued_row("2", sync_run_id=second))

    assert {row["id"]: row["is_new"] for row in store.list_messages()} == {"1": True, "2": True}


def test_only_issued_invoices_to_check_are_counted_as_issued_ones_to_check(store):
    store.save_client(VALID_CUI, "Alfa Construct SRL", "2026-11-01T09:00:00")
    store.insert_message(make_row(id="1"))
    store.set_classification("1", classification_status="review")
    store.insert_message(issued_row("2"))
    store.set_classification("2", classification_status="review")

    (client,) = store.clients()
    assert (client["review_count"], client["issued_review_count"]) == (2, 1)


def test_a_database_from_0_10_0_gets_issued_accounts_and_its_rules_stay_for_received_invoices(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE rules (id INTEGER PRIMARY KEY AUTOINCREMENT, position INTEGER NOT NULL, name TEXT NOT NULL,
            cont TEXT NOT NULL, keywords TEXT NOT NULL DEFAULT '[]', item_codes TEXT NOT NULL DEFAULT '[]',
            commodity_prefixes TEXT NOT NULL DEFAULT '[]', supplier_cuis TEXT NOT NULL DEFAULT '[]',
            client_cui TEXT, enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO rules (position, name, cont, keywords) VALUES (1, 'combustibil', '6022', '["motorina"]');
        INSERT INTO settings VALUES ('examples_added', '1');
    """)
    old.commit()
    old.close()

    store = Store(path)

    assert [(rule["name"], rule["direction"]) for rule in store.rules()] == [("combustibil", "received")]
    assert list(store.accounts(kind="issued")) == ["701", "704", "707"]
    assert store.accounts() == {}  # the examples for received invoices were added long ago, and removed
    store.close()
