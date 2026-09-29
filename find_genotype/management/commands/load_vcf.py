import gzip
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, TextIO

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.db.models import Max, Min

from find_genotype.models import Assembly, Chromosome, Coordinate, Genotype, Sample


def dot_to_none(value: str, to_type: Callable = str) -> Any:
    if value == ".":
        return None
    return to_type(value)


def take_batch(iterator: Iterator, batch_size: int) -> list:
    batch = []
    for i in iterator:
        batch.append(i)
        if len(batch) == batch_size:
            return batch
    return batch


def parse_header_contig(line: str) -> dict[str, str]:
    line = line.removeprefix("##contig=<").removesuffix(">")
    fields = {}
    all_fields = line.split(",")
    for field in all_fields:
        fields[field.split("=", 1)[0]] = field.split("=", 1)[1]

    return fields


def open_vcf(path: Path) -> TextIO:
    if not path.is_file():
        raise CommandError(f"File {path} does not exist.")
    if path.suffix == ".gz":
        open_function = gzip.open
    else:
        open_function = open
    return open_function(path, "rt")


def parse_header(file: TextIO) -> tuple[dict[str, int | None], str, list[str], int]:
    chrom_lengths = {}
    assembly = ""
    samples = []
    line_counter = 0
    for line in file:
        if line.startswith("#"):
            line = line.rstrip("\n")
            line_counter += 1
            if line.startswith("##contig") and line:
                contig_fields = parse_header_contig(line)
                chrom = contig_fields.get("ID")
                length = (
                    int(contig_fields.get("length"))
                    if contig_fields.get("length")
                    else None
                )
                chrom_lengths[chrom] = length
                if assembly == "":
                    assembly = contig_fields.get("assembly")
            if line.startswith("#CHROM") and line:
                samples = line.split("\t")[9:]
                break
    return chrom_lengths, assembly, samples, line_counter


def iter_genotypes(
    file: TextIO, get_chrom: Callable, samples: list[Sample], line_counter: int
) -> Iterator[tuple[Coordinate, list[Genotype]]]:
    for line_number, line in enumerate(file, start=line_counter + 1):
        line = line.rstrip("\n")
        if not line.startswith("#") and line:
            columns = line.split("\t")
            if len(columns) != len(samples) + 9:
                raise CommandError(
                    f"Got {len(columns)} columns in line {line_number}, expected {len(samples) + 9}."
                )
            (
                chrom,
                pos,
                uid,
                ref,
                alt,
                qual,
                filt,
                info_raw,
                format_keys,
                *sample_cols,
            ) = columns
            pos = int(pos)
            qual_value = dot_to_none(qual, float)
            filter_value = dot_to_none(filt)
            info_value = dot_to_none(info_raw)
            coord = Coordinate(
                chromosome=get_chrom(chrom),
                pos=pos,
                variant_id=dot_to_none(uid),
                ref=ref,
                alt=alt,
            )
            genotypes = []
            for sample_obj, sample_col in zip(samples, sample_cols):
                parsed_format = dict(zip(format_keys.split(":"), sample_col.split(":")))
                gt_value = dot_to_none(parsed_format.get("GT", "."))
                ps = dot_to_none(parsed_format.get("PS", "."), int)
                dp = dot_to_none(parsed_format.get("DP", "."), int)
                adall = dot_to_none(parsed_format.get("ADALL", "."))
                ad = dot_to_none(parsed_format.get("AD", "."))
                gq = dot_to_none(parsed_format.get("GQ", "."), int)

                genotypes.append(
                    Genotype(
                        sample=sample_obj,
                        gt=gt_value,
                        phase_set=ps,
                        depth=dp,
                        allele_depth_all=adall,
                        allele_depth_nofilt=ad,
                        genotype_quality=gq,
                        qual=qual_value,
                        filter=filter_value,
                        info=info_value,
                    )
                )
            yield coord, genotypes


