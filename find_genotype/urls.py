from django.urls import path

from . import views

urlpatterns = [
    path("genotypes/", views.genotype_search, name="genotype_search"),
]
