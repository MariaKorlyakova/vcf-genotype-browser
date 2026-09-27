from django.shortcuts import render
from django.core.paginator import Paginator
from .models import Genotype
from .forms import GenotypeRequestForm

def find_genotype(request):
    form = GenotypeRequestForm(request.GET or None)
    page = None
    if form.is_valid():
        f = form.cleaned_data
        genotypes = Genotype.objects.select_related("coordinate__chromosome", "sample").filter(coordinate__pos__range=(f["start"], f["end"]), coordinate__chromosome=f["chrom"])
        if f["sample"] is not None:
            genotypes = genotypes.filter(sample=f["sample"])
        paginator = Paginator(genotypes, 50)
        page = paginator.get_page(request.GET.get("page"))
    return render(request, "find_genotype/find_genotype.html", {"page": page, "form": form})
    

