# Copyright (c) Tingzheng Hou.
# Distributed under the terms of the MIT License.

"""This module implements functions to calculate the ionic conductivity."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from scipy import stats
from tqdm.auto import tqdm

from mdgo.msd import msd_fft

if TYPE_CHECKING:
    from MDAnalysis import AtomGroup, Universe

__author__ = "Kara Fong, Tingzheng Hou"
__version__ = "0.3.0"
__maintainer__ = "Tingzheng Hou"
__email__ = "tingzheng_hou@berkeley.edu"
__date__ = "Jul 19, 2021"


def calc_cond_msd(
    u: Universe,
    anions: AtomGroup,
    cations: AtomGroup,
    run_start: int,
    cation_charge: float = 1,
    anion_charge: float = -1,
) -> np.ndarray:
    """Calculates the conductivity "mean square displacement" over time.

    Note:
       Coordinates must be unwrapped (in dcd file when creating MDAnalysis Universe)
       Ions selections may consist of only one atom per ion, or include all of the atoms
          in the ion. The ion AtomGroups may consist of multiple types of cations/anions.

    Args:
        u: MDAnalysis universe
        anions: MDAnalysis AtomGroup containing all anions
        cations: MDAnalysis AtomGroup containing all cations
        run_start: index of trajectory from which to start analysis
        cation_charge: net charge of cation
        anion_charge: net charge of anion

    Returns a numpy.array containing conductivity "MSD" over time
    """
    # convert AtomGroup into list of molecules
    cation_list = cations.split("residue")
    anion_list = anions.split("residue")
    # compute sum over all charges and positions
    qr = []
    for _ts in tqdm(u.trajectory[run_start:]):
        qr_temp = np.zeros(3)
        for anion in anion_list:
            qr_temp += anion.center_of_mass() * anion_charge
        for cation in cation_list:
            qr_temp += cation.center_of_mass() * cation_charge
        qr.append(qr_temp)
    return msd_fft(np.array(qr))


def get_beta(
    msd: np.ndarray,
    time_array: np.ndarray,
    start: int,
    end: int,
) -> tuple:
    """Fits the MSD to the form t^(beta) and returns beta. beta = 1 corresponds
    to the diffusive regime.

    Args:
        msd: mean squared displacement
        time_array: times at which position data was collected in the simulation
        start: index at which to start fitting linear regime of the MSD
        end: index at which to end fitting linear regime of the MSD

    Returns beta (int) and the range of beta values within the region
    """
    msd_slope = np.gradient(np.log(msd[start:end]), np.log(time_array[start:end]))
    beta = np.mean(np.array(msd_slope))
    beta_range = np.max(msd_slope) - np.min(msd_slope)
    return beta, beta_range


def choose_msd_fitting_region(
    msd: np.ndarray,
    time_array: np.ndarray,
) -> tuple:
    """Chooses the optimal fitting regime for a mean-squared displacement.
    The MSD should be of the form t^(beta), where beta = 1 corresponds
    to the diffusive regime; as a rule of thumb, the MSD should exhibit this
    linear behavior for at least a decade of time. Finds the region of the
    MSD with the beta value closest to 1.

    Note:
       If a beta value greater than 0.9 cannot be found, returns a warning
       that the computed conductivity may not be reliable, and that longer
       simulations or more replicates are necessary.

    Args:
        msd: mean squared displacement
        time_array: times at which position data was collected in the simulation

    Returns at tuple with the start of the fitting regime (int), end of the
    fitting regime (int), and the beta value of the fitting regime (float).
    """
    beta_best = 0  # region with greatest linearity (beta = 1)
    # choose fitting regions to check
    for i in np.logspace(np.log10(2), np.log10(len(time_array) / 10), 10):  # try 10 regions
        start = int(i)
        end = int(i * 10)  # fit over one decade
        beta, beta_range = get_beta(msd, time_array, start, end)
        slope_tolerance = 2  # acceptable level of noise in beta values
        # check if beta in this region is better than regions tested so far
        if (np.abs(beta - 1) < np.abs(beta_best - 1) and beta_range < slope_tolerance) or beta_best == 0:
            beta_best = beta
            start_final = start
            end_final = end
    if beta_best < 0.9:
        print(f"WARNING: MSD is not sufficiently linear (beta = {beta_best}). Consider running simulations longer.")
    return start_final, end_final, beta_best


def conductivity_calculator(
    time_array: np.ndarray,
    cond_array: np.ndarray,
    v: float,
    name: str,
    start: int,
    end: int,
    T: float,
    units: str = "real",
) -> float:
    """Calculates the overall conductivity of the system.

    Args:
        time_array: times at which position data was collected in the simulation
        cond_array: conductivity "mean squared displacement"
        v: simulation volume (Angstroms^3)
        name: system name
        start: index at which to start fitting linear regime of the MSD
        end: index at which to end fitting linear regime of the MSD
        T: temperature
        units: unit system (currently 'real' and 'lj' are supported)

    Returns the overall ionic conductivity (float)
    """
    # Unit conversions
    if units == "real":
        A2cm = 1e-8  # Angstroms to cm
        ps2s = 1e-12  # picoseconds to seconds
        e2c = 1.60217662e-19  # elementary charge to Coulomb
        kb = 1.38064852e-23  # Boltzmann Constant, J/K
        convert = e2c * e2c / ps2s / A2cm * 1000
        cond_units = "mS/cm"
    elif units == "lj":
        kb = 1
        convert = 1
        cond_units = "q^2/(tau sigma epsilon)"
    else:
        raise ValueError("units selection not supported")

    slope, _, _, _, _ = stats.linregress(time_array[start:end], cond_array[start:end])
    cond = slope / 6 / kb / T / v * convert

    print("Conductivity of " + name + ": " + str(cond) + " " + cond_units)

    return cond
