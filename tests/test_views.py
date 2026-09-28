from pathlib import Path

import pytest
from django.core.management import call_command

from find_genotype.models import Chromosome, Sample

VCF = Path(__file__).parent / "data" / "sample.vcf"
VCF_002 = Path(__file__).parent / "data" / "sample_002.vcf"


@pytest.mark.django_db
def test_search_finds_genotypes(client):
    call_command("load_vcf", str(VCF))
    chrom_number = Chromosome.objects.get(name="chr1").pk
    response = client.get(
        "/genotypes/", {"chrom": chrom_number, "start": 783000, "end": 800000}
    )
    positions = [g.coordinate.pos for g in response.context["page"]]
    assert response.status_code == 200
    assert len(response.context["page"]) == 7
    assert 800046 not in positions
    assert 801142 not in positions
    assert 801143 not in positions


@pytest.mark.django_db
def test_sample_filter(client):
    call_command("load_vcf", str(VCF))
    call_command("load_vcf", str(VCF_002))
    chrom_number = Chromosome.objects.get(name="chr1").pk
    sample_number = Sample.objects.get(name="HG001").pk
    response_all = client.get(
        "/genotypes/", {"chrom": chrom_number, "start": 783000, "end": 800000}
    )
    assert len(response_all.context["page"]) == 14
    response_one = client.get(
        "/genotypes/",
        {
            "chrom": chrom_number,
            "start": 783000,
            "end": 800000,
            "sample": sample_number,
        },
    )
    assert len(response_one.context["page"]) == 7
    names = {g.sample.name for g in response_one.context["page"]}
    assert names == {"HG001"}
