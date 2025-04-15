import argparse
import json
import logging
import pickle
import tqdm
import rdflib

from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import XSD, RDF, RDFS, SDO
from core.io.CacheManager import CacheManager
from core.io.ServerManager import ServerManager
from core.io.TqdmLoggingHandler import TqdmLoggingHandler


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

    g.parse("data/sphn100.ttl",format="turtle")

    # Parsing command line parameters and necessary configuration
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", help="JSON file configuring the program (triplestore address, ...)",
                        required=True, dest="conf_file_path")
    parser.add_argument("--max-rows", dest="max_rows", help="Max number of rows returned by the SPARQL endpoint",
                        required=True, type=int, default=10000)
    parser.add_argument("--cache-manager", help="CacheManager file for individuals to reconcile",
                        required=True, dest="cache_manager_file_path")
    parser.add_argument("--output", dest="output_dir", help="Base directory for output files", required=True)
    args = parser.parse_args()

    with open(args.conf_file_path, 'r') as configuration_file:
        configuration_parameters = json.load(configuration_file)

    similarity_links = {l["url"] for l in configuration_parameters["similarity-links"]}

    # Loading CacheManager for individuals to reconcile
    cache_manager = CacheManager()
    cache_manager.load_from_csv(args.cache_manager_file_path)
    max_ind_i = cache_manager.get_size() - 1

    # CacheManager for predicates
    predicates_cache_manager = CacheManager()

    # Logging parameters
    logger = logging.getLogger()
    tqdm_logging_handler = TqdmLoggingHandler()
    tqdm_logging_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s][%(levelname)s] %(message)s"))
    logger.addHandler(tqdm_logging_handler)
    logger.setLevel(logging.INFO)

    # Querying predicates and inverses
    logger.info("Querying predicates and inverses")
    predicates_inverses = {}

    squery1 = '''
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX sphn: <https://biomedit.ch/rdf/sphn-schema/sphn>

        SELECT DISTINCT ?e
        WHERE {
        ?en ?e ?o .
        FILTER(isIRI(?o))
        }
        '''

    qres1 = g.query(squery1)
    
    for p in tqdm.tqdm(qres1):
        p_i = predicates_cache_manager.get_element_index(p)

        if p_i not in predicates_inverses:
            predicates_inverses[p_i] = set()

        squery2 = '''
        PREFIX owl: <http://www.w3.org/2002/07/owl#> 
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX sphn: <https://biomedit.ch/rdf/sphn-schema/sphn>

        SELECT DISTINCT ?e
        WHERE {
        {{
            sphn:p owl:inverseOf ?e
        }}
        UNION
        {{
            ?e owl:inverseOf sphn:p
        }}
        }

        '''
        #Inverses
        inverses = g.query(squery2,initBindings={'p':URIRef(SPHN[p]),'p':URIRef(SPHN[p])})


        for p_inv in inverses:
            p_inv_i = predicates_cache_manager.get_element_index(p_inv)

            predicates_inverses[p_i].add(p_inv_i)

            if p_inv_i not in predicates_inverses:
                predicates_inverses[p_inv_i] = set()
            predicates_inverses[p_inv_i].add(p_i)

        # Symmetric predicates
        squery3 = '''
        PREFIX owl: <http://www.w3.org/2002/07/owl#> 
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX sphn: <https://biomedit.ch/rdf/sphn-schema/sphn>

        ASK
        {{
            sphn:p rdf:type owl:SymmentricProperty
        }}
        '''
        symmetric = bool(g.query(squery3,initBindings={'p':URIRef(SPHN[p])}))

        if symmetric:
            predicates_inverses[p_i].add(p_i)

    # Querying graph adjacency
    logger.info("Querying graph adjacency")

    graph_adjacency = dict()
    edges_number = 0
    for p_i in tqdm.tqdm(predicates_inverses):
        p = predicates_cache_manager.get_element_from_index(p_i)

        logger.info("Querying {} adjacency".format(p))
        squery4 = '''
        SELECT ?e1 ?e2
        WHERE
        {
        ?e1 sphn:p ?e2 .
        FILTER(isIRI(?e2))
        }
        '''
        triples = g.query(squery4,initBindings={'p':URIRef(SPHN[p])})

        logger.info("Processing {} adjacency".format(p))
        graph_adjacency[p_i] = dict()
        for n1, n2 in tqdm.tqdm(triples):
            n1_i = cache_manager.get_element_index(n1)
            n2_i = cache_manager.get_element_index(n2)

            if p not in similarity_links or n1_i > max_ind_i or n2_i > max_ind_i:
                if n1_i not in graph_adjacency[p_i]:
                    graph_adjacency[p_i][n1_i] = set()
                graph_adjacency[p_i][n1_i].add(n2_i)
                edges_number += 1

    # Saving RDF graph
    logger.info("Saving RDF graph")

    output_dir = args.output_dir
    if output_dir[-1] != "/":
        output_dir += "/"

    # Saving graph adjacency
    pickle.dump(graph_adjacency, open(output_dir + "rdf_graph_adjacency", "wb"))

    # Saving predicates inverses as CSV
    with open(output_dir + "predicates_inverses.csv", "w") as file:
        for p_i in predicates_inverses:
            p = predicates_cache_manager.get_element_from_index(p_i)

            inverses = "{"
            for p_inv_i in predicates_inverses[p_i]:
                inverses += predicates_cache_manager.get_element_from_index(p_inv_i) + " "
            inverses += "}"

            file.write(f"{p},{inverses}\n")

    # Saving predicates inverses as binary
    pickle.dump(predicates_inverses, open(output_dir + "predicates_inverses", "wb"))

    # Saving CacheManager for RDF nodes and RDF predicates
    cache_manager.save_to_csv(output_dir + "nodes_cachemanager.csv")
    predicates_cache_manager.save_to_csv(output_dir + "predicates_cachemanager.csv")

    # Saving statistics
    with open(output_dir + "graph_statistics.md", "w") as file:
        file.write("* Number of nodes: {}\n".format(cache_manager.get_size()))
        file.write("* Number of edges: {}\n".format(edges_number))
        file.write("* Number of predicates: {}\n".format(predicates_cache_manager.get_size()))


if __name__ == '__main__':
    main()
