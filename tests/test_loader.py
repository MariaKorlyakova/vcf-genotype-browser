import gzip
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from find_genotype.models import Assembly, Chromosome, Coordinate, Genotype, Sample

VCF = Path(__file__).parent / "data" / "sample.vcf"
VCF_002 = Path(__file__).parent / "data" / "sample_002.vcf"
VCF_lowq = Path(__file__).parent / "data" / "sample_lowqual.vcf"
VCF_mult = Path(__file__).parent / "data" / "sample_multi.vcf"
VCF_shift = Path(__file__).parent / "data" / "sample_shifted.vcf"


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


@pytest.mark.django_db
def test_qual_and_filter_are_stored_per_sample():
    call_command("load_vcf", str(VCF))
    call_command("load_vcf", str(VCF_lowq))
    filter_hg001 = set(
        Genotype.objects.filter(sample__name="HG001").values_list("filter", flat=True)
    )
    filter_hg003 = set(
        Genotype.objects.filter(sample__name="HG003").values_list("filter", flat=True)
    )
    assert filter_hg001 == {"PASS"}
    assert filter_hg003 == {"LowQual"}


@pytest.mark.django_db
def test_gzipped_file_loads(tmp_path):
    VCF_gz = tmp_path / "sample.vcf.gz"
    with open(VCF, "r") as in_file, gzip.open(VCF_gz, "wt") as out_file:
        for line in in_file:
            out_file.write(line)
    call_command("load_vcf", str(VCF_gz))
    assert Assembly.objects.count() == 1
    assert Chromosome.objects.count() == 1
    assert Sample.objects.count() == 1
    assert Coordinate.objects.count() == 10
    assert Genotype.objects.count() == 10


@pytest.mark.django_db
def test_multi_sample_file_creates_genotype_per_sample():
    call_command("load_vcf", str(VCF_mult))
    assert Sample.objects.count() == 2
    assert Coordinate.objects.count() == 10
    assert Genotype.objects.count() == 20


@pytest.mark.django_db
def test_duplicate_record_is_rejected(tmp_path):
    VCF_dupl = tmp_path / "sample_duplicate.vcf"
    lines = VCF.read_text().splitlines(keepends=True)
    VCF_dupl.write_text("".join(lines + [lines[-1]]))
    with pytest.raises(CommandError, match="Duplicate record"):
        call_command("load_vcf", str(VCF_dupl))
    assert Coordinate.objects.count() == 0
    assert Sample.objects.count() == 0


@pytest.mark.django_db
def test_chromosome_position_range_is_stored():
    call_command("load_vcf", str(VCF))
    chrom = Chromosome.objects.get(name="chr1")
    assert chrom.first_pos == 783006
    assert chrom.last_pos == 801143
    call_command("load_vcf", str(VCF_shift))
    chrom = Chromosome.objects.get(name="chr1")
    assert chrom.first_pos == 783006
    assert chrom.last_pos == 1801143


def test_missing_file_is_rejected():
    with pytest.raises(CommandError, match="does not exist"):
        call_command("load_vcf", "no_such_file.vcf")