def save_coordinates_and_link(batch: list) -> list[Genotype]:
    coords_by_key = {}
    positions = set()
    chromosome_ids = set()
    for coord, genotypes in batch:
        key = (coord.chromosome_id, coord.pos, coord.ref, coord.alt)
        if key in coords_by_key:
            _, stored_genotypes = coords_by_key[key]
            stored_samples = {g.sample_id for g in stored_genotypes}
            for genotype in genotypes:
                if genotype.sample_id in stored_samples:
                    raise CommandError(
                        f"Duplicate record for sample {genotype.sample.name} at {coord.chromosome.name}:{coord.pos}."
                    )
            stored_genotypes.extend(genotypes)
        else:
            coords_by_key[key] = (coord, list(genotypes))
        positions.add(coord.pos)
        chromosome_ids.add(coord.chromosome_id)
    found_coords = Coordinate.objects.filter(
        chromosome_id__in=chromosome_ids, pos__in=positions
    )
    known_coords = {}
    for coord in found_coords:
        key = (coord.chromosome_id, coord.pos, coord.ref, coord.alt)
        known_coords[key] = coord
    to_create = []
    for key, (coord, genotypes) in coords_by_key.items():
        if key not in known_coords:
            to_create.append(coord)
            known_coords[key] = coord
    Coordinate.objects.bulk_create(to_create)
    linked_genotypes = []
    for key, (coord, genotypes) in coords_by_key.items():
        for genotype in genotypes:
            genotype.coordinate = known_coords[key]
            linked_genotypes.append(genotype)
    return linked_genotypes


class Command(BaseCommand):
    help = "Extract vcf file and pull it into Genotype model."

    def add_arguments(self, parser):
        parser.add_argument("path_to_vcf", help="Enter path to vcf file")
        parser.add_argument(
            "--assembly", default=None, help="Assembly name, e.g. GRCh38"
        )

    def handle(self, *args, **options) -> None:
        path_to_vcf = Path(options["path_to_vcf"])
        with open_vcf(path_to_vcf) as vcf:
            chrom_lengths, assembly, samples, line_counter = parse_header(vcf)
            if options["assembly"]:
                assembly = options["assembly"]
            if not assembly:
                assembly = "unknown"
            if len(samples) == 0:
                raise CommandError(f"File {path_to_vcf.name} has no sample columns.")
            with transaction.atomic():
                assembly_obj, _ = Assembly.objects.get_or_create(name=assembly)
                chrom_obj_dict = {}

                def get_chrom(name):
                    if name in chrom_obj_dict:
                        return chrom_obj_dict[name]
                    chrom_obj, _ = Chromosome.objects.get_or_create(
                        assembly=assembly_obj,
                        name=name,
                        defaults={"length": chrom_lengths.get(name)},
                    )
                    chrom_obj_dict[name] = chrom_obj
                    return chrom_obj

                sample_objs = []
                for sample_name in samples:
                    sample_obj, created_samp = Sample.objects.get_or_create(
                        name=sample_name, defaults={"file_name": path_to_vcf.name}
                    )
                    if not created_samp:
                        raise CommandError(
                            f"Sample {sample_name} is already in database."
                        )
                    sample_objs.append(sample_obj)
                gen_iter = iter_genotypes(vcf, get_chrom, sample_objs, line_counter)
                total_loaded = 0
                while True:
                    batch = take_batch(gen_iter, 3000)
                    if not batch:
                        break
                    genotypes = save_coordinates_and_link(batch)
                    try:
                        Genotype.objects.bulk_create(genotypes)
                    except IntegrityError:
                        raise CommandError(
                            "The file contains duplicate records, deduplicate it first."
                        )
                    total_loaded += len(genotypes)
                    self.stdout.write(f"Loaded {total_loaded}")
                for chrom_obj in chrom_obj_dict.values():
                    borders = Coordinate.objects.filter(chromosome=chrom_obj).aggregate(
                        first=Min("pos"), last=Max("pos")
                    )
                    chrom_obj.first_pos = borders["first"]
                    chrom_obj.last_pos = borders["last"]
                    chrom_obj.save()
            self.stdout.write(
                self.style.SUCCESS(f"All {total_loaded} genotypes loaded.")
            )
