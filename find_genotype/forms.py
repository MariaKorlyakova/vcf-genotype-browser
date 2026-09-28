from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Min, Max

from .models import Chromosome, Sample


class ChromosomeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        if obj.first is None:
            return obj.name
        else:
            return f"{obj.name} ({obj.first:,} - {obj.last:,})"


class GenotypeSearchForm(forms.Form):
    chrom = ChromosomeChoiceField(
        queryset=Chromosome.objects.annotate(
            first=Min("coordinate__pos"), last=Max("coordinate__pos")
        ),
        empty_label="(Choose chromosome)",
    )
    start = forms.IntegerField(label="Input start position", min_value=1)
    end = forms.IntegerField(label="Input end position", min_value=1)
    sample = forms.ModelChoiceField(
        queryset=Sample.objects.all(), empty_label="(All samples)", required=False
    )

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start")
        end = cleaned_data.get("end")
        if start and end and end < start:
            raise ValidationError("Start coordinate should be smaller or equal to end")
