# -*- coding: utf-8 -*-
"""
Created on Mon Nov 23 17:10:36 2020

@author: KLEF
"""
import pathlib

import numpy as np
import scipy.interpolate
import networkx as nx
import pandas as pd
import shapely
import shapely.wkt


#%%
def find_closest_node(G, point):
    """
    Find the node on graph G that is closest to the given
    shapely.geometry.Point point

    Parameters
    ----------
    G : networkx.Graph
        The graph in which the closest node is to be found.
    point : shapely.geometry.Point
        The point for which the closest node is to be found.

    Returns
    -------
    name_node : TYPE
        DESCRIPTION.
    distance_node : TYPE
        DESCRIPTION.

    """
    distance = np.full((len(G.nodes)), fill_value=np.nan)
    for ii, n in enumerate(G.nodes):
        distance[ii] = point.distance(G.nodes[n]['geometry'])
    name_node = list(G.nodes)[np.argmin(distance)]
    distance_node = np.min(distance)
    return name_node, distance_node


#%%
def find_closest_edge(G, point):
    distance = np.full((len(G.edges)), fill_value=np.nan)
    for ii, e in enumerate(G.edges):
        #start_node = G.nodes[G.edges[e]['StartJunctionId']]
        #end_node = G.nodes[G.edges[e]['EndJunctionId']]
        #distance[ii] = point.distance()
        distance[ii] = point.hausdorff_distance(shapely.wkt.loads(G.edges[e]['Wkt']))
    name_edge = list(G.edges)[np.argmin(distance)]
    distance_edge = np.min(distance)
    return name_edge, distance_edge


#%%
def determine_max_draught_on_path(graph, origin, destination, lobith_discharge, underkeel_clearance = 0.30
):
    """
    compute
    """
    #TODO: the file "depth.csv" is missing... this should be loaded as discharge_df

    depth_path = pathlib.Path('~/data/vaarwegen/discharge/depth.csv')
    discharge_df = pd.read_csv(depth_path)

    # also return distance
    origin_node, _ = find_closest_node(graph, origin.geometry)
    destination_node, _ = find_closest_node(graph, destination.geometry)

    # determine path and route (subgraph)
    path = nx.dijkstra_path(graph, origin_node, destination_node, weight='Length')
    route = nx.DiGraph(graph.subgraph(path))

    # get the discharge interpolation functions
    discharge_df = discharge_df.rename(columns={'Unnamed: 0': 'Lobith'})
    discharge_df = discharge_df.set_index('Lobith')
    F = discharge_df.apply(lambda series: scipy.interpolate.interp1d(series.index, series.values))

    # add some coordinates
    coordinates = {
        'Kaub': shapely.geometry.Point(7.764967, 50.085433),
        'Duisburg-Ruhrort': shapely.geometry.Point(6.727933, 51.455350),
        'Emmerich': shapely.geometry.Point(6.245600, 51.829250),
        'Erlecom': shapely.geometry.Point(5.95044, 51.86054),
        'Nijmegen': shapely.geometry.Point(5.84601, 51.85651),
        'Ophemert': shapely.geometry.Point(5.41371, 51.85023),
        'St. Andries': shapely.geometry.Point(5.33567, 51.80930),
        'Zaltbommel': shapely.geometry.Point(5.24990, 51.81733),
        'Nijmegen (fixed layer)': shapely.geometry.Point(5.85458, 51.85264)
    }
    # store in a DataFrame
    depth_df = pd.DataFrame(F, columns=['F'])
    # add the geometry
    depth_locations_df = pd.DataFrame(data=coordinates.items(), columns=['location', 'geometry']).set_index('location')
    # merge back together
    depth_df = pd.merge(depth_df, depth_locations_df, left_index=True, right_index=True)

    # lookup closest locations
    location_edge = {}
    for name, row in depth_df.iterrows():
        location_edge[name] = find_closest_edge(graph, row.geometry)[0]
    # merge closest edges with the table
    edges_df = pd.DataFrame(location_edge).T.rename(columns={0: 'edge_from', 1: 'edge_to'})
    depth_df = pd.merge(depth_df, edges_df, left_index=True, right_index=True)
    depth_df['on_route'] = depth_df.apply(lambda x: route.has_edge(x.edge_from, x.edge_to), axis=1)

    # determine the minimal depth
    min_depth = depth_df[depth_df.on_route].apply(lambda x: x.F(lobith_discharge), axis=1).min()

    max_draught = min_depth - underkeel_clearance

    return max_draught



def shorted_path_by_dimensions(graph, source, destination, width, height, depth, length):
    """create a new constrained graph, based on dimensions, of the same type as graph and find the shortest path"""
    nodes = []
    edges = []
    for start_node, end_node, edge in graph.edges(data=True):
        # GeneralWidth can be missing or None or it should be bigger than width
        width_ok = (
            'GeneralWidth' not in edge
            or np.isnan(edge['GeneralWidth'])
            or edge['GeneralWidth'] >= width
        )
        height_ok = (
            'GeneralHeight' not in edge
            or np.isnan(edge['GeneralHeight'])
            or edge['GeneralHeight'] >= height
        )
        depth_ok = (
            'GeneralDepth' not in edge
            or edge['GeneralDepth'] >= depth
            or np.isnan(edge['GeneralDepth'])
        )
        length_ok = (
            'GeneralLength' not in edge
            or edge['GeneralLength'] >= length
            or np.isnan(edge['GeneralLength'])
        )
        if (all([width_ok, height_ok, depth_ok, length_ok])):
            edges.append((start_node, end_node))
            nodes.append(start_node)
            nodes.append(end_node)

    constrained_graph = graph.__class__()

    for node in nodes:
        constrained_graph.add_node(node)
    for edge in edges:
        constrained_graph.add_edge(edge[0], edge[1])

    path = nx.dijkstra_path(constrained_graph, source, destination, weight='length')
    return path
