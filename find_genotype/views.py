from django.core.paginator import Paginator
from django.shortcuts import render

from .forms import GenotypeSearchForm
from .models import Genotype


def genotype_search(request):
    form = GenotypeSearchForm(request.GET or None)
    page = None
    if form.is_valid():
        data = form.cleaned_data
        genotypes = Genotype.objects.select_related(
            "coordinate__chromosome", "sample"
        ).filter(
            coordinate__pos__range=(data["start"], data["end"]),
            coordinate__chromosome=data["chrom"],
        )
        if data["sample"] is not None:
            genotypes = genotypes.filter(sample=data["sample"])
        paginator = Paginator(genotypes, 50)
        page = paginator.get_page(request.GET.get("page"))
    return render(
        request, "find_genotype/genotype_search.html", {"page": page, "form": form}
    )
