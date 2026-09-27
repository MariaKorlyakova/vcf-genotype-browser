from django import forms
from django.core.exceptions import ValidationError
from .models import Sample, Chromosome

class GenotypeSearchForm(forms.Form):
    chrom = forms.ModelChoiceField(queryset=Chromosome.objects.all(), empty_label="(Choose chromosome)")
    start = forms.IntegerField(label="Input start position", min_value=1)
    end = forms.IntegerField(label="Input end position", min_value=1)
    sample = forms.ModelChoiceField(queryset=Sample.objects.all(), empty_label="(All samples)", required=False)
    
    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start")
        end = cleaned_data.get("end")
        if start and end:
            if end < start:
                raise ValidationError("Start coordinate should be smaller or equal to end")