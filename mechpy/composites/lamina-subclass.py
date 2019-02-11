"""Defines the Lamina class for use with mechpy.

Assumptions
-----------
* Lamina are generally orthotropic.
* Lamina properties and values are assumed to be in the lamina coordinate
  system
  (i.e. 12-plane).
* Theta is in degrees, measured from the laminate x-axis to the lamina 1-axis.
* The laminate z-direction is upward, away from the bottom surface.
* Reported strain values are in engineering strain.
* All loads and moments are running values supplied as force or moment per unit
  width.
* Unit systems are consistent (i.e. SI, US, or Imperial).
* Equations and symbol conventions are per NASA-RP-1351 'Basic Mechanics of
  Laminated Composite Plates' and Jones' 'Mechanics Of Composite Materials'.

TODO:
-----
* [ ] add functionality to register laminate property to forwad updates to
      Laminate classes
* [ ] add error checking for attribute types
* [ ] add a property for the compliance matrix Sk
* [ ] add failure indeces
* [ ] remove laminate orientation calculations and have them be returned as
      calculated properties
"""

import numpy as np
from math import isnan, cos, sin, radians


class Lamina:
    """An individual lamina or "ply".

    Each lamina is assumed to be orthotropic.
    """

    __name__ = 'Lamina'
    __slots__ = ['t', 'E1', 'E2', 'nu12', 'G12', 'alpha', 'beta']

    def __init__(self,
                 t=1,     # lamina thickness
                 E1=1,    # Young's modulus in 1-direction
                 E2=1,    # Young's modulus in 2-direction
                 nu12=1,  # Poisson's ratio in 12-plane
                 G12=1,   # shear modulus in 12-plane
                 a11=1,   # coeff. of thermal expansion in 1-direction
                 a22=1,   # coeff. of thermal expansion in 2-direction
                 b11=1,   # coeff. of moisture expansion in 1-direction
                 b22=1):  # coeff. of moisture expansion in 2-direction
        """Initialize the Lamina instance."""

        self.t = t
        self.E1 = E1
        self.E2 = E2
        self.nu12 = nu12
        self.G12 = G12
        self.alpha = np.array([[a11],
                               [a22],
                               [0]], dtype=float)
        self.beta = np.array([[b11],
                              [b22],
                              [0]], dtype=float)

    @property
    def is_fully_defined(self):
        """Check if lamina is fully defined with proper attr data types."""

        if self.t == 0 or isnan(self.t):
            raise TypeError("lamina.tk must be a non-zero number")
        elif isnan(self.theta):
            raise TypeError("lamina.theta must be a number (in degrees)")
        elif self.E1 == 0 or isnan(self.E1):
            raise TypeError("lamina.E1 must be a non-zero number")
        elif self.E2 == 0 or isnan(self.E2):
            raise TypeError("lamina.E2 must be a non-zero number")
        elif (self.nu12 <= 0 or self.nu12 > 1) or isnan(self.nu12):
            raise TypeError("""lamina.nu12 must be a non-zero number between
                            zero and 1""")
        elif self.G12 == 0 or isnan(self.G12):
            raise TypeError("lamina.G12 must be a non-zero number")
        else:
            return True


class Ply(Lamina):
    """A Ply for use in a Laminate."""

    __name__ = 'Ply'
    __protected__ = ['Q', 'Qbar', 'T', 'Tinv']
    __unprotected__ = ['id', 'e_t', 'e_h']
    __updated__ = Lamina.__slots__ + ['t', 'z', 'theta', 'e_m']
    __slots__ = __protected__ + __unprotected__ + __updated__

    def __init__(self,
                 id=0,
                 t=1,
                 z=0,
                 theta=0,
                 E1=1,
                 E2=1,
                 nu12=1,
                 G12=1,
                 a11=1,
                 a22=1,
                 b11=1,
                 b22=1,
                 e_m=np.zeros((3, 1))):
        """Initialize the Ply instance."""

        self.id = id
        self.z = z
        self.theta = theta
        self.e_m = e_m
        self.e_t = np.zeros((3, 3))
        self.e_h = np.zeros((3, 3))

        super(Lamina, self).__init__(
            t, E1, E2, nu12, G12, a11, a22, b22, b22
        )

        self.__update()

    def __setattr__(self, attr, val):
        """Check and set attributes."""

        # udpate laminate after updated properties are set
        if attr in self.__updated__:
            self.__sattr(attr, val)
            self.__update()

        # don't set protected values
        elif attr in self.__protected__:
            raise AttributeError(self.__name__ + ".%s" % attr
                                 + "is a derived value and cannot be set")

        # check if attribute is an unprotected value
        elif attr in self.__unprotected__:
            self.__sattr(attr, val)

    def __sattr(self, arg, val):
        """Directly set attribute."""
        super().__setattr__(arg, val)

    def __update(self):
        """Update calculated properties when new values are assigned."""

        # on-axis reduced stiffness matrix, Q
        # NASA-RP-1351, Eq (15)
        nu21 = self.nu12 * self.E2 / self.E1  # Jones, Eq (2.67)
        q11 = self.E1 / (1 - self.nu12 * nu21)
        q12 = self.nu12 * self.E2 / (1 - self.nu12 * nu21)
        q22 = self.E2 / (1 - self.nu12 * nu21)
        q66 = self.G12

        self.__sattr(
            'Q', np.array([[q11, q12, 0], [q12, q22, 0], [0, 0, q66]])
        )

        # the transformation matrix and its inverse
        # create intermediate trig terms
        m = cos(radians(self.theta))
        n = sin(radians(self.theta))

        # create transformation matrix and inverse
        self.__sattr('T', np.array([[m**2, n**2, 2 * m * n],
                                     [n**2, m**2, -2 * m * n],
                                     [-m * n, m * n, m**2 - n**2]]))
        self.__sattr('Tinv', np.linalg.inv(self.T))

        # the transformed reduced stiffness matrix (laminate coordinate system)
        # Jones, Eq (2.84)
        self.__sattr('Qbar', self.Tinv @ self.Q @ self.Tinv.T)

        # thermal and hygral strains in laminate and lamina c-systems
        # NASA-RP-1351 Eq (90), (91), and (95)
        self.__sattr('e_t', self.alpha * self.dT)
        self.__sattr('e_h', self.beta * self.dM)

    @property
    def zk(self):
        """The vertical location of the lamina's top plane.

        zk is measured from the midplane of the laminate with the convention
        of positive pointing upward.
        """
        return self.z + self.t / 2

    @property
    def zk1(self):
        """The vertical location of the lamina's bottom plane.

        zk1 is measured from the midplane of the laminate with the convention
        of positive pointing upward. Note: zk1 is z_(k-1).
        """
        return self.z - self.t / 2

    @property
    def e_tbar(self):
        """Transformed thermal strain."""
        return self.Tinv @ self.alpha  # NASA-RP-1351 Eq (90)

    @property
    def e_hbar(self):
        """Transformed hygral strain."""
        return self.Tinv @ self.alpha  # NASA-RP-1351 Eq (95)

    @property
    def e(self):
        """Total strain."""
        return self.e_m + self.e_t + self.e_h
