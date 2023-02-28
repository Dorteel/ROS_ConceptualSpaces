# ===================================================================
#  This is an implementation of the Metric Conceptual Space Algebra
#   by Adams and Raubal (2009)
#       Mark Adamik <m.adamik@vu.nl>
# ===================================================================

from scipy.optimize import linprog
import numpy as np

class Context():
    """
    Set of salience weight and conceptual space component pairs of the
    same type (e.g. quality dimensions)
    """
    def __init__(self) -> None:
        pass

class ContrastClass():
    """
    Defined as a region in a unit hypercube for a given domain.
    Can be thought of as a line segment in a one-dimensional domain, or
    as a region bounded by two paralel lines intersecting a unit square.
    """
    def __init__(self) -> None:
        pass

class Instance():
    """
    Represented as a finites set of points (vector)
    in one or more domains
    """
    def __init__(self) -> None:
        pass

class ConvexRegion():
    """
    Can be represented either as a set of vertices (V-polytope)
    or a bounded intersection of half-spaces, that can
    be written as a set of linear inequalitites (H-polytope)
    ---
    In this implementation, convex regions are represented as H-polytope
    """
    def __init__(self, A, q, b) -> None:
        pass

class Concept:
    """
    A concept is defined as a finite set of convex regions,
    with one region corresponding for each domain
    Defined with a prototypical instance
    """
    def __init__(self, cr=None, P=None) -> None:
        pass

class QualityDimension:
    """
    
    """

    def __init__(self, mu: str, r: tuple, o: bool) -> None:
        """
        mu : {ratio, interval, ordinal}
        r : range of the dimension (min, max)
        o : circularity {true, false} 
        """    
        pass

class Domain:
    """
    A domain is defined as a set of quality dimensions, δ = Q.
    Q is the finite set of integral quality dimensions that form the domain..
    """


    def __init__(self, quality_dimensions) -> None:
        pass

class ConceptualSpace:
    """
    A class to represent a metric conceptual space.

    ...

    Attributes
    ----------
    domains : D
        A finite set of domains
    concepts : C
        A finite set of concepts
    instances : I
        instances
    contrast classes : CC
        A finite set of contrast classes
    contexts : CX
        A finite set of contexts
    c: constant similarity sensitivity parameter

    Methods
    -------
    info(additional=""):
        Prints the person's name and age.
    """

    def __init__(self, domains, concepts, instances, contrast_classes, contexts, c) -> None:
        pass

    def intersection(self, regions) -> ConvexRegion:
        """
        Calculates the intersection of two (or more) convex regions
        
        Return:
            Either a convex region or an empty set
        """
        # Make sure the regions passed are Convex Regions
        assert all([type(region) == ConvexRegion for region in regions])


# Set the inequality constraints matrix
# Note: the inequality constraints must be in the form of <=
A = np.array([[-1, -1, -1], [-1, 2, 0], [0, 0, -1], [-1, 0, 0], [0, -1, 0], [0, 0, -1]])

# Set the inequality constraints vector
b = np.array([-1000, 0, -340, 0, 0, 0])

# Set the coefficients of the linear objective function vector
c = np.array([10, 15, 25])

# Solve linear programming problem
res = linprog(c, A_ub=A, b_ub=b)

# Print results
print('Optimal value:', round(res.fun, ndigits=2),
      '\nx values:', res.x,
      '\nNumber of iterations performed:', res.nit,
      '\nStatus:', res.message)