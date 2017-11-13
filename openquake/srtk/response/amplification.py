# =============================================================================
#
# Copyright (C) 2010-2017 GEM Foundation
#
# This file is part of the OpenQuake's Site Response Toolkit (OQ-SRTK)
#
# OQ-SRTK is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# OQ-SRTK is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# with this download. If not, see <http://www.gnu.org/licenses/>
#
# Author: Valerio Poggi
#
# =============================================================================
"""
Collection of methods to compute seismic amplification from a
one-dimensional soil column.
"""

import numpy as _np


# =============================================================================

def impedance_amplification(top_vs, top_dn, ref_vs=[], ref_dn=[], inc_ang=0.):
    """
    This function calculates the amplification due to a single seismic
    impedance contrast as formalized in Joyner et al. (1981) and
    Boore (2013).
    Site (top) parameters can be either scalars or arrays, as for
    the case of quarter-wavelenght approximation. If no reference
    is provided, the last value of the site array is used.
    Default angle of incidence is vertical.

    :param float or numpy.array top_vs:
        topmost shear-wave velocity in m/s

    :param float or numpy.array top_dn:
        topmost density in kg/m3

    :param float or numpy.array ref_vs:
        lowermost (reference) shear-wave velocity in m/s

    :param float or numpy.array ref_dn:
        lowermost (reference) density in kg/m3

    :param float inc_ang:
        angle of incidence relative to the vertical direction in degree

    :return float or array imp_amp:
        amplification due to the seismic impedance contrast
    """

    # Setting the reference, if not provided
    if not _np.sum(ref_vs):
        ref_vs = top_vs[-1] if _np.size(top_vs) > 1. else top_vs

    if not _np.sum(ref_dn):
        ref_dn = top_dn[-1] if _np.size(top_dn) > 1. else top_dn

    # Computing square-root impedance amplification
    imp_amp = _np.sqrt((ref_dn*ref_vs)/(top_dn*top_vs))

    if inc_ang > 0.:
        # Converting incident angle from degrees to radiants
        inc_ang *= _np.pi/180.

        # Effective angle of incidence computed using Snell's law
        eff_ang = _np.arcsin((top_vs/ref_vs)*_np.sin(inc_ang))

        # Correcting for non-vertical incidence
        imp_amp *= _np.sqrt(_np.cos(inc_ang)/_np.cos(eff_ang))

    return imp_amp

# =============================================================================

def sh_transfer_function(freq, hl, vs, dn, qs=None, inc_ang=0.):
    """
    Compute the SH-wave transfer function using Knopoff formalism
    (implicit layer matrix scheme). Calculation can be done for an
    arbitrary angle of incidence (0-90), with or without anelastic
    attenuation.
    NOTE: the implicit scheme is simple to understand and to implement,
    but is also computationally intensive and memory consuming.
    For the future, an explicit (recursive) scheme should be implemented.

    :param numpy.array hl:

    :param numpy.array vs:

    :param numpy.array dn:

    :param numpy.array qs:

    :param float or numpy.array freq:

    :param numpy.array freq:

    """

    # Precision of the complex type
    CTP = 'complex128'

    # Check for single frequency value
    if isinstance(freq, float):
        freq = _np.array([freq])

    # Model size
    lnum = len(hl)
    fnum = len(freq)

    # Variable recasting to numpy complex
    hl = _np.array(hl, dtype=CTP)
    vs = _np.array(vs, dtype=CTP)
    dn = _np.array(dn, dtype=CTP)

    # Attenuation using complex velocities
    if qs is not None:
        qs = _np.array(qs, dtype=CTP)
        vs *= ((2.*qs*1j)/(2.*qs*1j-1.))

    # Conversion to angular frequency
    angf = 2.*_np.pi*freq

    # -------------------------------------------------------------------------
    # Computing angle of propagation within layers

    iD = _np.zeros(lnum, dtype=CTP)
    iM = _np.zeros((lnum, lnum), dtype=CTP)

    iD[0] = _np.sin(inc_ang)
    iM[0,-1] = 1.

    for nl in range(lnum-1):
      iM[nl+1,nl] = 1./vs[nl]
      iM[nl+1,nl+1] = -1./vs[nl+1]

    iA = _np.linalg.solve(iM, iD)
    iS = _np.arcsin(iA)

    # -------------------------------------------------------------------------
    # Elastic parameters

    # Lame Parameters : shear modulus
    mu = dn*(vs**2.)

    # Horizontal slowness
    ns = _np.cos(iS)/vs

    # -------------------------------------------------------------------------
    # Data vector initialisation

    # Layer's amplitude vector (incognita term)
    AmpVec = _np.zeros(lnum*2, dtype=CTP)

    # Layer matrix
    LayMat = _np.zeros((lnum*2, lnum*2), dtype=CTP)

    # Input motion vector (known term)
    InpVec = _np.zeros(lnum*2, dtype=CTP)
    InpVec[-1] = 1.

    # Ouput layer's displacement matrix
    DisMat = _np.zeros((lnum, fnum), dtype=CTP)

    # -------------------------------------------------------------------------
    # Loop over frequencies

    for nf in range(fnum):

        # Reinitialise the layer matrix
        LayMat *= 0.

        # Free surface constraints
        LayMat[0, 0] = 1.
        LayMat[0, 1] = -1.

        # Interface constraints
        for nl in range(lnum-1):
            row = (nl*2)+1
            col = nl*2

            expDSA = _np.exp(1j*angf[nf]*ns[nl]*hl[nl])
            expUSA = _np.exp(-1j*angf[nf]*ns[nl]*hl[nl])

            # Displacement continuity conditions
            LayMat[row, col+0] = expDSA
            LayMat[row, col+1] = expUSA
            LayMat[row, col+2] = -1.
            LayMat[row, col+3] = -1.

            # Stress continuity conditions
            LayMat[row+1, col+0] = mu[nl]*ns[nl]*expDSA
            LayMat[row+1, col+1] = -mu[nl]*ns[nl]*expUSA
            LayMat[row+1, col+2] = -mu[nl+1]*ns[nl+1]
            LayMat[row+1, col+3] = mu[nl+1]*ns[nl+1]

        # Input motion constraints
        LayMat[-1, -1] = 1.

        # Solving linear system of wave's amplitudes
        try:
            AmpVec = _np.linalg.solve(LayMat, InpVec)
        except:
            AmpVec[:] = _np.nan

        # ---------------------------------------------------------------------
        # Solving displacement at the interfaces

        # Displacement a the surface
        DisMat[0, nf] = AmpVec[0] + AmpVec[1]

        # Loop through layer interfaces
        for nl in range(lnum-1):
            expDSA = _np.exp(1j*angf[nf]*ns[nl]*hl[nl])
            expUSA = _np.exp(-1j*angf[nf]*ns[nl]*hl[nl])

            disDSA = AmpVec[nl*2]*expDSA
            disUSA = AmpVec[nl*2+1]*expUSA

            DisMat[nl+1, nf] = disDSA + disUSA

    return DisMat