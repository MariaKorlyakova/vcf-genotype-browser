from find_genotype.forms import GenotypeSearchForm


def test_end_before_start_is_rejected():
    form = GenotypeSearchForm(data={"start": 200, "end": 100})
    assert form.is_valid() is False
    assert (
        "Start coordinate should be smaller or equal to end" in form.non_field_errors()
    )
