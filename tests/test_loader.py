from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from find_genotype.models import Assembly, Chromosome, Coordinate, Genotype, Sample

VCF = Path(__file__).parent / "data" / "sample.vcf"
VCF_002 = Path(__file__).parent / "data" / "sample_002.vcf"


@pytest.mark.django_db
def test_load_creates_expected_rows():
    call_command("load_vcf", str(VCF))
    assert Assembly.objects.count() == 1
    assert Chromosome.objects.count() == 1
    assert Sample.objects.count() == 1
    assert Coordinate.objects.count() == 10
    assert Genotype.objects.count() == 10


@pytest.mark.django_db
def test_second_sample_does_not_duplicate_coordinates():
    call_command("load_vcf", str(VCF))
    call_command("load_vcf", str(VCF_002))
    assert Coordinate.objects.count() == 10
    assert Genotype.objects.count() == 20
    assert Sample.objects.count() == 2


@pytest.mark.django_db
def test_prevention_of_re_uploading():
    call_command("load_vcf", str(VCF))
    with pytest.raises(CommandError, match="already in database."):
        call_command("load_vcf", str(VCF))
        assert Genotype.objects.count() == 10
        assert Sample.objects.count() == 1
