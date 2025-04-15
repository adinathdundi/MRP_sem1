#Example script
def convert_to_ttl(input_file, output_file):
    prefixes = """
@prefix sphn: <http://example.org/sphn#> .
@prefix d_labitems: <http://example.org/d_labitems#> .
@prefix patients: <http://example.org/patients#> .
"""
    with open(input_file, 'r') as infile, open(output_file, 'w') as outfile:
        outfile.write(prefixes)
        for line in infile:
            s, p, o = line.strip().split(',')
            if p == 'a':
                ttl_line = f'<{s}> a sphn:{o.split("#")[1]} .\n'
            elif p == 'sphn#hasCode':
                 ttl_line = f'<{s}> sphn:hasCode <{o}> .\n'
            elif p == 'sphn#hasLabTest':
                 ttl_line = f'<{s}> sphn:hasLabTest <{o}> .\n'
            elif p == 'sphn#hasSubjectPseudoIdentifier':
                 ttl_line = f'<{s}> sphn:hasSubjectPseudoIdentifier <{o}> .\n'
            else:
                ttl_line = f'<{s}> {p} <{o}> .\n'
            outfile.write(ttl_line)

input_txt_file = 'data/mgdb100.txt'
output_ttl_file = 'data/mgdb100.ttl'
convert_to_ttl(input_txt_file, output_ttl_file)