from django.contrib import admin

from .models import Assembly, Chromosome, Coordinate, Genotype, Sample


@admin.register(Assembly)
class AssemblyAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ("name", "file_name")
    search_fields = ("name",)


@admin.register(Chromosome)
class ChromosomeAdmin(admin.ModelAdmin):
    list_display = ("name", "assembly", "length", "first_pos", "last_pos")
    list_filter = ("assembly",)


@admin.register(Coordinate)
class CoordinateAdmin(admin.ModelAdmin):
    list_display = ("chromosome", "pos", "ref", "alt")
    list_filter = ("chromosome",)


@admin.register(Genotype)
class GenotypeAdmin(admin.ModelAdmin):
    list_display = ("sample", "coordinate", "gt", "depth", "genotype_quality")
    list_select_related = ("sample", "coordinate__chromosome")
    show_full_result_count = False
