#!/usr/bin/env python3
"""
photodyn2p - general TTV and photodynamical model for a system with TWO planets (TTVFast).

Derived from toi3686_photodynamical_ttvfast_v3.py (same physics and conventions), but general:
  * each planet is transiting (mid-times and/or photometry) or non-transiting (seen only through the
    TTVs of the other planet and, optionally, the RVs);
  * two modes:
      "ttv"       : mid-transit times (+ optional RVs); fast; with a global search (differential evolution)
                    over the dynamics; also produces a start file for the photodynamical mode;
      "photodyn"  : light curves per segment (batman, optional quasi-periodic GP per segment)
                    + mid-times + optional RVs;
  * masses as log10(m_p/M*) (TTVs constrain mass ratios); masses in M_earth/M_J are derived;
  * everything through a JSON configuration (see the examples and the GUI photodyn2p_gui.py).

Usage:
  python photodyn2p.py config.json [--nproc 8] [--no-search] [--no-mcmc] [--mcmc] [--steps N]
                                   [--start-json start.json] [--outdir DIR] [--eval-only]
Requires: numpy scipy matplotlib batman-package celerite2 ttvfast emcee  (optional: h5py, corner, tqdm)
Python >= 3.7.
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import copy
import json
import sys
import time
from collections import Counter, OrderedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import minimize

try:
    from ttvfast import ttvfast as ttvfast_run
    from ttvfast.models import Planet
except ImportError as e:
    raise SystemExit("ttvfast is required: pip install ttvfast\n" + str(e)) from e

VERSION = "1.1 (31 Oct 2026)"

# ===========================================================================
# Constanten
# ===========================================================================
K2_GAUSS = 2.959122082855911e-4        # (Gauss-constante)^2 [AU^3 / (Msun d^2)]
RSUN_AU = 1.0 / 215.032
RSUN_REARTH, RSUN_RJUP = 109.076, 9.731
AUDAY_TO_MS = 1.495978707e11 / 86400.0
MEARTH_MSUN, MJUP_MSUN = 3.003e-6, 9.548e-4
MASS_UNITS = {"Mearth": MEARTH_MSUN, "Mjup": MJUP_MSUN}
RADIUS_UNITS = {"Mearth": ("Rearth", RSUN_REARTH), "Mjup": ("Rjup", RSUN_RJUP)}
INPUT_FLAG = 0                         # TTVFast: 0 = Jacobi-elementen

DEFAULT_CONFIG = {
    "name": "object",
    "mode": "ttv",                     # "ttv" | "photodyn"
    "outdir": "p2p_output",
    "t_start": None,                   # default: 1 d before the earliest data point
    "t_end": None,                     # default: 1 d after the last data point
    "dt": None,                        # TTVFast step [d]; default min(P)/32
    "star": {"mstar": [1.0, 0.1], "rstar": [1.0, 0.05]},          # Gaussische priors [Msun], [Rsun]
    "planets": [],
    "dOm_bounds": None,                # default [-45, 45] if both transit, otherwise [-180, 180]
    "free_ecc": True,
    "ecc_max": 0.5,
    "b_max": 1.0,                      # bound |b| for transiting planets
    "midtimes": {"floor_min": 2.0, "jitter": "none", "exclude_facility_in_photodyn": "TESS"},
    "rv": None,                        # {"file":..., "gp": false, "prot_bounds": [4, 20], "share_prot_with": null,
                                       #  "search_jitter": 10.0}
    "photometry": None,                # {"csv":..., "residuals_csv":..., "segments": null, "trend": "ignore"|"multiply", "gp": true,
                                       #  "prot_bounds": [4, 20], "lnq0_min": -2.302585, "dilution": "fixed"|"free",
                                       #  "gp_start": {...}}
    # prefit (as toi3686_ttv_prefit.py): DE + polishing on a cheap objective; b/cos i, dOm, M*, R* fixed
    "search": {"enabled": True, "popsize": 15, "maxiter": 400, "seed": 1, "strategy": "best1bin",
               "phase_window": 0.15, "init_json": [], "checkpoint": "prefit_checkpoint.npz", "top": 10,
               "polish_nfev": 150, "rv_term": "auto", "phot_weight": 1.0, "free_geometry": False},
    "optimize": {"maxiter_nuis": 50, "maxiter": 400},
    "mcmc": {"enabled": False, "nwalkers": 0, "steps": 3000, "init_hessian": True, "backend": "chain.h5",
             "burn": None},
    "start_json": None,
}
DEFAULT_PLANET = {
    "name": "b",
    "transiting": True,
    "P": None,                         # observed (mean) period [d]; starting value of the osculating P
    "P_range": 0.02,                   # relative search width of the osculating P
    "T0": None,                        # a conjunction/transit time [BTJD] (optional)
    "midtimes": None,                  # file: epoch time sig_stat [sig_sys] [facility]; errors in days
    "mass_unit": "Mearth",             # "Mearth" | "Mjup" (display and log_mp in start files)
    "mass_guess": None,                # in mass_unit
    "mass_bounds": None,               # in mass_unit, at M* = prior mean; default [0.1, 3000] Mearth
    "rp": 0.02,                        # Rp/R* (transiting only)
    "rp_prior": None,                  # [mu, sigma] Gaussian (e.g. from undiluted ground-based photometry)
    "b": 0.3,                          # starting impact parameter (transiting)
    "cosi": 0.0,                       # starting cos i (non-transiting)
    "forbid_transit": True,            # non-transiting: |b| < 1 forbidden
    "ecosw": 0.0, "esinw": 0.0,        # startwaarden
    "P_bounds": None,                  # explicit bounds of the osculating P [d] (otherwise P*(1 -+ P_range))
    "phase_window": None,              # prefit: half-width of the phase window (default search.phase_window)
    "ecc_search": [0.4, 0.45],         # prefit: bound on |ecosw|, |esinw| and cut in e
    "segment_times": None,             # prefit: sector T_ref sig_T P_loc sig_P rho (b_times.dat format)
    "segment_halfwidth": 13.0,         # window [d] around T_ref when there is no residual photometry
    "phot_term": False,                # prefit: template of this planet on the residual photometry
}
SEG_KEYS = ["ln_sig", "ln_Prot", "ln_Q0", "ln_dQ", "f_gp"]


def merge(default, user):
    out = copy.deepcopy(default)
    for k, v in (user or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path):
    with open(path) as fh:
        user = json.load(fh)
    cfg = merge(DEFAULT_CONFIG, user)
    if len(cfg["planets"]) != 2:
        raise SystemExit("the configuration must contain exactly two planets")
    cfg["planets"] = [merge(DEFAULT_PLANET, p) for p in cfg["planets"]]
    names = [p["name"] for p in cfg["planets"]]
    if len(set(names)) != 2 or not all(n.isidentifier() for n in names):
        raise SystemExit(f"planet names must be different and simple (letters/digits): {names}")
    if not any(p["transiting"] for p in cfg["planets"]):
        raise SystemExit("at least one planet must transit")
    for p in cfg["planets"]:
        if not p["P"]:
            raise SystemExit(f"planet {p['name']}: period P is missing")
        if p["mass_unit"] not in MASS_UNITS:
            raise SystemExit(f"planet {p['name']}: mass_unit must be Mearth or Mjup")
    if cfg["mode"] not in ("ttv", "photodyn"):
        raise SystemExit("mode must be 'ttv' or 'photodyn'")
    if cfg["mode"] == "photodyn" and not (cfg["photometry"] and cfg["photometry"].get("csv")):
        raise SystemExit("mode 'photodyn' requires photometry.csv")
    base = os.path.dirname(os.path.abspath(path))
    cfg["_base"] = base
    return cfg


def resolve(cfg, path):
    """Paths relative to the directory of the configuration file (or absolute)."""
    if not path:
        return None
    if os.path.isabs(path) or os.path.isfile(path):
        return path
    cand = os.path.join(cfg["_base"], path)
    if os.path.isfile(cand):
        return cand
    raise SystemExit(f"file not found: {path} (also not in {cfg['_base']})")


# ===========================================================================
# Fysica (identiek aan v3)
# ===========================================================================
def a_au(P, mstar, mp):
    return (K2_GAUSS * (mstar + mp) * P**2 / (4.0 * np.pi**2)) ** (1.0 / 3.0)


def a_over_rstar(P, mstar, mp, rstar):
    return a_au(P, mstar, mp) / (rstar * RSUN_AU)


def inc_from_b(b, aR, e, w_deg):
    """Inclination [degrees] from the SIGNED impact parameter: b < 0 gives i > 90 degrees."""
    c = b / aR * (1.0 + e * np.sin(np.radians(w_deg))) / (1.0 - e**2)
    return float(np.degrees(np.arccos(np.clip(c, -0.9999, 0.9999))))


def b_from_inc(i_deg, aR, e, w_deg):
    return float(aR * np.cos(np.radians(i_deg)) * (1.0 - e**2) / (1.0 + e * np.sin(np.radians(w_deg))))


def mean_anomaly_at_start(T0, P, t_start, e, w_deg):
    """Mean anomaly [degrees] at t_start such that the conjunction (f = pi/2 - omega) falls at T0."""
    w = np.radians(w_deg)
    f_tr = 0.5 * np.pi - w
    E_tr = 2.0 * np.arctan2(np.sqrt(1 - e) * np.sin(f_tr / 2), np.sqrt(1 + e) * np.cos(f_tr / 2))
    M_tr = E_tr - e * np.sin(E_tr)
    return float(np.degrees(M_tr - 2.0 * np.pi * (T0 - t_start) / P) % 360.0)


def hill_ok(m1, m2, a1, a2, mstar):
    rh = ((m1 + m2) / (3.0 * mstar)) ** (1.0 / 3.0) * 0.5 * (a1 + a2)
    return abs(a2 - a1) / rh > 2.0 * np.sqrt(3.0)


def k_semi_amplitude(mp, mstar, P, i_deg, e):
    K = ((2.0 * np.pi * K2_GAUSS / P) ** (1.0 / 3.0) * mp * np.sin(np.radians(i_deg))
         / (mstar + mp) ** (2.0 / 3.0) / np.sqrt(1.0 - e**2))
    return float(K * AUDAY_TO_MS)


def mutual_inclination(i1, i2, dOm):
    i1, i2, dOm = np.radians(i1), np.radians(i2), np.radians(dOm)
    c = np.cos(i1) * np.cos(i2) + np.sin(i1) * np.sin(i2) * np.cos(dOm)
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def rotation_kernel(ln_sig, ln_Prot, ln_Q0, ln_dQ, f_gp):
    from celerite2 import terms
    return terms.RotationTerm(sigma=np.exp(ln_sig), period=np.exp(ln_Prot),
                              Q0=np.exp(ln_Q0), dQ=np.exp(ln_dQ), f=f_gp)


# ===========================================================================
# Data
# ===========================================================================
def to_btjd(t):
    """BJD, BJD-2450000 or BJD-2400000 -> BTJD (= BJD - 2457000); BTJD stays BTJD."""
    t = np.asarray(t, float)
    med = float(np.nanmedian(t))
    if med > 2.4e6:
        return t - 2457000.0
    if 5.0e4 < med < 1.0e5:
        return t - 57000.0
    if 5.0e3 < med < 2.0e4:
        return t - 7000.0
    return t


def load_midtimes(path, P_guess, label):
    """epoch time sig_stat [sig_sys] [facility] (errors in days). Returns a dict with t [BTJD], sig [d],
    epoch (int), fac (list)."""
    rows = []
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            p = s.split()
            try:
                n, t = float(p[0]), float(p[1])
                es = float(p[2]) if len(p) > 2 else 0.0
                ey = float(p[3]) if len(p) > 3 else 0.0
            except (ValueError, IndexError):
                continue
            rows.append((n, t, float(np.hypot(es, ey)), p[4] if len(p) > 4 else ""))
    if not rows:
        raise SystemExit(f"no mid-times read from {path}")
    n = np.array([r[0] for r in rows])
    t = to_btjd([r[1] for r in rows])
    ep = np.round(n).astype(int)
    if not np.allclose(n, ep, atol=1e-6) or len(np.unique(ep)) < 2:
        print(f"  [warning] {label}: epochs not usable; rounded with P = {P_guess}")
        ep = np.round((t - t.min()) / P_guess).astype(int)
    else:
        Pf = np.polyfit(ep, t, 1)[0]
        if abs(Pf / P_guess - 1.0) > 0.1:
            raise SystemExit(f"{label}: epochs in {path} give P = {Pf:.5f} d, far from P = {P_guess}; "
                             "check the epoch column or the period")
    o = np.argsort(t)
    return dict(t=t[o], sig=np.array([r[2] for r in rows])[o], epoch=ep[o],
                fac=[rows[i][3] for i in o])


def load_rvs(path):
    """time rv[m/s] err[m/s] instrument; the weighted mean is subtracted per instrument."""
    rows = []
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            p = s.split()
            try:
                rows.append((float(p[0]), float(p[1]), float(p[2]), p[3] if len(p) > 3 else "rv"))
            except (ValueError, IndexError):
                continue
    if not rows:
        raise SystemExit(f"no RVs read from {path}")
    data = OrderedDict()
    for inst in sorted(set(r[3] for r in rows)):
        sel = [r for r in rows if r[3] == inst]
        t = to_btjd([r[0] for r in sel])
        rv, er = np.array([r[1] for r in sel]), np.array([r[2] for r in sel])
        rv = rv - np.average(rv, weights=1.0 / er**2)
        o = np.argsort(t)
        data[inst] = dict(t=t[o], rv=rv[o], err=er[o])
    return data


def _has_header(path):
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            try:
                [float(v) for v in s.replace(",", " ").split()]
                return False
            except ValueError:
                return True
    return False


def load_photometry(path, segments=None, trend="ignore"):
    """CSV: time, flux, error, segment[, trend]. trend = 'multiply' reconstructs flux x trend (for
    detrended data whose trend is modelled again with a GP)."""
    with open(path) as fh:
        first = fh.readline()
    delim = "," if "," in first or first.startswith("#") and "," in open(path).read(2000) else None
    d = np.loadtxt(path, delimiter=delim, skiprows=1 if _has_header(path) else 0, ndmin=2)
    t, f, e, seg = d[:, 0], d[:, 1], d[:, 2], d[:, 3].astype(int)
    if trend == "multiply":
        if d.shape[1] < 5:
            raise SystemExit("photometry.trend = 'multiply' requires a fifth column (trend)")
        f, e = f * d[:, 4], e * d[:, 4]
    t = to_btjd(t)
    out = []
    for s in (segments or sorted(set(seg.tolist()))):
        m = seg == s
        if not m.any():
            print(f"  [warning] segment {s} not in {path}")
            continue
        o = np.argsort(t[m])
        ff, ee, ts = f[m][o], e[m][o], t[m][o]
        med = np.median(ff)
        out.append(dict(seg=int(s), t=ts, f=ff / med, e=ee / med, cad=float(np.median(np.diff(ts)))))
    return out


# ===========================================================================
# TTVFast
# ===========================================================================
def run_ttvfast(dyn, tags, t_start, t_end, dt, rv_times=None, rstar=None):
    """Integration; per planet transit times, epochs, |b| and v_sky; optionally stellar RVs [m/s]."""
    total = float(t_end - t_start)
    if total <= 0 or not (0 < dt < min(dyn["P_" + t] for t in tags) / 20.0):
        raise ValueError("invalid integration window or step")
    pl = []
    for k, tag in enumerate(tags):
        pl.append(Planet(mass=dyn["mp_" + tag], period=dyn["P_" + tag], eccentricity=dyn["e_" + tag],
                         inclination=dyn["i_" + tag], longnode=0.0 if k == 0 else dyn["dOm"],
                         argument=dyn["w_" + tag] % 360.0,
                         mean_anomaly=mean_anomaly_at_start(dyn["T0_" + tag], dyn["P_" + tag], t_start,
                                                            dyn["e_" + tag], dyn["w_" + tag])))
    rv_rel = None
    if rv_times is not None and len(rv_times):
        rv_rel = [float(x) for x in (np.asarray(rv_times, float) - t_start)]
        if min(rv_rel) < 2 * dt or np.any(np.diff(rv_rel) < 0):
            raise ValueError("rv_times must be sorted and >= 2 dt after the start")
    res = ttvfast_run(pl, dyn["mstar"], 0.0, dt, total, rv_times=rv_rel, input_flag=INPUT_FLAG)
    pos = np.asarray(res["positions"], float)
    pid, epo, tt, rsky, vsky = pos[0].astype(int), pos[1].astype(int), pos[2], pos[3], pos[4]
    good = tt > -1.0
    rs_au = (rstar if rstar is not None else dyn["rstar"]) * RSUN_AU
    out = {}
    for k, tag in enumerate(tags):
        m = (pid == k) & good
        b = np.abs(rsky[m]) / rs_au
        ok = b < 1.5
        out["times_" + tag] = tt[m][ok] + t_start
        out["epoch_" + tag] = epo[m][ok]
        out["b_" + tag] = b[ok]
        out["vsky_" + tag] = np.abs(vsky[m][ok]) / rs_au
        out["conj_" + tag] = tt[m] + t_start          # all conjunctions (also without a transit)
    out["rv"] = None
    if rv_rel is not None:
        rv = np.asarray(res["rv"], float) * AUDAY_TO_MS
        if len(rv) == len(rv_rel) and np.all(np.isfinite(rv)) and np.count_nonzero(rv == 0.0) == 0:
            out["rv"] = rv
    return out


def mean_ephemeris(times, epochs, t_ref=None):
    times, epochs = np.asarray(times, float), np.asarray(epochs, float)
    if len(times) < 2:
        return None
    P, T0 = np.polyfit(epochs, times, 1)
    epoch_ref = int(epochs[np.argmin(np.abs(times - t_ref))]) if t_ref is not None else int(epochs[0])
    oc = (times - (T0 + epochs * P)) * 1440.0
    return dict(P=float(P), T0_ref=float(T0 + epoch_ref * P), epoch_ref=int(epoch_ref), T0_epoch0=float(T0),
                oc_rms_min=float(np.std(oc)), oc_halfamp_min=float(np.ptp(oc) / 2))


# ===========================================================================
# Lichtkrommen
# ===========================================================================
def multi_transit_model(t, t0_list, b_list, P, rp, aR, q1, q2, e, w_deg, cad, dil=1.0):
    """Sum of individual transits [ppt], each with its own T0 and b (batman per event in a window)."""
    import batman
    flux = np.ones_like(t, dtype=float)
    dur = P / np.pi / max(aR, 1.01) * (1.0 + rp)                 # upper bound of the transit duration [d]
    half = min(0.45 * P, max(0.6, 1.5 * dur))
    ss = 7 if cad > 0.01 else 1
    p = batman.TransitParams()
    p.per, p.rp, p.a, p.ecc, p.w = P, rp, aR, e, w_deg
    p.limb_dark, p.u = "quadratic", [2 * np.sqrt(q1) * q2, np.sqrt(q1) * (1 - 2 * q2)]
    for t0, b in zip(t0_list, b_list):
        lo, hi = np.searchsorted(t, [t0 - half, t0 + half])
        if hi - lo < 5:
            continue
        p.t0, p.inc = float(t0), inc_from_b(abs(b), aR, e, w_deg)
        flux[lo:hi] *= batman.TransitModel(p, t[lo:hi], supersample_factor=ss, exp_time=cad).light_curve(p)
    return (flux - 1.0) * 1e3 * dil


class Segment:
    PAD = 0.6

    def __init__(self, d, use_gp):
        self.t, self.seg, self.cad = d["t"], d["seg"], d["cad"]
        self.y, self.e = (d["f"] - 1.0) * 1e3, d["e"] * 1e3
        self.t_min, self.t_max = self.t.min(), self.t.max()
        self.use_gp = use_gp

    def transits(self, ev, d, shape, tag, D):
        tt = ev["times_" + tag]
        m = (tt >= self.t_min - self.PAD) & (tt <= self.t_max + self.PAD)
        return multi_transit_model(self.t, tt[m], ev["b_" + tag][m], d["P_" + tag], shape["rp_" + tag],
                                   d["aR_" + tag], shape["q1"], shape["q2"], d["e_" + tag], d["w_" + tag],
                                   self.cad, D)

    def gp(self, sp):
        from celerite2 import GaussianProcess
        gp = GaussianProcess(rotation_kernel(sp["ln_sig"], sp["ln_Prot"], sp["ln_Q0"], sp["ln_dQ"], sp["f_gp"]),
                             mean=0.0)
        gp.compute(self.t, diag=self.e**2 + np.exp(2 * sp["ln_jit"]), quiet=True)
        return gp

    def lnlike(self, resid, sp):
        if self.use_gp:
            return self.gp(sp).log_likelihood(resid)
        var = self.e**2 + np.exp(2 * sp["ln_jit"])
        return float(-0.5 * np.sum(resid**2 / var + np.log(2 * np.pi * var)))


class RVData:
    def __init__(self, rv_data, use_gp):
        self.instruments = list(rv_data)
        t = np.concatenate([rv_data[i]["t"] for i in self.instruments])
        rv = np.concatenate([rv_data[i]["rv"] for i in self.instruments])
        er = np.concatenate([rv_data[i]["err"] for i in self.instruments])
        ix = np.concatenate([np.full(len(rv_data[i]["t"]), k) for k, i in enumerate(self.instruments)])
        o = np.argsort(t, kind="stable")
        self.t, self.rv, self.err, self.idx = t[o], rv[o], er[o], ix[o].astype(int)
        self.n_inst = len(self.instruments)
        self.use_gp = use_gp

    def offsets(self, p):
        return np.array([p["rv_off_%d" % k] for k in range(self.n_inst)])[self.idx]

    def jitter2(self, p):
        return np.exp(2.0 * np.array([p["rv_ln_jit_%d" % k] for k in range(self.n_inst)]))[self.idx]

    def gp(self, p, ln_Prot):
        from celerite2 import GaussianProcess
        gp = GaussianProcess(rotation_kernel(p["rv_ln_sig"], ln_Prot, p["rv_ln_Q0"], p["rv_ln_dQ"], p["rv_f_gp"]),
                             mean=0.0)
        gp.compute(self.t, diag=self.err**2 + self.jitter2(p), quiet=True)
        return gp

    def lnlike(self, rv_dyn, p, ln_Prot):
        r = self.rv - rv_dyn - self.offsets(p)
        if self.use_gp:
            return self.gp(p, ln_Prot).log_likelihood(r)
        var = self.err**2 + self.jitter2(p)
        return float(-0.5 * np.sum(r**2 / var + np.log(2 * np.pi * var)))

    def profiled_chi2(self, rv_dyn, jit):
        """Fast term for the search: offsets per instrument profiled, fixed jitter, no GP."""
        w = 1.0 / (self.err**2 + jit**2)
        r = self.rv - rv_dyn
        chi2 = 0.0
        for k in range(self.n_inst):
            m = self.idx == k
            off = np.sum(w[m] * r[m]) / np.sum(w[m])
            chi2 += np.sum(w[m] * (r[m] - off) ** 2)
        return float(chi2)


# ===========================================================================
# Probleem: parameters, priors, likelihood
# ===========================================================================
class Problem:
    CACHE_SIZE = 8

    def __init__(self, cfg, mode=None):
        self.cfg = cfg
        self.mode = mode or cfg["mode"]
        self.planets = cfg["planets"]
        self.tags = [p["name"] for p in self.planets]
        self.pl = {p["name"]: p for p in self.planets}
        self.free_ecc, self.ecc_max = bool(cfg["free_ecc"]), float(cfg["ecc_max"])
        self.ref_tag = next(p["name"] for p in self.planets if p["transiting"])   # b >= 0 for this planet
        ms0, ss0 = cfg["star"]["mstar"]
        rs0, sr0 = cfg["star"]["rstar"]
        self.mstar_prior, self.rstar_prior = (float(ms0), float(ss0)), (float(rs0), float(sr0))

        # --- data -------------------------------------------------------------------
        self.tt = {}
        mt = cfg["midtimes"]
        excl = mt.get("exclude_facility_in_photodyn") if self.mode == "photodyn" else None
        for p in self.planets:
            if p["transiting"] and p["midtimes"]:
                d = load_midtimes(resolve(cfg, p["midtimes"]), p["P"], "mid-times " + p["name"])
                use = np.ones(len(d["t"]), bool)
                if excl:
                    use = np.array([excl.upper() not in f.upper() for f in d["fac"]])
                d["use"] = use
                d["sig_tot"] = np.sqrt(d["sig"]**2 + (float(mt.get("floor_min") or 0.0) / 1440.0)**2)
                self.tt[p["name"]] = d
                print(f"  mid-times {p['name']}: {len(d['t'])} ({int(use.sum())} in the likelihood"
                      f"{', ' + excl + ' omitted' if excl else ''})")
        self.tt_jitter = mt.get("jitter") == "free"
        # ttv mode: measured sector times and local periods (b_times.dat) as a likelihood term; not in photodyn
        # mode (the same photometry is already in the likelihood)
        self.segt = []
        if self.mode == "ttv":
            phc0 = cfg.get("photometry") or {}
            wins = {}
            if phc0.get("residuals_csv"):
                dd = np.loadtxt(resolve(cfg, phc0["residuals_csv"]), delimiter=",", comments="#", usecols=(0, 3))
                tt_, sg_ = to_btjd(dd[:, 0]), dd[:, 1].astype(int)
                wins = {int(g): (float(tt_[sg_ == g].min()), float(tt_[sg_ == g].max())) for g in np.unique(sg_)}
            for p in self.planets:
                if p["transiting"] and p.get("segment_times"):
                    self.segt += load_segment_times(p["name"], resolve(cfg, p["segment_times"]), wins,
                                                    float(p.get("segment_halfwidth", 13.0)))
            if self.segt:
                print(f"  sector times in the likelihood: {[(st['tag'], st['seg']) for st in self.segt]}")
        self.rv = None
        rvc = cfg.get("rv")
        if rvc and rvc.get("file"):
            self.rv = RVData(load_rvs(resolve(cfg, rvc["file"])), bool(rvc.get("gp")))
            print(f"  RVs: {len(self.rv.t)} points, instruments {self.rv.instruments}"
                  f"{' (with GP)' if self.rv.use_gp else ''}")
        self.segments = []
        phc = cfg.get("photometry") or {}
        if self.mode == "photodyn":
            segs = load_photometry(resolve(cfg, phc["csv"]), phc.get("segments"), phc.get("trend", "ignore"))
            self.segments = [Segment(s, bool(phc.get("gp", True))) for s in segs]
            print(f"  photometry: {sum(len(s.t) for s in self.segments)} points in segments "
                  f"{[s.seg for s in self.segments]}{' (GP per segment)' if phc.get('gp', True) else ''}")

        # --- tijdvenster ------------------------------------------------------------
        tmin, tmax = [], []
        for d in self.tt.values():
            tmin.append(d["t"][d["use"]].min() if d["use"].any() else d["t"].min())
            tmax.append(d["t"].max())
        if self.rv is not None:
            tmin.append(self.rv.t.min())
            tmax.append(self.rv.t.max())
        for s in self.segments:
            tmin.append(s.t_min)
            tmax.append(s.t_max)
        if phc.get("residuals_csv"):                 # the residual photometry of the prefit counts as well (as v3)
            tr = to_btjd(np.loadtxt(resolve(cfg, phc["residuals_csv"]), delimiter=",", comments="#", usecols=0))
            tmin.append(float(tr.min()))
            tmax.append(float(tr.max()))
        if not tmin:
            raise SystemExit("no data: give mid-times, RVs or photometry")
        self.t_start = float(cfg["t_start"]) if cfg["t_start"] is not None else float(min(tmin) - 1.0)
        self.t_end = float(cfg["t_end"]) if cfg["t_end"] is not None else float(max(tmax) + 1.0)
        Pmin = min(p["P"] for p in self.planets)
        self.dt = float(cfg["dt"]) if cfg["dt"] else float(Pmin / 32.0)
        self.t_mid = 0.5 * (self.t_start + self.t_end)

        # --- parameters -------------------------------------------------------------
        spec = []

        def add(n, lo, hi, x0, typ=None, dyn=False):
            x0 = float(np.clip(x0, lo + 1e-6 * (hi - lo), hi - 1e-6 * (hi - lo)))
            spec.append((n, float(lo), float(hi), x0, typ, dyn))

        both_tr = all(p["transiting"] for p in self.planets)
        dOm_b = cfg["dOm_bounds"] or ([-45.0, 45.0] if both_tr else [-180.0, 180.0])
        for p in self.planets:
            tag, unit = p["name"], MASS_UNITS[p["mass_unit"]]
            mb = p["mass_bounds"] or ([0.1, 3000.0] if p["mass_unit"] == "Mearth" else [3e-4, 10.0])
            mg = p["mass_guess"] or float(np.sqrt(mb[0] * mb[1]))
            add("log_q_" + tag, np.log10(mb[0] * unit / ms0), np.log10(mb[1] * unit / ms0),
                np.log10(mg * unit / ms0), 0.02, True)
            P0 = float(p["P"])
            Pb_ = p.get("P_bounds") or [P0 * (1 - p["P_range"]), P0 * (1 + p["P_range"])]
            add("P_" + tag, Pb_[0], Pb_[1], P0, 2e-5 * P0 / 2.5, True)
            add("phi_" + tag, 0.0, 1.0, self.phase_guess(p), 2e-4, True)
            if self.free_ecc:
                add("ecosw_" + tag, -self.ecc_max, self.ecc_max, p["ecosw"], 0.005, True)
                add("esinw_" + tag, -self.ecc_max, self.ecc_max, p["esinw"], 0.005, True)
            if p["transiting"]:
                bm = float(cfg["b_max"])
                add("b_" + tag, 0.0 if tag == self.ref_tag else -bm, bm, p["b"], 0.01, True)
            else:
                add("cosi_" + tag, -1.0, 1.0, p["cosi"], 0.005, True)
        add("dOm", dOm_b[0], dOm_b[1], 0.0, 0.5, True)
        add("mstar", max(0.05, ms0 - 6 * ss0), ms0 + 6 * ss0, ms0, None, True)
        add("rstar", max(0.05, rs0 - 6 * sr0), rs0 + 6 * sr0, rs0, None, True)
        if self.tt_jitter and self.tt:
            add("ln_ttjit", np.log(1e-5), np.log(0.1), np.log(1e-3))
        if self.mode == "photodyn":
            for p in self.planets:
                if p["transiting"]:
                    rp = float(p["rp"])
                    add("rp_" + p["name"], 0.2 * rp, min(3.0 * rp, 0.5), rp)
            add("q1", 0.0, 1.0, 0.3)
            add("q2", 0.0, 1.0, 0.3)
            pb = phc.get("prot_bounds", [4.0, 20.0])
            lnq0_min = float(phc.get("lnq0_min", np.log(0.1)))
            gstart = phc.get("gp_start") or {}
            for s in self.segments:
                g = gstart.get(str(s.seg), {})
                if s.use_gp:
                    add("s%d_ln_sig" % s.seg, np.log(0.1), np.log(50.0), g.get("ln_sig", np.log(7.0)))
                    add("s%d_ln_Prot" % s.seg, np.log(pb[0]), np.log(pb[1]),
                        g.get("ln_Prot", np.log(np.sqrt(pb[0] * pb[1]))))
                    add("s%d_ln_Q0" % s.seg, lnq0_min, 5.0, g.get("ln_Q0", 2.5))
                    add("s%d_ln_dQ" % s.seg, -10.0, 10.0, g.get("ln_dQ", 0.0))
                    add("s%d_f_gp" % s.seg, 0.001, 1.0, g.get("f_gp", 0.3))
                add("s%d_ln_jit" % s.seg, np.log(1e-3), np.log(10.0), g.get("ln_jit", np.log(0.05)))
                add("s%d_F0" % s.seg, -30.0, 30.0, g.get("F0", 0.0))
                if phc.get("dilution", "fixed") == "free":
                    add("s%d_D" % s.seg, 0.5, 1.5, 1.0)
        if self.rv is not None:
            if self.rv.use_gp:
                add("rv_ln_sig", np.log(0.05), np.log(50.0), np.log(30.0))
                if not self.rv_shared_prot_seg():
                    pb = rvc.get("prot_bounds", [4.0, 20.0])
                    add("rv_ln_Prot", np.log(pb[0]), np.log(pb[1]), np.log(np.sqrt(pb[0] * pb[1])))
                add("rv_ln_Q0", 0.0, 10.0, 2.0)
                add("rv_ln_dQ", -10.0, 10.0, 0.0)
                add("rv_f_gp", 0.001, 1.0, 0.4)
            for k in range(self.rv.n_inst):
                add("rv_off_%d" % k, -100.0, 100.0, 0.0)
            for k in range(self.rv.n_inst):
                add("rv_ln_jit_%d" % k, np.log(0.1), np.log(100.0), np.log(5.0))

        self.names = [s[0] for s in spec]
        self.lo = np.array([s[1] for s in spec])
        self.hi = np.array([s[2] for s in spec])
        self.x0 = np.array([s[3] for s in spec])
        self.typ = np.array([s[4] if s[4] else (s[2] - s[1]) / 20.0 for s in spec])
        self.ndim = len(spec)
        self.dyn_idx = np.array([i for i, s in enumerate(spec) if s[5]])
        self.nuis_idx = np.array([i for i, s in enumerate(spec) if not s[5]], dtype=int)
        self._cache = OrderedDict()
        self.fail = Counter()
        self.n_eval = 0

    def rv_shared_prot_seg(self):
        rvc = self.cfg.get("rv") or {}
        s = rvc.get("share_prot_with")
        if s is None or self.mode != "photodyn":
            return None
        if not any(seg.seg == int(s) and seg.use_gp for seg in self.segments):
            raise SystemExit(f"rv.share_prot_with = {s}: no segment with a GP with that number")
        return int(s)

    def phase_guess(self, p):
        """Starting phase from T0 or from the linear ephemeris of the mid-times."""
        P = float(p["P"])
        T0 = p["T0"]
        if T0 is None and p["name"] in getattr(self, "tt", {}):
            d = self.tt[p["name"]]
            Pf, Tf = np.polyfit(d["epoch"], d["t"], 1)
            T0 = Tf + np.ceil((self.t_start - Tf) / Pf) * Pf
            P = Pf
        if T0 is None:
            return 0.5
        return float(((T0 - self.t_start) / P) % 1.0)

    def idx(self, name):
        return self.names.index(name)

    def __getstate__(self):
        st = self.__dict__.copy()
        st["_cache"] = OrderedDict()
        return st

    # --- afgeleide grootheden ---------------------------------------------------
    def derive(self, x):
        p = dict(zip(self.names, x))
        ms, rs = p["mstar"], p["rstar"]
        d = dict(mstar=ms, rstar=rs, dOm=p["dOm"])
        for tag in self.tags:
            d["mp_" + tag] = 10 ** p["log_q_" + tag] * ms
            d["P_" + tag] = p["P_" + tag]
            d["T0_" + tag] = self.t_start + p["phi_" + tag] * p["P_" + tag]
            ec, es = (p["ecosw_" + tag], p["esinw_" + tag]) if self.free_ecc else (0.0, 0.0)
            e = float(np.hypot(ec, es))
            d["e_" + tag] = e
            d["w_" + tag] = float(np.degrees(np.arctan2(es, ec))) if e > 1e-6 else 90.0
            d["aR_" + tag] = a_over_rstar(d["P_" + tag], ms, d["mp_" + tag], rs)
            if "b_" + tag in p:
                d["i_" + tag] = inc_from_b(p["b_" + tag], d["aR_" + tag], e, d["w_" + tag])
                d["bconj_" + tag] = p["b_" + tag]
            else:
                d["i_" + tag] = float(np.degrees(np.arccos(np.clip(p["cosi_" + tag], -1.0, 1.0))))
                d["bconj_" + tag] = b_from_inc(d["i_" + tag], d["aR_" + tag], e, d["w_" + tag])
        shape = {k: p[k] for k in p if k.startswith("rp_") or k in ("q1", "q2")}
        return p, d, shape

    def lnprior(self, x, p, d):
        if np.any(x < self.lo) or np.any(x > self.hi):
            return -np.inf
        t1, t2 = self.tags
        if d["e_" + t1] >= self.ecc_max or d["e_" + t2] >= self.ecc_max:
            return -np.inf
        if not hill_ok(d["mp_" + t1], d["mp_" + t2], a_au(d["P_" + t1], d["mstar"], d["mp_" + t1]),
                       a_au(d["P_" + t2], d["mstar"], d["mp_" + t2]), d["mstar"]):
            return -np.inf
        for pl in self.planets:
            if not pl["transiting"] and pl["forbid_transit"] and abs(d["bconj_" + pl["name"]]) < 1.0:
                return -np.inf
        lp = -0.5 * ((p["mstar"] - self.mstar_prior[0]) / self.mstar_prior[1]) ** 2
        lp += -0.5 * ((p["rstar"] - self.rstar_prior[0]) / self.rstar_prior[1]) ** 2
        for pl in self.planets:
            if pl["rp_prior"] and "rp_" + pl["name"] in p:
                mu, sg = pl["rp_prior"]
                lp += -0.5 * ((p["rp_" + pl["name"]] - mu) / sg) ** 2
        if self.free_ecc:                   # uniform in e
            lp -= sum(np.log(max(d["e_" + t], 1e-3)) for t in self.tags)
        return lp

    def events(self, x, d, rv=True):
        key = (tuple(np.asarray(x, float)[self.dyn_idx].tolist()), rv)
        ev = self._cache.get(key)
        if ev is not None:
            self._cache.move_to_end(key)
            return ev
        ev = run_ttvfast(d, self.tags, self.t_start, self.t_end, self.dt,
                         rv_times=self.rv.t if (rv and self.rv is not None) else None)
        self._cache[key] = ev
        if len(self._cache) > self.CACHE_SIZE:
            self._cache.popitem(last=False)
        return ev

    def tt_residuals(self, ev, tag):
        """Observed - model [d] with the nearest model transit (requires TTV << P/2)."""
        tm = ev["times_" + tag]
        d = self.tt[tag]
        if len(tm) < 2:
            return None
        t = d["t"]
        j = np.clip(np.searchsorted(tm, t), 1, len(tm) - 1)
        near = np.where(np.abs(t - tm[j - 1]) < np.abs(t - tm[j]), tm[j - 1], tm[j])
        return t - near

    def lnlike_tt(self, ev, p):
        ll = 0.0
        jit2 = np.exp(2 * p["ln_ttjit"]) if "ln_ttjit" in p else 0.0
        for tag, d in self.tt.items():
            r = self.tt_residuals(ev, tag)
            if r is None:
                self.fail["tt_" + tag] += 1
                return -np.inf
            u = d["use"]
            var = d["sig_tot"][u] ** 2 + jit2
            ll += float(-0.5 * np.sum(r[u] ** 2 / var + np.log(2 * np.pi * var)))
        return ll

    def rv_ln_Prot(self, p):
        s = self.rv_shared_prot_seg()
        return p["s%d_ln_Prot" % s] if s is not None else p["rv_ln_Prot"]

    def seg_pars(self, p, seg):
        sp = {k: p.get("s%d_%s" % (seg.seg, k)) for k in SEG_KEYS}
        sp["ln_jit"] = p["s%d_ln_jit" % seg.seg]
        sp["F0"] = p["s%d_F0" % seg.seg]
        sp["D"] = p.get("s%d_D" % seg.seg, 1.0)
        return sp

    def photo_model(self, ev, d, shape, seg, sp):
        tot = np.zeros_like(seg.t)
        for pl in self.planets:
            if pl["transiting"]:
                tot = tot + seg.transits(ev, d, shape, pl["name"], sp["D"])
        return tot

    def lnprob(self, x, debug=False):
        self.n_eval += 1
        x = np.asarray(x, float)
        try:
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                p, d, shape = self.derive(x)
                lp = self.lnprior(x, p, d)
                if not np.isfinite(lp):
                    return -np.inf
                ev = self.events(x, d)
                ll = 0.0
                for seg in self.segments:
                    sp = self.seg_pars(p, seg)
                    l = seg.lnlike(seg.y - sp["F0"] - self.photo_model(ev, d, shape, seg, sp), sp)
                    if debug:
                        print(f"  segment {seg.seg}: lnL = {l:.1f}")
                    ll += l
                if self.segt:
                    r_, _ = segt_residuals(ev, self.segt)
                    l = float(-0.5 * np.sum(r_**2) - sum(np.log(2 * np.pi * abs(np.linalg.det(st["L"])))
                                                         for st in self.segt))
                    if debug:
                        print(f"  sector times: lnL = {l:.1f}")
                    ll += l
                if self.tt:
                    l = self.lnlike_tt(ev, p)
                    if debug:
                        print(f"  mid-times: lnL = {l:.1f}")
                    ll += l
                if self.rv is not None:
                    if ev["rv"] is None:
                        self.fail["ttvfast_rv"] += 1
                        return -np.inf
                    l = self.rv.lnlike(ev["rv"], p, self.rv_ln_Prot(p) if self.rv.use_gp else None)
                    if debug:
                        print(f"  RV: lnL = {l:.1f}")
                    ll += l
                tot = lp + ll
            if not np.isfinite(tot):
                self.fail["non-finite"] += 1
                return -np.inf
            return float(tot)
        except Exception as exc:
            self.fail[type(exc).__name__] += 1
            if debug:
                print(f"  error: {type(exc).__name__}: {exc}")
            return -np.inf

    def report_failures(self, label=""):
        if self.fail:
            print(f"  [failed evaluations{label}] " + ", ".join(f"{k}: {v}" for k, v in self.fail.most_common()))


# ===========================================================================
# Parallelle hulpfuncties
# ===========================================================================
_W = {}


def _init_worker(prob, x_full=None, idx=None):
    _W["prob"], _W["x"], _W["idx"] = prob, x_full, idx


def _lnprob_worker(x):
    return _W["prob"].lnprob(x)


def close_pool(pool):
    """terminate instead of close: no workers left behind, also after an interruption (Stop in the GUI, SIGTERM)."""
    if pool is not None:
        pool.terminate()
        pool.join()


def make_pool(nproc, prob, x_full=None, idx=None):
    if nproc <= 1:
        _init_worker(prob, x_full, idx)
        return None
    import multiprocessing as mp
    return mp.get_context("fork" if sys.platform != "win32" else "spawn").Pool(
        nproc, initializer=_init_worker, initargs=(prob, x_full, idx))


# ===========================================================================
# Global search, optimisation, MCMC
# ===========================================================================
# ===========================================================================
# Prefit (general version of toi3686_ttv_prefit.py)
# ===========================================================================
def nearest(tm, tq):
    j = np.clip(np.searchsorted(tm, tq), 1, len(tm) - 1)
    return np.where(np.abs(tq - tm[j - 1]) < np.abs(tq - tm[j]), tm[j - 1], tm[j])


def load_segment_times(tag, path, windows, hw):
    """sector T_ref sigma_T P_loc sigma_P rho (b_times.dat format). Window: the segment in the residual
    photometry (windows), otherwise T_ref +- hw."""
    out = []
    for row in np.atleast_2d(np.loadtxt(path, comments="#", usecols=(0, 1, 2, 3, 4, 5))):
        sec, T, sT, P, sP, rho = row
        C = np.array([[sT**2, rho * sT * sP], [rho * sT * sP, sP**2]])
        out.append(dict(tag=tag, seg=int(sec), T=T, P=P, L=np.linalg.cholesky(C),
                        win=windows.get(int(sec), (T - hw, T + hw))))
    return out


def segt_residuals(ev, segt):
    """Whitened residuals (T, P) per segment: local linear ephemeris of the model transits in the segment,
    evaluated at the epoch nearest to the measured T_ref (as btime_residuals in the v3 prefit)."""
    out, info = [], []
    for st in segt:
        tb = ev["times_" + st["tag"]]
        lo, hi = st["win"]
        m = (tb > lo) & (tb < hi)
        if m.sum() < 3:
            out += [30.0, 30.0]
            info.append((st["tag"], st["seg"], np.nan, np.nan))
            continue
        Pm, T0m = np.polyfit(np.arange(m.sum()), tb[m], 1)
        k = np.round((st["T"] - T0m) / Pm)
        dv = np.array([T0m + k * Pm - st["T"], Pm - st["P"]])
        out += list(np.linalg.solve(st["L"], dv))
        info.append((st["tag"], st["seg"], dv[0] * 24, dv[1]))
    return np.array(out), info


class Prefit:
    """Cheap objective for the global search for the right dynamical mode (as the v3 prefit):

      chi2 = sum_k chi2(mid-times k; ALL facilities, with error floor)
             + sum_k ((m_k - m_k,RV)/s_k)^2         RV prior from a Keplerian fit (planets with an ephemeris)
               or N-body RVs with profiled offsets (rv_term = 'profiled'; needed for a non-transiting
               planet)
             + w_phot * dchi2_phot                    template on the residual photometry, global depth
             + chi2(sector times and local periods)   b_times.dat format
    Free: log_q, P, phase, e-vector per planet; fixed (as v3): b/cos i, dOm, M*, R*."""

    def __init__(self, prob):
        self.prob = prob
        cfg = prob.cfg
        sc = cfg["search"]
        self.floor = float(cfg["midtimes"].get("floor_min") or 0.0) / 1440.0
        # --- mid-times: all facilities (the prefit uses no photometry of these transits) ----------------
        self.tt = {}
        for p in prob.planets:
            if p["transiting"] and p["midtimes"]:
                d = load_midtimes(resolve(cfg, p["midtimes"]), p["P"], "mid-times " + p["name"])
                Pl, Tl = np.polyfit(d["epoch"], d["t"], 1, w=1.0 / np.maximum(d["sig"], 1e-6))
                self.tt[p["name"]] = dict(t=d["t"], s=np.hypot(d["sig"], self.floor), lin=(Pl, Tl), n=d["epoch"])
        # --- free parameters and bounds ----------------------------------------------------------------
        self.free = []
        lo, hi = [], []
        for p in prob.planets:
            tag = p["name"]
            for n in ("log_q_", "P_", "phi_") + (("ecosw_", "esinw_") if prob.free_ecc else ()):
                self.free.append(prob.idx(n + tag))
        if sc.get("free_geometry", False):
            self.free += [i for i, n in enumerate(prob.names)
                          if n.startswith(("b_", "cosi_")) or n in ("dOm", "mstar", "rstar")]
        self.free = np.array(self.free)
        self.names = [prob.names[i] for i in self.free]
        x0 = prob.x0.copy()
        for i, n in zip(self.free, self.names):
            l, h = prob.lo[i], prob.hi[i]
            tag = n.split("_")[-1]
            pl = prob.pl.get(tag)
            if n.startswith("phi_"):
                win = pl.get("phase_window") or (sc.get("phase_window", 0.15) if tag in self.tt else 0.5)
                if tag in self.tt and win < 0.5:
                    Pl, Tl = self.tt[tag]["lin"]
                    c = ((Tl + np.ceil((prob.t_start - Tl) / Pl) * Pl - prob.t_start) / x0[prob.idx("P_" + tag)]) % 1
                    x0[i] = c
                    l, h = c - win, c + win            # may lie outside [0, 1): the phase is taken modulo 1
                else:
                    l, h = 0.0, 1.0
            elif n.startswith(("ecosw_", "esinw_")):
                em = float(pl["ecc_search"][0])
                l, h = -em, em
            lo.append(l)
            hi.append(h)
        self.lo, self.hi = np.array(lo), np.array(hi)
        self.x_fixed = x0
        self.wrap = np.array([n.startswith("phi_") for n in self.names])
        self.ecut = {p["name"]: float(p["ecc_search"][1]) for p in prob.planets}
        # --- RV-term -------------------------------------------------------------------------------------
        self.rv_prior = {}
        mode = sc.get("rv_term", "auto")
        if mode == "auto":     # Keplerian prior (v3) if both transit, otherwise N-body RVs (perturber unknown)
            if prob.rv is None:
                mode = "none"
            elif all(p["transiting"] for p in prob.planets) and self.tt:
                mode = "prior"
            else:
                mode = "profiled"
        self.rv_mode = mode
        if mode == "prior":
            self.rv_mass_prior()
        # --- residual photometry and template -----------------------------------------------------------
        phc = cfg.get("photometry") or {}
        self.phot_tags = [p["name"] for p in prob.planets if p["transiting"] and p.get("phot_term")]
        self.wphot = float(sc.get("phot_weight", 1.0))
        self.phot = []
        if phc.get("residuals_csv"):
            self.load_residuals(resolve(cfg, phc["residuals_csv"]), phc)
        # --- sector times and local periods ----------------------------------------------------------------
        self.segt = []
        for p in prob.planets:
            if p.get("segment_times"):
                self.load_segment_times(p["name"], resolve(cfg, p["segment_times"]), p)
        print(f"Prefit: {len(self.free)} free parameters ({', '.join(self.names)}); fixed: b/cos i, dOm, M*, R*"
              f"{' (except with free_geometry)' if sc.get('free_geometry') else ''}")
        for tag, d in self.tt.items():
            Pl, Tl = d["lin"]
            chi = float(np.sum(((d["t"] - (Tl + d["n"] * Pl)) / d["s"]) ** 2))
            print(f"  mid-times {tag}: {len(d['t'])} (all facilities), linear ephemeris chi2 = {chi:.1f}")
        if self.rv_prior:
            for tag, (m, s, K, sK) in self.rv_prior.items():
                print(f"  RV prior {tag}: K = {K:.1f} ± {sK:.1f} m/s -> m sin i = {m:.4g} ± {s:.2g} "
                      f"{prob.pl[tag]['mass_unit']}")
        elif self.rv_mode == "profiled":
            print("  RV term: N-body RVs with profiled offsets, fixed jitter "
                  f"{(cfg.get('rv') or {}).get('search_jitter', 10.0)} m/s")
        if self.phot:
            print(f"  residual photometry: segments {[ph['seg'] for ph in self.phot]}, template for "
                  f"{self.phot_tags or '-'}, weight {self.wphot}")
        for st in self.segt:
            print(f"  sector times {st['tag']} segment {st['seg']}: T = {st['T']:.4f}, P_loc = {st['P']:.4f}")

    # --- invoer ----------------------------------------------------------------------------------------------
    def rv_mass_prior(self):
        """Circular Keplerian fit of the RVs at the linear ephemerides (offset per instrument); prior on
        m sin i for planets with K/sigma_K > 3 (as v3 for c)."""
        prob = self.prob
        rv = prob.rv
        tags = [t for t in prob.tags if t in self.tt]
        X = np.zeros((len(rv.t), len(tags) + rv.n_inst))
        for j, tag in enumerate(tags):
            Pl, Tl = self.tt[tag]["lin"]
            X[:, j] = -np.sin(2 * np.pi * (rv.t - Tl) / Pl)
        X[np.arange(len(rv.t)), len(tags) + rv.idx] = 1.0
        W = 1.0 / rv.err**2
        C = np.linalg.inv(X.T @ (X * W[:, None]))
        beta = C @ (X.T @ (W * rv.rv))
        ms, sms = prob.mstar_prior
        for j, tag in enumerate(tags):
            K, sK = beta[j], np.sqrt(C[j, j])
            Pl = self.tt[tag]["lin"][0]
            unit = MASS_UNITS[prob.pl[tag]["mass_unit"]]
            fac = 1 / AUDAY_TO_MS / (2 * np.pi * K2_GAUSS / Pl) ** (1 / 3) * ms ** (2 / 3) / unit
            m = K * fac
            s = float(np.hypot(sK * fac, m * 2 / 3 * sms / ms))
            if K / sK > 3:
                self.rv_prior[tag] = (float(m), s, float(K), float(sK))
            else:
                print(f"  RV: K_{tag} = {K:.1f} ± {sK:.1f} m/s (< 3 sigma): no mass prior for {tag}")

    def load_residuals(self, path, phc):
        prob = self.prob
        d = np.loadtxt(path, delimiter=",", comments="#", ndmin=2)
        t, f, e, sec = to_btjd(d[:, 0]), d[:, 1], d[:, 2], d[:, 3].astype(int)
        ok = np.isfinite(f)
        if d.shape[1] > 4:
            ok &= d[:, 4] == 0                                   # flare-vlag
        for tag, tt in self.tt.items():                          # mask the transits of planets without a photometric term
            if tag in self.phot_tags:
                continue
            Pl, Tl = tt["lin"]
            n = np.round((t - Tl) / Pl)
            ok &= np.abs(t - (Tl + n * Pl)) > float(phc.get("mask_hours", 3.0)) / 24
        ms, rs = prob.mstar_prior[0], prob.rstar_prior[0]
        u = phc.get("ld_u", [0.4, 0.2])
        bin_min = float(phc.get("bin_min", 10.0))
        for s in np.unique(sec[ok]):
            m = ok & (sec == s)
            ts, fs, es = t[m], (f[m] - 1) * 1e3, e[m] * 1e3
            fs = fs - np.median(fs)
            es = es * max(np.std(fs) / np.median(es), 1.0)
            cad = float(np.median(np.diff(ts)))
            if cad < bin_min / 1440 * 0.5:
                w = 1 / es**2
                k = np.floor((ts - ts.min()) / (bin_min / 1440)).astype(int)
                keep = np.bincount(k) > 0
                Wb = np.bincount(k, w)[keep]
                ts, fs, es = np.bincount(k, ts * w)[keep] / Wb, np.bincount(k, fs * w)[keep] / Wb, 1 / np.sqrt(Wb)
                cad = bin_min / 1440
            tm = {}
            for tag in self.phot_tags:
                pl = prob.pl[tag]
                aR = a_over_rstar(pl["P"], ms, 0.0, rs)
                tm[tag] = self.template(cad, pl["rp"], aR, inc_from_b(pl["b"], aR, 0.0, 90.0), pl["P"], u)
            self.phot.append(dict(seg=int(s), t=ts, f=fs, w=1 / es**2, tm=tm, win=(ts.min(), ts.max())))
        self.null = float(sum(np.sum(ph["w"] * ph["f"] ** 2) for ph in self.phot))

    G = np.linspace(-0.3, 0.3, 3001)                             # time axis of the template [d]

    def template(self, cad, rp, aR, inc, P, u):
        import batman
        p = batman.TransitParams()
        p.t0, p.per, p.rp, p.a, p.inc, p.ecc, p.w = 0.0, P, rp, aR, inc, 0.0, 90.0
        p.limb_dark, p.u = "quadratic", list(u)
        m = batman.TransitModel(p, self.G, supersample_factor=7 if cad > 0.004 else 1, exp_time=cad)
        return (m.light_curve(p) - 1.0) * 1e3

    def load_segment_times(self, tag, path, pl):
        self.segt += load_segment_times(tag, path, {ph["seg"]: ph["win"] for ph in self.phot},
                                        float(pl.get("segment_halfwidth", 13.0)))

    # --- model ------------------------------------------------------------------------------------------------
    def full(self, v):
        x = self.x_fixed.copy()
        v = np.array(v, float)
        v[self.wrap] = v[self.wrap] % 1.0
        x[self.free] = v
        return x

    def components(self, v):
        prob = self.prob
        x = self.full(v)
        try:
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                p, d, _ = prob.derive(x)
                if not np.isfinite(prob.lnprior(x, p, d)):
                    return None
                if any(d["e_" + t] > self.ecut[t] for t in prob.tags):
                    return None
                ev = run_ttvfast(d, prob.tags, prob.t_start, prob.t_end, prob.dt,
                                 rv_times=prob.rv.t if (self.rv_mode == "profiled" and prob.rv is not None) else None)
        except Exception:
            return None
        span = prob.t_end - prob.t_start
        for tag in self.tt:
            if len(ev["times_" + tag]) < 0.8 * span / d["P_" + tag]:
                return None
        out = dict(ev=ev, d=d, rc={}, rm={})
        for tag, tt in self.tt.items():
            out["rc"][tag] = (tt["t"] - nearest(ev["times_" + tag], tt["t"])) / tt["s"]
        for tag, (m, s, _, _) in self.rv_prior.items():
            out["rm"][tag] = (d["mp_" + tag] / MASS_UNITS[prob.pl[tag]["mass_unit"]] - m) / s
        out["rv_chi2"] = 0.0
        if self.rv_mode == "profiled":
            if ev["rv"] is None:
                return None
            out["rv_chi2"] = prob.rv.profiled_chi2(ev["rv"], float((prob.cfg.get("rv") or {}).get("search_jitter",
                                                                                                    10.0)))
        # photometry: one global profiled depth per planet with a photometric term (as v3)
        out["mods"], out["A"], out["sn"] = {}, {}, {}
        for tag in self.phot_tags:
            tb = ev["times_" + tag]
            if len(tb) < 2:
                return None
            mods = [np.interp(ph["t"] - nearest(tb, ph["t"]), self.G, ph["tm"][tag]) for ph in self.phot]
            sdp = [float(np.sum(ph["w"] * mod * ph["f"])) for ph, mod in zip(self.phot, mods)]
            spp = [float(np.sum(ph["w"] * mod**2)) for ph, mod in zip(self.phot, mods)]
            out["mods"][tag] = mods
            out["A"][tag] = float(np.clip(sum(sdp) / sum(spp), 0.0, 1.5)) if sum(spp) > 0 else 0.0
            out["sn"][tag] = [a / np.sqrt(b) if b > 0 else 0.0 for a, b in zip(sdp, spp)] + \
                             [sum(sdp) / np.sqrt(sum(spp)) if sum(spp) > 0 else 0.0]
        return out

    def dchi2_phot(self, c, A=None):
        if not self.phot_tags:
            return 0.0
        tot = 0.0
        for k, ph in enumerate(self.phot):
            mod = sum((A[tag] if A else c["A"][tag]) * c["mods"][tag][k] for tag in self.phot_tags)
            tot += float(np.sum(ph["w"] * (ph["f"] - mod) ** 2))
        return tot - self.null

    def segt_residuals(self, ev):
        return segt_residuals(ev, self.segt)

    def objective(self, v):
        c = self.components(v)
        if c is None:
            return 1e9
        tot = sum(float(np.sum(r**2)) for r in c["rc"].values()) + sum(r**2 for r in c["rm"].values())
        tot += c["rv_chi2"] + self.wphot * self.dchi2_phot(c)
        if self.segt:
            tot += float(np.sum(self.segt_residuals(c["ev"])[0] ** 2))
        return float(tot)

    def residual_vector(self, q):
        """For least_squares: free parameters + one depth per planet with a photometric term."""
        nA = len(self.phot_tags)
        v, A = q[:len(self.free)], dict(zip(self.phot_tags, q[len(self.free):]))
        n = sum(len(t["t"]) for t in self.tt.values()) + len(self.rv_prior) + \
            sum(len(ph["t"]) for ph in self.phot) * (1 if nA else 0) + 2 * len(self.segt) + \
            (len(self.prob.rv.t) if self.rv_mode == "profiled" else 0)
        c = self.components(v)
        if c is None:
            return np.full(n, 30.0)
        out = [r for r in c["rc"].values()] + [[r] for r in c["rm"].values()]
        if self.rv_mode == "profiled":
            rv = self.prob.rv
            jit = float((self.prob.cfg.get("rv") or {}).get("search_jitter", 10.0))
            w = 1.0 / (rv.err**2 + jit**2)
            r = rv.rv - c["ev"]["rv"]
            for k in range(rv.n_inst):
                mk = rv.idx == k
                r[mk] -= np.sum(w[mk] * r[mk]) / np.sum(w[mk])
            out.append(r * np.sqrt(w))
        if nA:
            wb = np.sqrt(self.wphot)
            for k, ph in enumerate(self.phot):
                mod = sum(A[tag] * c["mods"][tag][k] for tag in self.phot_tags)
                out.append(wb * (ph["f"] - mod) * np.sqrt(ph["w"]))
        if self.segt:
            out.append(self.segt_residuals(c["ev"])[0])
        return np.concatenate([np.atleast_1d(o) for o in out])

    def diagnose(self, v):
        c = self.components(v)
        if c is None:
            return None
        prob, d, ev = self.prob, c["d"], c["ev"]
        dg = dict(chi2_tt={t: float(np.sum(r**2)) for t, r in c["rc"].items()},
                  rms_tt_min={t: float(np.sqrt(np.mean((r * self.tt[t]["s"]) ** 2)) * 1440) for t, r in c["rc"].items()},
                  chi2_rvprior={t: float(r**2) for t, r in c["rm"].items()}, chi2_rv_profiled=c["rv_chi2"],
                  dchi2_phot=self.dchi2_phot(c), A=c["A"], SN=c["sn"])
        if self.segt:
            r, info = self.segt_residuals(ev)
            dg["chi2_segt"] = float(np.sum(r**2))
            dg["segt"] = [dict(planet=t, seg=s, dT_h=dT, dP=dP) for t, s, dT, dP in info]
        else:
            dg["chi2_segt"] = 0.0
        dg["total"] = float(sum(dg["chi2_tt"].values()) + sum(dg["chi2_rvprior"].values()) + c["rv_chi2"] +
                            self.wphot * dg["dchi2_phot"] + dg["chi2_segt"])
        for tag in prob.tags:
            pl = prob.pl[tag]
            r = dict(mass=d["mp_" + tag] / MASS_UNITS[pl["mass_unit"]], e=d["e_" + tag], P_osc=d["P_" + tag])
            if pl["transiting"]:
                e = mean_ephemeris(ev["times_" + tag], ev["epoch_" + tag])
                if e:
                    r.update(P_mean=e["P"], TTV_halfamp_h=e["oc_halfamp_min"] / 60)
            dg[tag] = r
        dg["x"] = dict(zip(self.names, map(float, self.full(v)[self.free])))
        return dg

    def start_vector(self, v, dg):
        """Full parameter vector for the main model: free values, fixed values, and Rp/R* from the depth."""
        x = self.full(v)
        for tag in self.phot_tags:
            if "rp_" + tag in self.prob.names:
                x[self.prob.idx("rp_" + tag)] = float(self.prob.pl[tag]["rp"] * np.sqrt(np.clip(dg["A"][tag], 0.25, 1.5)))
        return np.clip(x, self.prob.lo, self.prob.hi)

    def vector_from_start(self, path):
        x = apply_start(self.prob, self.x_fixed.copy(), path, self.prob.cfg, quiet=True)
        v = x[self.free].copy()
        for k, n in enumerate(self.names):              # put the phase inside the search window
            if self.wrap[k]:
                v[k] = v[k] + np.round((0.5 * (self.lo[k] + self.hi[k]) - v[k]))
        return np.clip(v, self.lo, self.hi)


def _prefit_obj(v):
    return _W["pre"].objective(v)


def _init_prefit_worker(pre):
    _W["pre"] = pre


def run_prefit(prob, out, nproc=1):
    """Differential evolution (with checkpoints and injection) + polishing of distinct solutions."""
    from scipy.optimize import least_squares
    from scipy.optimize._differentialevolution import DifferentialEvolutionSolver
    sc = prob.cfg["search"]
    pre = Prefit(prob)
    _W["pre"] = pre
    B = list(zip(pre.lo, pre.hi))
    ck_path = os.path.join(out, sc.get("checkpoint") or "prefit_checkpoint.npz")
    maxiter = int(sc["maxiter"])
    init, gen0 = "sobol", 0
    if os.path.isfile(ck_path):
        ck = np.load(ck_path, allow_pickle=True)
        if ck["population"].shape[1] == len(B) and list(ck["names"]) == pre.names:
            init, gen0 = ck["population"], int(ck["generation"])
            print(f"  resuming {ck_path} after {gen0} generations (best {ck['energies'].min():.1f})")
            if gen0 >= maxiter:
                print(f"  [note] maxiter {maxiter} <= {gen0} completed generations: only injection and polishing. "
                      "For a new search: remove the checkpoint or increase maxiter.")
        else:
            print(f"  [note] {ck_path} belongs to other parameters; new search")
    pool = None
    if nproc > 1:
        import multiprocessing as mp
        pool = mp.get_context("fork" if sys.platform != "win32" else "spawn").Pool(
            nproc, initializer=_init_prefit_worker, initargs=(pre,))
    results = []
    try:
        kw = dict(popsize=int(sc["popsize"]), init=init, strategy=sc.get("strategy", "best1bin"),
                  mutation=(0.5, 1.0), recombination=0.7, tol=0, polish=False,
                  updating="deferred" if pool else "immediate", workers=pool.map if pool else 1,
                  maxiter=max(maxiter, 1))
        seed = int(sc.get("seed", 1)) + gen0
        try:
            solver = DifferentialEvolutionSolver(_prefit_obj, B, rng=seed, **kw)
        except TypeError:
            solver = DifferentialEvolutionSolver(_prefit_obj, B, seed=seed, **kw)
        print(f"\nGlobal search: population {len(solver.population)} members, strategy {kw['strategy']}, "
              f"generations {gen0} -> {maxiter}, {nproc} process(es)", flush=True)
        inj = sc.get("init_json") or []
        if inj:
            if not np.all(np.isfinite(solver.population_energies)):
                solver.population_energies[:] = solver._calculate_population_energies(solver.population)
            worst = np.argsort(solver.population_energies)[::-1]
            for k, path in enumerate(inj):
                v = pre.vector_from_start(resolve(prob.cfg, path))
                i = worst[k]
                solver.population[i] = solver._unscale_parameters(v)
                solver.population_energies[i] = pre.objective(v)
                print(f"  {path} inserted into the population: chi2_prefit = {solver.population_energies[i]:.1f}")
        t0 = time.time()
        for gen in range(gen0, maxiter):
            next(solver)
            if (gen + 1) % 5 == 0 or gen + 1 == maxiter:
                np.savez(ck_path, population=solver._scale_parameters(solver.population),
                         energies=solver.population_energies, generation=gen + 1, names=np.array(pre.names))
                e = np.sort(solver.population_energies)
                print(f"  generation {gen + 1:4d}: best {e[0]:9.1f}  median {np.median(e):9.1f}  "
                      f"({time.time() - t0:.0f} s)", flush=True)
        pop = solver._scale_parameters(solver.population)
        en = np.array(solver.population_energies)
        # --- polishing of mutually distinct solutions (phase > 0.02 or P > 1e-3 relative) -----------------------
        top = int(sc.get("top", 10))
        iph = [k for k, n in enumerate(pre.names) if n.startswith("phi_")]
        iP = [k for k, n in enumerate(pre.names) if n.startswith("P_")]
        picked = []
        for i in np.argsort(en):
            if all(any(abs(((pop[i, k] - pop[j, k]) + 0.5) % 1 - 0.5) > 0.02 for k in iph) or
                   any(abs(pop[i, k] / pop[j, k] - 1) > 1e-3 for k in iP) for j in picked):
                picked.append(i)
            if len(picked) == top:
                break
        nA = len(pre.phot_tags)
        lo = np.r_[pre.lo, np.zeros(nA)]
        hi = np.r_[pre.hi, np.full(nA, 1.5)]
        typ = np.array([prob.typ[i] for i in pre.free])
        xs = np.r_[np.maximum(typ, 1e-6) * 5, np.full(nA, 0.05)]
        print(f"\nPolishing {len(picked)} solutions (max. {sc.get('polish_nfev', 150)} evaluations each):",
              flush=True)
        for i in picked:
            c = pre.components(pop[i])
            A0 = [c["A"][t] for t in pre.phot_tags] if c else [0.5] * nA
            q0 = np.clip(np.r_[pop[i], np.maximum(A0, 0.05)], lo + 1e-9, hi - 1e-9)
            r = least_squares(pre.residual_vector, q0, bounds=(lo, hi), x_scale=xs, diff_step=1e-6,
                              max_nfev=int(sc.get("polish_nfev", 150)))
            dg = pre.diagnose(r.x[:len(pre.free)])
            if dg is None:
                continue
            dg["_v"] = r.x[:len(pre.free)]
            results.append(dg)
            print(f"  {len(results)}/{len(picked)}: total {dg['total']:.1f}", flush=True)
    finally:
        close_pool(pool)
    results.sort(key=lambda r: r["total"])
    print("\nPolished solutions, best first:")
    for dg in results:
        parts = [f"total {dg['total']:7.1f}"]
        parts += [f"chi2_{t} {v:.1f} (rms {dg['rms_tt_min'][t]:.1f} min)" for t, v in dg["chi2_tt"].items()]
        parts += [f"prior m_{t} {v:.1f}" for t, v in dg["chi2_rvprior"].items()]
        if pre.rv_mode == "profiled":
            parts.append(f"RV {dg['chi2_rv_profiled']:.1f}")
        if pre.phot_tags:
            parts.append(f"dchi2_phot {dg['dchi2_phot']:.1f} (A " +
                         ", ".join(f"{t} {a:.2f}" for t, a in dg["A"].items()) + ")")
        if pre.segt:
            parts.append(f"sector times {dg['chi2_segt']:.1f}")
        parts += [f"m_{t} {dg[t]['mass']:.3g} e_{t} {dg[t]['e']:.3f}" for t in prob.tags]
        parts += [f"TTV_{t} {dg[t]['TTV_halfamp_h']:.2f} h" for t in prob.tags if "TTV_halfamp_h" in dg[t]]
        print("  " + " | ".join(parts))
    clean = [{k: v for k, v in dg.items() if k != "_v"} for dg in results]
    with open(os.path.join(out, "prefit_results.json"), "w") as fh:
        json.dump(dict(t_start=prob.t_start, t_end=prob.t_end, rv_term=pre.rv_mode,
                       rv_prior={t: dict(m=m, s=s, K=K, sK=sK) for t, (m, s, K, sK) in pre.rv_prior.items()},
                       results=clean), fh, indent=2, default=float)
    if not results:
        raise SystemExit("prefit: no usable solution")
    best = results[0]
    x = pre.start_vector(best["_v"], best)
    with open(os.path.join(out, "prefit_start.json"), "w") as fh:
        json.dump(start_dict(prob, x), fh, indent=2)
    print(f"  -> {os.path.join(out, 'prefit_results.json')}, prefit_start.json")
    return x, best["total"]


def prefit_eval(prob, path):
    """Check: prefit objective at a start file (without a search)."""
    pre = Prefit(prob)
    v = pre.vector_from_start(path)
    dg = pre.diagnose(v)
    print(json.dumps({k: v for k, v in dg.items() if k != "x"}, indent=1, default=float))
    return dg


def optimize(prob, x, free=None, maxiter=200, label="", pool=None):
    """L-BFGS-B in scaled coordinates with a parallel finite-difference gradient (as v3)."""
    x = np.asarray(x, float).copy()
    free = np.arange(prob.ndim) if free is None else np.asarray(free)
    if len(free) == 0 or maxiter <= 0:
        return x, prob.lnprob(x)
    lo, hi, typ = prob.lo[free], prob.hi[free], prob.typ[free]
    u_hi = (hi - lo) / typ
    h = 1e-4
    n_eval = [0]

    def to_x(u):
        xx = x.copy()
        xx[free] = np.clip(lo + u * typ, lo, hi)
        return xx

    def evaluate(us):
        xs = [to_x(u) for u in us]
        n_eval[0] += len(xs)
        if pool is not None:
            vals = pool.map(_lnprob_worker, xs, chunksize=max(1, len(xs) // (4 * pool._processes)))
        else:
            vals = [prob.lnprob(xx) for xx in xs]
        return np.array([-v if np.isfinite(v) else np.inf for v in vals])

    def f_and_g(u):
        steps = np.where(u + h <= u_hi, h, -h)
        us = [u] + [u + s * e_i for s, e_i in zip(steps, np.eye(len(free)))]
        f = evaluate(us)
        g = (f[1:] - f[0]) / steps
        return f[0], np.where(np.isfinite(g), g, 0.0)

    t0 = time.time()
    u0 = np.clip((x[free] - lo) / typ, 0.0, u_hi)
    f0, g0 = f_and_g(u0)
    if not np.isfinite(f0):
        print(f"  {label}: starting point has lnP = -inf; skipped")
        return x, -np.inf
    fscale = max(float(np.linalg.norm(g0)), 1.0)
    first = [True]

    def obj(u):
        if first[0] and np.array_equal(u, u0):
            first[0] = False
            return 0.0, g0 / fscale
        f, g = f_and_g(u)
        return ((f - f0) / fscale if np.isfinite(f) else 1e10), g / fscale

    res = minimize(obj, u0, jac=True, method="L-BFGS-B", bounds=list(zip(np.zeros_like(u_hi), u_hi)),
                   options=dict(maxiter=maxiter, ftol=1e-15, gtol=1e-8))
    f_new = f0 + res.fun * fscale
    if f_new < f0:
        x[free] = to_x(res.x)[free]
    else:
        f_new = f0
    dt = time.time() - t0
    print(f"  {label}: lnP {-f0:.1f} -> {-f_new:.1f}  ({res.nit} iterations, {n_eval[0]} evaluations, "
          f"{dt:.0f} s = {1e3 * dt / max(n_eval[0], 1):.1f} ms/evaluation; {res.message})", flush=True)
    return x, float(-f_new)


def hessian_init(prob, x_ml, nw, pool, rng, out_dir):
    """Walkers from the Laplace approximation N(x_ML, (-H)^-1) (as v3, --init-hessian)."""
    t0 = time.time()
    lo, hi, nd = prob.lo, prob.hi, prob.ndim
    span = hi - lo

    def lnp_many(xs):
        if pool is not None:
            vals = pool.map(_lnprob_worker, xs, chunksize=max(1, len(xs) // (4 * pool._processes)))
        else:
            vals = [prob.lnprob(xx) for xx in xs]
        return np.array([v if np.isfinite(v) else -np.inf for v in vals])

    def shifted(steps):
        xs = []
        for st in steps:
            xx = x_ml.copy()
            for k in range(0, len(st), 2):
                xx[st[k]] += st[k + 1]
            xs.append(xx)
        return xs

    f0 = prob.lnprob(x_ml)
    d = 0.1 * prob.typ.copy()
    drop = np.full(nd, np.nan)
    for it in range(6):
        ok = (x_ml - d > lo) & (x_ml + d < hi)
        idx = np.where(ok)[0]
        v = lnp_many(shifted([(i, d[i]) for i in idx] + [(i, -d[i]) for i in idx]))
        drop[idx] = f0 - 0.5 * (v[:len(idx)] + v[len(idx):])
        done = True
        for k, i in enumerate(idx):
            dr = drop[i]
            if not np.isfinite(dr) or dr > 2.0:
                d[i] *= 0.3 if not np.isfinite(dr) else max(0.1, np.sqrt(0.5 / dr))
                done = False
            elif dr < 0.1:
                d[i] *= min(10.0, np.sqrt(0.5 / max(dr, 1e-4)))
                done = False
        for i in np.where(~ok)[0]:
            if d[i] > 1e-6 * span[i]:
                d[i] *= 0.3
                done = False
        if done:
            break
    inner = np.where((x_ml - d > lo) & (x_ml + d < hi) & np.isfinite(drop) & (drop > 0))[0]
    edge = np.setdiff1d(np.arange(nd), inner)
    h = 0.5 * d[inner]
    m = len(inner)
    vd = lnp_many(shifted([(inner[a], h[a]) for a in range(m)] + [(inner[a], -h[a]) for a in range(m)]))
    A = np.zeros((m, m))
    A[np.arange(m), np.arange(m)] = -(vd[:m] + vd[m:] - 2.0 * f0)
    pairs = [(a, b) for a in range(m) for b in range(a + 1, m)]
    st = []
    for a, b in pairs:
        i, j = inner[a], inner[b]
        st += [(i, h[a], j, h[b]), (i, h[a], j, -h[b]), (i, -h[a], j, h[b]), (i, -h[a], j, -h[b])]
    vo = lnp_many(shifted(st)).reshape(-1, 4) if st else np.zeros((0, 4))
    off = -(vo[:, 0] - vo[:, 1] - vo[:, 2] + vo[:, 3]) / 4.0
    for (a, b), o in zip(pairs, off):
        A[a, b] = A[b, a] = o if np.isfinite(o) else 0.0
    lam, V = np.linalg.eigh(A)
    floor = 1e-3 * lam.max()
    cov = ((V / np.maximum(lam, floor)) @ V.T) * np.outer(h, h)
    print(f"  Hessian: {m} parameters ({len(edge)} at a bound treated separately), {time.time() - t0:.0f} s")
    L = np.linalg.cholesky(cov + 1e-30 * np.eye(m))
    thr = f0 - (nd / 2.0 + 10.0 * np.sqrt(nd))
    pos = np.empty((nw, nd))
    todo = np.arange(nw)
    scale = 1.0
    for it in range(8):
        cand = np.repeat(x_ml[None, :], len(todo), axis=0)
        cand[:, inner] += scale * (rng.standard_normal((len(todo), m)) @ L.T)
        for i in edge:
            z = rng.standard_normal(len(todo))
            sgn = 1.0 if x_ml[i] - lo[i] < hi[i] - x_ml[i] else -1.0
            cand[:, i] += sgn * np.abs(z) * max(0.5 * d[i], 0.01 * span[i])
        cand = np.clip(cand, lo + 1e-9 * span, hi - 1e-9 * span)
        v = lnp_many(list(cand))
        good = np.isfinite(v) & (v > thr)
        pos[todo[good]] = cand[good]
        todo = todo[~good]
        if len(todo) == 0:
            break
        if it >= 2:
            scale *= 0.7
    if len(todo):
        pos[todo] = x_ml + 1e-4 * span * rng.standard_normal((len(todo), nd))
    if out_dir:
        np.savez(os.path.join(out_dir, "laplace.npz"), names=np.array([prob.names[i] for i in inner]), cov=cov,
                 x_ml=x_ml)
    return pos


def run_mcmc(prob, x_ml, out, nproc):
    import emcee
    mc = prob.cfg["mcmc"]
    nw = int(mc.get("nwalkers") or 0) or 4 * prob.ndim
    if nw < 2 * prob.ndim + 2:
        print(f"  [note] nwalkers {nw} < 2 ndim + 2; increased to {2 * prob.ndim + 2}")
        nw = 2 * prob.ndim + 2
    nw += nw % 2
    steps = int(mc.get("steps", 3000))
    span = prob.hi - prob.lo
    rng = np.random.default_rng(42)
    backend, initial = None, "start"
    bpath = os.path.join(out, mc["backend"]) if mc.get("backend") else None
    if bpath:
        try:
            import h5py  # noqa: F401
            backend = emcee.backends.HDFBackend(bpath)
            npath = bpath + ".names.json"
            if os.path.isfile(bpath) and backend.iteration > 0:
                old = json.load(open(npath)) if os.path.isfile(npath) else None
                if backend.shape != (nw, prob.ndim) or (old is not None and old != prob.names):
                    raise SystemExit(f"{bpath} belongs to another configuration (walkers/parameters); "
                                     "choose another back-end name")
                print(f"  resuming {bpath} after {backend.iteration} steps")
                initial = None
            else:
                backend.reset(nw, prob.ndim)
                json.dump(prob.names, open(npath, "w"))
        except ImportError:
            print("  [warning] h5py is missing; no back-end")
            backend = None
    moves = [(emcee.moves.DEMove(sigma=1e-12), 0.8), (emcee.moves.DESnookerMove(), 0.2)]
    print(f"\nMCMC: {nw} walkers x {steps} steps (ndim={prob.ndim}, {nproc} process(es))", flush=True)
    pool = make_pool(nproc, prob)
    try:
        if isinstance(initial, str):
            if mc.get("init_hessian", True):
                print("  starting positions from the Laplace approximation")
                initial = hessian_init(prob, x_ml, nw, pool, rng, out)
            else:
                initial = np.clip(x_ml + 1e-4 * span * rng.standard_normal((nw, prob.ndim)),
                                  prob.lo + 1e-9 * span, prob.hi - 1e-9 * span)
        sam = emcee.EnsembleSampler(nw, prob.ndim, _lnprob_worker if pool is not None else prob.lnprob,
                                    pool=pool, moves=moves, backend=backend)
        sam.random_state = np.random.RandomState(42).get_state()
        t0 = time.time()
        for k, _ in enumerate(sam.sample(initial, iterations=steps, progress=False)):
            if (k + 1) % 50 == 0 or k + 1 == steps:
                el = time.time() - t0
                print(f"  MCMC step {k + 1}/{steps}  ({el / (k + 1):.2f} s/step, ~{el / (k + 1) * (steps - k - 1) / 60:.0f} min to go)"
                      f"  acceptance {np.mean(sam.acceptance_fraction):.3f}", flush=True)
    finally:
        close_pool(pool)
    n_it = sam.iteration
    tau = sam.get_autocorr_time(quiet=True)
    if not np.any(np.isfinite(tau)):
        tau = np.full(prob.ndim, float(n_it))
    tau_max = float(np.nanmax(tau))
    burn = mc.get("burn")
    burn = int(burn) if burn is not None else int(min(3.0 * tau_max, 0.5 * n_it))
    thin = max(1, int(0.5 * np.nanmin(tau)))
    chain = sam.get_chain(discard=burn, thin=thin, flat=True)
    acc = float(np.mean(sam.acceptance_fraction))
    conv = bool(n_it - burn > 50 * tau_max)
    print(f"  acceptance {acc:.3f}  tau_max {tau_max:.0f}  burn {burn}  thin {thin}  {len(chain)} samples"
          f"{'' if conv else '  [WARNING: probably not converged; extend the chain]'}")
    diag = dict(steps=int(n_it), nwalkers=nw, acceptance=acc, tau_max=tau_max, burn=burn, thin=thin,
                converged=conv, n_samples=int(len(chain)), tau=dict(zip(prob.names, map(float, tau))))
    return chain, diag


# ===========================================================================
# Derived quantities and output
# ===========================================================================
def derived(prob, x, ev=None):
    p, d, shape = prob.derive(x)
    if ev is None:
        ev = prob.events(x, d)
    out = dict(mstar=d["mstar"], rstar=d["rstar"], dOm=d["dOm"],
               i_mut=mutual_inclination(d["i_" + prob.tags[0]], d["i_" + prob.tags[1]], d["dOm"]))
    for pl in prob.planets:
        tag, unit = pl["name"], pl["mass_unit"]
        r = dict(mass=d["mp_" + tag] / MASS_UNITS[unit], mass_unit=unit, q=d["mp_" + tag] / d["mstar"],
                 mass_Mearth=d["mp_" + tag] / MEARTH_MSUN, mass_Mjup=d["mp_" + tag] / MJUP_MSUN,
                 P_osc=d["P_" + tag], T0_osc=d["T0_" + tag], e=d["e_" + tag], w=d["w_" + tag],
                 i=d["i_" + tag], b_conj=d["bconj_" + tag], aR=d["aR_" + tag],
                 K=k_semi_amplitude(d["mp_" + tag], d["mstar"], d["P_" + tag], d["i_" + tag], d["e_" + tag]))
        if pl["transiting"]:
            e = mean_ephemeris(ev["times_" + tag], ev["epoch_" + tag], t_ref=prob.t_mid)
            if e:
                r.update(P_mean=e["P"], T0_mean=e["T0_ref"], epoch_ref=e["epoch_ref"],
                         TTV_halfamp_min=e["oc_halfamp_min"], TTV_rms_min=e["oc_rms_min"])
            if "rp_" + tag in shape:
                rn, rs = RADIUS_UNITS[unit]
                r["rp_Rs"] = shape["rp_" + tag]
                r["Rp"] = shape["rp_" + tag] * d["rstar"] * rs
                r["Rp_unit"] = rn
            if tag in prob.tt:
                res = prob.tt_residuals(ev, tag)
                if res is not None:
                    u = prob.tt[tag]["use"]
                    r["midtimes"] = dict(n=int(u.sum()), rms_min=float(np.sqrt(np.mean(res[u] ** 2)) * 1440),
                                         chi2=float(np.sum((res[u] / prob.tt[tag]["sig_tot"][u]) ** 2)),
                                         max_abs_min=float(np.max(np.abs(res[u])) * 1440) if u.any() else 0.0)
        else:
            ct = ev["conj_" + tag]
            if len(ct) > 1:
                r["P_mean_conj"] = float(np.polyfit(np.arange(len(ct)), ct, 1)[0])
        out[tag] = r
    t1, t2 = prob.tags
    out["period_ratio_mean"] = (out[t2].get("P_mean") or out[t2].get("P_mean_conj") or out[t2]["P_osc"]) / \
                               (out[t1].get("P_mean") or out[t1].get("P_mean_conj") or out[t1]["P_osc"])
    return out


def mass_posteriors(prob, chain):
    ms = chain[:, prob.idx("mstar")]
    out = {}
    for pl in prob.planets:
        tag, unit = pl["name"], pl["mass_unit"]
        q = 10 ** chain[:, prob.idx("log_q_" + tag)]
        for k, v in (("q_" + tag, q), ("m_%s_%s" % (tag, unit), q * ms / MASS_UNITS[unit])):
            pc = np.percentile(v, [16, 50, 84])
            out[k] = dict(median=float(pc[1]), lo=float(pc[1] - pc[0]), hi=float(pc[2] - pc[1]))
    return out


def start_dict(prob, x):
    st = dict(t_start=prob.t_start, source="photodyn2p " + VERSION, mode=prob.mode)
    st.update({n: float(v) for n, v in zip(prob.names, x)})
    for tag in prob.tags:
        st["T0_" + tag] = prob.t_start + st["phi_" + tag] * st["P_" + tag]
    return st


def apply_start(prob, x, path, cfg, quiet=False):
    with open(path) as fh:
        st = json.load(fh)
    t_st = st.get("t_start")
    x = x.copy()
    n_set = 0
    ms = st.get("mstar", prob.x0[prob.idx("mstar")])
    if "dOm" not in st and "dOm_c" in st:                   # start files of toi3686 v3
        st["dOm"] = st["dOm_c"]
    for pl in prob.planets:
        tag = pl["name"]
        if "log_q_" + tag not in st and "log_mp_" + tag in st:
            st["log_q_" + tag] = st["log_mp_" + tag] + np.log10(MASS_UNITS[pl["mass_unit"]] / ms)
        if "T0_" + tag in st and "P_" + tag in st:          # recompute the phase for our t_start
            st["phi_" + tag] = ((st["T0_" + tag] - prob.t_start) / st["P_" + tag]) % 1.0
        if not quiet and t_st is not None and abs(t_st - prob.t_start) > 1e-5 and ("P_" + tag) in st:
            print(f"  [warning] t_start of the start file ({t_st:.5f}) differs from this run "
                  f"({prob.t_start:.5f}): osculating elements hold at their own t_start; set the same t_start in the "
                  "configuration for an exact transfer")
    for k, v in st.items():
        if k in prob.names and isinstance(v, (int, float)):
            i = prob.idx(k)
            if not quiet and not (prob.lo[i] <= v <= prob.hi[i]):
                print(f"  [warning] start {k} = {v:.6g} outside [{prob.lo[i]:.6g}, {prob.hi[i]:.6g}]; clipped")
            x[i] = float(np.clip(v, prob.lo[i] + 1e-9 * (prob.hi[i] - prob.lo[i]),
                                 prob.hi[i] - 1e-9 * (prob.hi[i] - prob.lo[i])))
            n_set += 1
    if not quiet:
        print(f"  {n_set} of {prob.ndim} parameters from {path}")
    return x


def fmt_summary(prob, x, lnp, der, post=None, diag=None):
    L = [f"photodyn2p {VERSION} - {prob.cfg['name']} - mode {prob.mode}", "=" * 70,
         f"lnP = {lnp:.2f}   ndim = {prob.ndim}   t_start = {prob.t_start:.5f}   dt = {prob.dt:.4f} d", "",
         f"Star: M* = {der['mstar']:.4f} Msun, R* = {der['rstar']:.4f} Rsun", ""]
    for pl in prob.planets:
        r = der[pl["name"]]
        L.append(f"Planet {pl['name']} ({'transiting' if pl['transiting'] else 'non-transiting'}):")
        L.append(f"  mass   = {r['mass']:.4g} {r['mass_unit']}   (m/M* = {r['q']:.4g}; {r['mass_Mearth']:.3f} Mearth)")
        L.append(f"  P_osc  = {r['P_osc']:.6f} d   T0_osc = {r['T0_osc']:.5f}   (at t_start, Jacobi)")
        if "P_mean" in r:
            L.append(f"  P_mean = {r['P_mean']:.6f} d   T0_mean = {r['T0_mean']:.5f} (epoch {r['epoch_ref']})   "
                     f"TTV half-amplitude {r['TTV_halfamp_min']:.1f} min")
        L.append(f"  e = {r['e']:.4f}   w = {r['w']:.1f} deg   i = {r['i']:.2f} deg   b(conj) = {r['b_conj']:.3f}   "
                 f"a/R* = {r['aR']:.3f}   K = {r['K']:.2f} m/s")
        if "Rp" in r:
            L.append(f"  Rp/R*  = {r['rp_Rs']:.5f}   Rp = {r['Rp']:.3f} {r['Rp_unit']}")
        if "midtimes" in r:
            m = r["midtimes"]
            L.append(f"  mid-times: n = {m['n']}, rms = {m['rms_min']:.2f} min, max = {m['max_abs_min']:.1f} min, "
                     f"chi2 = {m['chi2']:.1f}")
        L.append("")
    L.append(f"dOmega = {der['dOm']:.2f} deg   mutual inclination = {der['i_mut']:.2f} deg   "
             f"period ratio (mean) = {der['period_ratio_mean']:.5f}")
    if diag:
        L += ["", f"MCMC: {diag['nwalkers']} walkers x {diag['steps']} steps, acceptance {diag['acceptance']:.3f}, "
                  f"tau_max {diag['tau_max']:.0f}, burn {diag['burn']}, converged = {diag['converged']}"]
    if post:
        L += ["", "Posterior (median +84/-16):"]
        for k, v in post.items():
            L.append(f"  {k:18s} {v['median']:.8g}  +{v['hi']:.4g} -{v['lo']:.4g}")
    return "\n".join(L) + "\n"


# ===========================================================================
# Figuren
# ===========================================================================
def plot_oc(prob, x, path):
    p, d, _ = prob.derive(x)
    ev = run_ttvfast(d, prob.tags, prob.t_start, prob.t_end, prob.dt)
    trs = [pl["name"] for pl in prob.planets if pl["transiting"]]
    fig, axs = plt.subplots(len(trs), 1, figsize=(9, 3.2 * len(trs)), squeeze=False)
    for ax, tag in zip(axs[:, 0], trs):
        tm, ep = ev["times_" + tag], ev["epoch_" + tag]
        if len(tm) < 2:
            ax.set_title(f"{tag}: no model transits")
            continue
        P, T0 = np.polyfit(ep, tm, 1)
        ax.plot(tm, (tm - (T0 + ep * P)) * 1440, "-", lw=1, color="C0" if tag == trs[0] else "C1",
                label=f"model {tag} (P_mean = {P:.6f} d)")
        if tag in prob.tt:
            dd = prob.tt[tag]
            n = np.round((dd["t"] - T0) / P)
            oc = (dd["t"] - (T0 + n * P)) * 1440
            u = dd["use"]
            ax.errorbar(dd["t"][u], oc[u], yerr=dd["sig_tot"][u] * 1440, fmt="o", ms=4, color="k",
                        label="observed (in likelihood)")
            if (~u).any():
                ax.errorbar(dd["t"][~u], oc[~u], yerr=dd["sig_tot"][~u] * 1440, fmt="o", ms=4, mfc="w",
                            color="k", label="observed (not in likelihood)")
        ax.axhline(0, color="0.6", ls=":")
        ax.set_ylabel(f"O-C {tag} [min]")
        ax.legend(fontsize=8)
    axs[-1, 0].set_xlabel("BTJD")
    fig.suptitle(f"{prob.cfg['name']}: TTV (O-C with respect to the mean ephemeris of the model)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_rv(prob, x, path):
    if prob.rv is None:
        return
    p, d, _ = prob.derive(x)
    ev = prob.events(x, d)
    rv = prob.rv
    off = rv.offsets(p)
    res = rv.rv - ev["rv"] - off
    gpm = np.zeros_like(res)
    if rv.use_gp:
        gpm = rv.gp(p, prob.rv_ln_Prot(p)).predict(res, t=rv.t)
    t0, t1 = rv.t.min(), rv.t.max()
    span = t1 - t0
    n = int(min(3000, max(200, span / (2 * prob.dt))))
    tg = np.linspace(t0 + 0.0, t1, n)
    tg = tg[tg > prob.t_start + 2 * prob.dt]
    try:
        evg = run_ttvfast(d, prob.tags, prob.t_start, prob.t_end, prob.dt, rv_times=tg)
        mg = evg["rv"]
    except ValueError:
        mg = None
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True, gridspec_kw=dict(height_ratios=[3, 1]))
    jit = np.sqrt(rv.err**2 + rv.jitter2(p))
    for k, inst in enumerate(rv.instruments):
        m = rv.idx == k
        a1.errorbar(rv.t[m], (rv.rv - off - gpm)[m], yerr=jit[m], fmt="o", ms=4, label=inst)
        a2.errorbar(rv.t[m], (res - gpm)[m], yerr=jit[m], fmt="o", ms=4)
    if mg is not None:
        a1.plot(tg, mg, "-", color="k", lw=0.8, label="model (N-body)")
    a1.set_ylabel("RV - offset - GP [m/s]")
    a1.legend(fontsize=8)
    a2.axhline(0, color="0.6", ls=":")
    a2.set_ylabel("residual [m/s]")
    a2.set_xlabel("BTJD")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_photometry(prob, x, path):
    if not prob.segments:
        return
    p, d, shape = prob.derive(x)
    ev = prob.events(x, d)
    fig, axs = plt.subplots(len(prob.segments), 1, figsize=(10, 2.8 * len(prob.segments)), squeeze=False)
    for ax, seg in zip(axs[:, 0], prob.segments):
        sp = prob.seg_pars(p, seg)
        tr = prob.photo_model(ev, d, shape, seg, sp)
        r = seg.y - sp["F0"] - tr
        g = seg.gp(sp).predict(r, t=seg.t) if seg.use_gp else np.zeros_like(r)
        ax.plot(seg.t, seg.y - sp["F0"], ",", color="0.6")
        ax.plot(seg.t, g + tr, "-", color="C3", lw=0.6, label="GP + transits")
        ax.plot(seg.t, tr - 3 * np.std(r - g) - 2, "-", color="C0", lw=0.6, label="transits (offset)")
        ax.set_ylabel(f"segment {seg.seg} [ppt]")
        ax.legend(fontsize=7, loc="lower right")
    axs[-1, 0].set_xlabel("BTJD")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_corner(prob, chain, path):
    try:
        import corner
    except ImportError:
        return
    keys = [n for n in prob.names if n.split("_")[0] in ("log", "P", "ecosw", "esinw", "b", "cosi", "dOm", "mstar")
            or n.startswith("log_q")][:16]
    fig = corner.corner(chain[:, [prob.idx(k) for k in keys]], labels=keys, quantiles=[0.16, 0.5, 0.84])
    fig.savefig(path, dpi=80)
    plt.close(fig)


# ===========================================================================
# Hoofdprogramma
# ===========================================================================
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", help="JSON configuration")
    ap.add_argument("--nproc", type=int, default=1)
    ap.add_argument("--outdir", default=None, help="overrides outdir of the configuration")
    ap.add_argument("--mode", choices=["ttv", "photodyn"], default=None, help="overrides mode")
    ap.add_argument("--start-json", default=None, help="starting values (overrides start_json)")
    ap.add_argument("--no-search", action="store_true", help="no prefit/global search")
    ap.add_argument("--prefit-only", action="store_true", help="stop after the prefit (prefit_start.json)")
    ap.add_argument("--prefit-eval", default=None, metavar="START.json",
                    help="check: prefit objective at this start file, then stop")
    ap.add_argument("--no-mcmc", action="store_true")
    ap.add_argument("--mcmc", action="store_true", help="run the MCMC, even if the configuration disables it")
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--eval-only", action="store_true", help="only lnP at the start (check)")
    a = ap.parse_args(argv)
    import signal
    signal.signal(signal.SIGTERM, lambda *_: sys.exit("aborted (SIGTERM)"))

    cfg = load_config(a.config)
    if a.mode:
        cfg["mode"] = a.mode
    if a.outdir:
        cfg["outdir"] = a.outdir
    if a.start_json:
        cfg["start_json"] = a.start_json
    if a.steps:
        cfg["mcmc"]["steps"] = a.steps
    out = cfg["outdir"] if os.path.isabs(cfg["outdir"]) else os.path.join(cfg["_base"], cfg["outdir"])
    os.makedirs(out, exist_ok=True)
    print(f"photodyn2p {VERSION}: {cfg['name']}, mode {cfg['mode']}, output -> {out}", flush=True)
    with open(os.path.join(out, "config_used.json"), "w") as fh:
        json.dump({k: v for k, v in cfg.items() if not k.startswith("_")}, fh, indent=2)

    prob = Problem(cfg)
    print(f"{prob.ndim} parameters; t_start = {prob.t_start:.5f}, t_end = {prob.t_end:.5f}, dt = {prob.dt:.4f} d; "
          f"planets: " + ", ".join(f"{p['name']} ({'transiting' if p['transiting'] else 'non-transiting'})"
                                    for p in prob.planets), flush=True)
    x = prob.x0.copy()
    if cfg["start_json"]:
        x = apply_start(prob, x, resolve(cfg, cfg["start_json"]), cfg)
    if a.prefit_eval:
        prefit_eval(prob, resolve(cfg, a.prefit_eval))
        return
    l0 = prob.lnprob(x, debug=True)
    print(f"Start: lnP = {l0:.2f}", flush=True)
    if a.eval_only:
        prob.report_failures()
        return

    do_search = cfg["search"].get("enabled", True) and not a.no_search and not cfg["start_json"]
    if do_search:
        x, fbest = run_prefit(prob, out, a.nproc)
        print(f"  prefit solution in the full model: lnP = {prob.lnprob(x):.2f}", flush=True)
        if a.prefit_only:
            return
    elif not cfg["start_json"]:
        print("  [note] no start file and no prefit: the dynamics are strongly multimodal; the result "
              "depends on the starting values")

    oc = cfg["optimize"]
    pool = make_pool(a.nproc, prob)
    try:
        print("\nOptimisation:")
        if len(prob.nuis_idx):
            x, _ = optimize(prob, x, prob.nuis_idx, int(oc["maxiter_nuis"]), "step 1 (nuisance parameters)", pool)
        x, lnp = optimize(prob, x, None, int(oc["maxiter"]), "step 2 (all parameters)", pool)
    finally:
        close_pool(pool)
    prob.report_failures()
    der = derived(prob, x)
    with open(os.path.join(out, "start.json"), "w") as fh:
        json.dump(start_dict(prob, x), fh, indent=2)
    print("\nFigures...")
    plot_oc(prob, x, os.path.join(out, "ttv_oc.png"))
    plot_rv(prob, x, os.path.join(out, "rv.png"))
    plot_photometry(prob, x, os.path.join(out, "photometry.png"))

    post, diag, chain = None, None, None
    if (cfg["mcmc"].get("enabled") or a.mcmc) and not a.no_mcmc:
        chain, diag = run_mcmc(prob, x, out, a.nproc)
        np.save(os.path.join(out, "chain.npy"), chain)
        post = {}
        for i, n in enumerate(prob.names):
            q = np.percentile(chain[:, i], [16, 50, 84])
            post[n] = dict(median=float(q[1]), lo=float(q[1] - q[0]), hi=float(q[2] - q[1]))
        post.update(mass_posteriors(prob, chain))
        plot_corner(prob, chain, os.path.join(out, "corner.png"))

    res = dict(version=VERSION, name=cfg["name"], mode=prob.mode, lnP=lnp, ndim=prob.ndim, t_start=prob.t_start,
               t_end=prob.t_end, dt=prob.dt, parameters_ml={n: float(v) for n, v in zip(prob.names, x)},
               derived_ml=der, evaluation_failures=dict(prob.fail))
    if post:
        res["posterior"] = post
        res["mcmc"] = diag
    with open(os.path.join(out, "results.json"), "w") as fh:
        json.dump(res, fh, indent=2)
    txt = fmt_summary(prob, x, lnp, der, post, diag)
    with open(os.path.join(out, "summary.txt"), "w") as fh:
        fh.write(txt)
    print("\n" + txt)
    print(f"Done -> {out}  (start.json, results.json, summary.txt, figures)", flush=True)


if __name__ == "__main__":
    main()
