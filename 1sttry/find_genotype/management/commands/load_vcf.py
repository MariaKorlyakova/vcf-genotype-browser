from find_genotype.models import Sample, Chromosome, Assembly, Coordinate, Genotype
from django.core.management.base import BaseCommand, CommandError
from pathlib import Path
from django.db import transaction
import gzip

def dot_to_none(arg, to_type=str):
    if arg == ".":
        return None
    return to_type(arg)
    
def islice(iterator, batch_size):
    batch = []
    for i in iterator:
        batch.append(i)
        if len(batch) == batch_size:
            return batch
    return batch

def parse_header_contig(l):
    ##contig=<ID=chr1,length=248956422,assembly=human_GRCh38_no_alt_analysis_set.fasta>
    l = l.removeprefix("##contig=<").removesuffix(">")
    d = {}
    all_fields = l.split(",")
    for field in all_fields:
        d[field.split("=", 1)[0]] = field.split("=", 1)[1]

    return d

def open_vcf(path):
    if not path.is_file():
        raise CommandError(f"File {path} does not exist.")
    if path.suffix == ".gz":
        open_function = gzip.open
    else:
        open_function = open
    return open_function(path, "rt")

def parse_header(file):
    chrom_len_dict = {}
    assembly = ''
    samples = []
    for line in file:
        if line.startswith("#"):
            line = line.rstrip("\n")
            if line.startswith("##contig") and line:
                parsed_header = parse_header_contig(line)
                chrom = parsed_header.get("ID")
                length = int(parsed_header.get("length")) if parsed_header.get("length") else None
                chrom_len_dict[chrom] = length
                if assembly == '':
                    assembly = parsed_header.get("assembly")
            if line.startswith("#CHROM") and line:
                samples =  line.split("\t")[9:]
                break
    return chrom_len_dict, assembly, samples
        
        
def iter_genotypes(file, get_chrom, samples):
    for n, line in enumerate(file, start=1):
        line = line.rstrip("\n")
        if not line.startswith("#") and line:
            line_parsed = line.split("\t")
            if len(line_parsed) != len(samples) + 9:
                raise CommandError(f"Got {len(line_parsed)} columns in line {n}, expected {len(samples) + 9}.")
            chrom, pos, uid, ref, alt, qual, filt, inf, form, *sample_cols = line_parsed
            pos = int(pos)
            qual_value=dot_to_none(qual, float)
            filter_value=dot_to_none(filt)
            info_value=dot_to_none(inf)
            coord = Coordinate(chromosome=get_chrom(chrom), pos=pos, uid=dot_to_none(uid),
                             ref=ref, alt=alt)
            g_list = []
            for sample_obj, col in zip(samples, sample_cols):
                parsed_format = dict(zip(form.split(":"), col.split(":")))
                genot = dot_to_none(parsed_format.get("GT", "."))
                ps = dot_to_none(parsed_format.get("PS", "."), int)
                dp = dot_to_none(parsed_format.get("DP", "."), int)
                adall = dot_to_none(parsed_format.get("ADALL", "."))
                ad = dot_to_none(parsed_format.get("AD", "."))
                gq = dot_to_none(parsed_format.get("GQ", "."), int)

                g_list.append(Genotype(sample=sample_obj, gt=genot, phase_set=ps,
                            depth=dp, allel_depth_all=adall, allel_depth_nofilt=ad,
                            genotype_quality=gq, qual=qual_value, filter=filter_value, info=info_value))
            yield coord, g_list

def check_coord_presence(c_g_batch):
    coord_new = {}
    existing_pos = []
    chrom_of_exist_pos = set()
    for c, g in c_g_batch:
        key_new = (c.chromosome_id, c.pos, c.ref, c.alt)
        if key_new in coord_new:
            coord_new[key_new][1].extend(g)
        else:
            coord_new[key_new] = (c, list(g))
        existing_pos.append(c.pos)
        chrom_of_exist_pos.add(c.chromosome_id)
    coord_req = Coordinate.objects.filter(chromosome_id__in=chrom_of_exist_pos, pos__in=existing_pos)
    coord_old = {}
    for i in coord_req:
        key_old = (i.chromosome_id, i.pos, i.ref, i.alt)
        coord_old[key_old] = i
    to_create = []
    for key, value in coord_new.items():
        if not key in coord_old:
            to_create.append(value[0])
            coord_old[key] = value[0]
    Coordinate.objects.bulk_create(to_create)
    gen_list = []
    for key, value in coord_new.items():
        for gen in value[1]:
            gen.coordinate = coord_old[key]
            gen_list.append(gen)
    return gen_list
            
                    
class Command(BaseCommand):
    help = "Extract vcf file and pull it into Genotype model."
    
    def add_arguments(self, parser):
        parser.add_argument("path_to_vcf", help="Enter path to vcf file")
        parser.add_argument("--assembly", default=None, help="Assembly name, e.g. GRCh38")    
    def handle(self, *args, **options):
        path_to_vcf = Path(options["path_to_vcf"])
        with open_vcf(path_to_vcf) as vcf:
            chrom_len_d, assembly, samples = parse_header(vcf)
            if options["assembly"]:
                assembly = options["assembly"]
            if not assembly:
                assembly = "unknown"
            if len(samples) == 0:
                raise CommandError(f"File {path_to_vcf.name} has no sample columns.")
            with transaction.atomic():
                obj_asm, created_asm = Assembly.objects.get_or_create(assembly_uid=assembly)
                chrom_obj_dict = {}   
                for chrom, length in chrom_len_d.items():
                    obj_chr, created_chr = Chromosome.objects.get_or_create(assembly=obj_asm, chrom=chrom, defaults={"length": length})
                    chrom_obj_dict[chrom] = obj_chr
                def get_chrom(name):
                    if name in chrom_obj_dict:
                        return chrom_obj_dict[name]
                    obj_chr, created_chr = Chromosome.objects.get_or_create(assembly=obj_asm, chrom=name)
                    chrom_obj_dict[name] = obj_chr
                    return obj_chr 
                sample_objs = []
                for s in samples:
                    obj_samp, created_samp = Sample.objects.get_or_create(sample_uid=s, defaults={"file_name": path_to_vcf.name})
                    if not created_samp:
                        raise CommandError(f"Sample {s} is already in database.")
                    sample_objs.append(obj_samp)    
                gen_iter = iter_genotypes(vcf, get_chrom, sample_objs)
                total_add = 0
                while True:
                    batch_for_load = islice(gen_iter, 3000)
                    if not batch_for_load:
                        break
                    gen_list = check_coord_presence(batch_for_load)
                    Genotype.objects.bulk_create(gen_list)
                    total_add += len(gen_list)
                    self.stdout.write(f"Loaded {total_add}")
            self.stdout.write(self.style.SUCCESS(f"All {total_add} genotypes loaded."))