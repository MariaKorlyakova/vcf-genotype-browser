from django.db import models


class Genotype(models.Model):
    coordinate = models.ForeignKey(
        "Coordinate",
        on_delete=models.CASCADE,
    )
    sample = models.ForeignKey(
        "Sample",
        on_delete=models.CASCADE,
    )
    gt = models.TextField(null=True)
    phase_set = models.IntegerField(null=True)
    depth = models.IntegerField(null=True)
    allele_depth_all = models.TextField(null=True)
    allele_depth_nofilt = models.TextField(null=True)
    genotype_quality = models.IntegerField(null=True)
    qual = models.FloatField(null=True)
    filter = models.TextField(null=True)
    info = models.TextField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["coordinate", "sample"], name="unique_genotype"
            )
        ]
        ordering = ["coordinate__pos", "sample"]

    def __str__(self):
        return f"{self.sample} {self.coordinate}"


class Coordinate(models.Model):
    chromosome = models.ForeignKey(
        "Chromosome",
        on_delete=models.PROTECT,
    )
    pos = models.IntegerField()
    variant_id = models.TextField(null=True)
    ref = models.TextField()
    alt = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["chromosome", "pos", "ref", "alt"], name="unique_variant"
            )
        ]

    def __str__(self):
        return f"{self.chromosome}:{self.pos} {self.ref}>{self.alt}"


class Chromosome(models.Model):
    assembly = models.ForeignKey(
        "Assembly",
        on_delete=models.PROTECT,
    )
    name = models.TextField()
    length = models.IntegerField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["assembly", "name"], name="unique_chrom")
        ]

    def __str__(self):
        return self.name


class Assembly(models.Model):
    name = models.TextField(unique=True)

    def __str__(self):
        return self.name


class Sample(models.Model):
    name = models.TextField(unique=True)
    file_name = models.TextField()

    def __str__(self):
        return self.name
