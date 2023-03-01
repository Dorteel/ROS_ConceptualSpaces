# ===================================================================
#  This is an implementation of the Metric Conceptual Space Algebra
#   by Adams and Raubal (2009)
#       Mark Adamik <m.adamik@vu.nl>
# ===================================================================

from scipy.optimize import linprog
import numpy as np
from intvalpy import lineqs
import matplotlib.pyplot as plt

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
    def __init__(self, A, q, b, name=None) -> None:
        assert isinstance(q, Domain), "Argument 'q' must be a domain"
        assert len(q.dims) == A.shape[1], "The domain and matrix 'A' must have the same dimensions"
        self.A = A
        self.q = q
        self.b = b
        self.name = name

    def visualize(self, q1, q2):
        """
        Intended as a visualisation aid

        Parameters:
            q1: QualityDimension
                The first dimension that is visualised
            q2: QualityDimension
                The second dimension that is visualised

        Returns:
            A plot of the convex region
        """
        A = -np.array([[-0.894, -0.447],
               [0, -1],
               [0, 1],
               [1, 0],
               [0.894, 0.447]])
        b = -np.array([-0.671, 0, 1, 1, 1.073])

        vertices = lineqs(A, b, show=False)
        fig = plt.figure(figsize=(15, 15))
        ax = fig.add_subplot(111, title='Solution')
        x, y = vertices[:, 0], vertices[:, 1]
        ax.fill(x, y, linestyle='-', linewidth=1, color='red', alpha=0.2)
        ax.scatter(x, y, s=10, color='black', alpha=1)
        plt.show()

class Concept:

    def __init__(self, crs=None, P=None) -> None:
        """    A concept is defined as a finite set of convex regions,
        with one region corresponding for each domain
        Defined with a prototypical instance

        Args:
            crs (List, optional): A list of convex regions. Defaults to None.
            P (Instance, optional): a prototypical instance. Defaults to None.
        """
        self.regions = crs
        self.P = P

    def add_convex_region(self):
        pass

class QualityDimension:

    def __init__(self, name: str, mu: str, r: tuple, o: bool) -> None:
        """
        mu : {ratio, interval, ordinal}
        r : range of the dimension (min, max)
        o : circularity {true, false} 
        """    
        assert mu in ["ratio", "interval", "ordinal"], "Invalid mu"
        assert len(r) == 2, "Dimension limits, min and max are not set"
        self.mu = mu
        self.min, self.max = r
        self.name = name
        self.circular = o


class Domain:
    """
    A domain is defined as a set of quality dimensions, δ = Q.
    Q is the finite set of integral quality dimensions that form the domain..
    """

    def __init__(self, quality_dimensions) -> None:
        self.dims = []
        for qd in quality_dimensions:
            self.dims.append(qd)

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

    def __init__(self, domains=None, concepts=None, instances=None, contrast_classes=None, contexts=None, c=None) -> None:
        pass

    def intersection(self, regions) -> ConvexRegion:
        """
        Calculates the intersection of two (or more) convex regions
        
        Return:
            Either a convex region or an empty set
        """
        # Make sure the regions passed are Convex Regions
        # assert all([isinstance(region, ConvexRegion) for region in regions]), "All regions must be of ConvexRegion type"

        # Set the inequality constraints matrix
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


if __name__ == "__main__":

    # Testing the canonical examples: Color domain
    hue = QualityDimension("Hue", "interval", (0,360), True)
    sat = QualityDimension("Saturation", "interval", (0, 255), False)
    lig = QualityDimension("Brightness", "interval", (0, 255), False)
    colors = Domain([hue, sat, lig])
    
    red = Concept()
    test = ConvexRegion()
    red.add_convex_region()

    cs = ConceptualSpace()
    cs.intersection(0)