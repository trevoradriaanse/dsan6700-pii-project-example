from needtoknow.detectors import RegexDetector


def found(text):
    return {(s.label, s.text) for s in RegexDetector().detect(text)}


def test_shapes_it_should_find():
    got = found("Call (202) 555-0143 or write maria@example.com. SSN 123-45-6789, account 004417829931, "
                "due 03/01/2026, see https://example.com/lease, at 1450 Oak Street, Arlington, VA 22201.")
    assert ("private_phone", "(202) 555-0143") in got
    assert ("private_email", "maria@example.com") in got
    assert ("account_number", "123-45-6789") in got
    assert ("account_number", "004417829931") in got
    assert ("private_date", "03/01/2026") in got
    assert ("private_url", "https://example.com/lease") in got
    assert any(label == "private_address" and text.startswith("1450 Oak Street") for label, text in got)


def test_masked_ssn_counts():
    assert ("account_number", "XXX-XX-6741") in found("SSN: XXX-XX-6741")


def test_it_leaves_ordinary_numbers_alone():
    assert found("Rent is $1,850 per month for 12 months in 2026.") == set()


def test_names_are_out_of_reach_for_a_baseline():
    # The baseline has no idea what a name is: this is the gap a model has to close.
    assert not any(label == "private_person" for label, _ in found("Tenant: Maria Delgado"))
