import argparse
import json
import logging
import pickle
import tqdm
import rdflib

from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import XSD, RDF, RDFS, SDO
from datetime import datetime
from core.io.CacheManager import CacheManager
from core.io.TqdmLoggingHandler import TqdmLoggingHandler

__author__ = "Pierre Monnin"


def main():
    g = Graph()

    SPHN = rdflib.Namespace('https://biomedit.ch/rdf/sphn-schema/sphn#')     
    OWL = rdflib.Namespace("http://www.w3.org/2002/07/owl#")

    g.bind('sphn',SPHN)
    g.bind('xsd',XSD)
    g.bind('rdf',RDF)
    g.bind('rdfs',RDFS)
    g.bind('sdo',SDO)
    g.bind('owl',OWL)

    g.parse("sphn100.ttl",format="turtle")
    
    
    # Parsing command line parameters and necessary configuration
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", help="JSON file configuring the program (triplestore address, ...)",
                        required=True, dest="conf_file_path")
    parser.add_argument("--max-rows", dest="max_rows", help="Max number of rows returned by the SPARQL endpoint",
                        required=True, type=int, default=10000)
    parser.add_argument("--output", dest="output_dir", help="Base directory for output files", required=True)
    args = parser.parse_args()

    with open(args.conf_file_path, 'r') as configuration_file:
        configuration_parameters = json.load(configuration_file)

    # Building and CacheManager object
    cache_manager = CacheManager()

    # Logging parameters
    logger = logging.getLogger()
    tqdm_logging_handler = TqdmLoggingHandler()
    tqdm_logging_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s][%(levelname)s] %(message)s"))
    logger.addHandler(tqdm_logging_handler) 
    logger.setLevel(logging.INFO)

    # Querying individuals
    logger.info("Querying individuals to reconcile")
    relations = set()

    for concept in configuration_parameters["individuals-classes"]:
        squery1 = '''
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX sphn: <https://biomedit.ch/rdf/sphn-schema/sphn>

        SELECT ?e
        WHERE {
        ?e rdf:type sphn:concept .
        }
        '''

        qres1 = g.query(squery1, initBindings={'concept': URIRef(SPHN[concept])})
        for ind in qres1:
            ind_i = cache_manager.get_element_index(ind)
            relations.add(ind_i)
    
    
    logger.info("Number of individuals to reconcile: " + str(len(relations)))


    data_set = {}
    for l in tqdm.tqdm(configuration_parameters["similarity-links"]):
        data_set[l["url"]] = set()

        for c1 in configuration_parameters["individuals-classes"]:
            for c2 in configuration_parameters["individuals-classes"]:

                logger.info("Querying {} links for {} / {} ".format(l["url"],c1,c2))

                ret_val = '''
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX sphn: <https://biomedit.ch/rdf/sphn-schema/sphn>

                SELECT ?e1 ?e2
                WHERE {
                ?e1 rdf:type sphn:c1 .
                ?e2 rdf:type sphn:c2 .
                ?e1 sphn:lurl ?e2 .
                }
                '''
                qres2 = g.query(ret_val, initBindings={'c1':URIRef(SPHN[c1]),'c2':URIRef(SPHN[c2]),'lurl':URIRef(l["url"])})
                for ind1, ind2 in qres2:
                    ind1_i = cache_manager.get_element_index(ind1)
                    ind2_i = cache_manager.get_element_index(ind2)
                    if not l["symmetry"] or (ind2_i,ind1_i) not in data_set[l["url"]]:
                        data_set[l["url"]].add((ind1_i,ind2_i))
    
    logger.info("Saving simset")

    output_dir = args.output_dir
    if output_dir[-1] != "/":
        output_dir += "/"

    cache_manager.save_to_csv(output_dir + "ind_cachemanager.csv")
    pickle.dump(data_set, open (output_dir + "ind_similaritylinks", "wb"))

    with open(output_dir + "ind_statistics.csv","w") as file:
        file.write("# Individuals to reconcile,{}\n".format(len(relations)))

        for l in configuration_parameters["similarity-links"]:
            file.write("# links {},{}\n".format(l["url"],len(data_set[l["url"]])))


if __name__ == '__main__':
    main()
