#!/usr/bin/env python3
"""
Generate the synthetic test examples for photodyn2p (and its GUI) with a KNOWN truth.

The data are produced with the physics of photodyn2p itself (TTVFast for the transit times and stellar RVs,
batman for the light curves), so a correct fit must recover the input values within the uncertainties.

System: a sub-Neptune b (P = 3.000 d) and a warm Jupiter c (P = 6.150 d) just wide of the 2:1 resonance,
around a solar-type star; the osculating elements below hold at T_START.

  example1_ttv_both/           both planets transit; mid-times of b and c + RVs          (mode ttv)
  example2_ttv_nontransiting/  c does NOT transit; mid-times of b + RVs only              (mode ttv)
  example3_photodyn/           light curves of two 27-d segments + ground mid-times of c + RVs (mode photodyn)

Usage (from the directory that contains photodyn2p.py, or with photodyn2p.py on the Python path):
  python make_synthetic_examples.py [--outdir examples_synthetic] [--seed 42]
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for cand in (os.getcwd(), HERE, os.path.join(HERE, "..")):
    if os.path.isfile(os.path.join(cand, "photodyn2p.py")):
        sys.path.insert(0, cand)
        break
import photodyn2p as P2  # noqa: E402

T_START = 999.0                       # BTJD; also written explicitly into every configuration
T_END = 1800.0
MSUN_ME, MSUN_MJ = 332946.0, 1047.57

TRUTH = dict(
    mstar=1.00, rstar=1.00,
    b=dict(P=3.0000, T0=1000.2500, m_Mearth=15.0, ecosw=0.030, esinw=-0.040, b=0.30, rp=0.030),
    c=dict(P=6.1500, T0=1002.1000, m_Mjup=0.60, ecosw=0.010, esinw=0.015, b=0.20, rp=0.100),
    dOm=0.0, q1=0.36, q2=0.30,
)
C_NONTRANSIT_B = 1.60                 # impact parameter of c in example 2 (no transit)
MEAN_P = dict(b=3.0013, c=6.1490)     # mean periods of the synthetic system (as measured from its transit times)


def dyn_dict(truth, b_c=None):
    """Dynamical dictionary in the conventions of photodyn2p (Jacobi elements osculating at T_START)."""
    ms, rs = truth["mstar"], truth["rstar"]
    d = dict(mstar=ms, rstar=rs, dOm=truth["dOm"])
    for tag, unit in (("b", 1.0 / MSUN_ME), ("c", 1.0 / MSUN_MJ)):
        t = truth[tag]
        m = (t["m_Mearth"] if tag == "b" else t["m_Mjup"]) * unit
        e = float(np.hypot(t["ecosw"], t["esinw"]))
        w = float(np.degrees(np.arctan2(t["esinw"], t["ecosw"])))
        aR = P2.a_over_rstar(t["P"], ms, m, rs)
        bb = t["b"] if (tag == "b" or b_c is None) else b_c
        d.update({f"mp_{tag}": m, f"P_{tag}": t["P"], f"T0_{tag}": t["T0"], f"e_{tag}": e, f"w_{tag}": w,
                  f"aR_{tag}": aR, f"i_{tag}": P2.inc_from_b(bb, aR, e, w)})
    return d


def write_midtimes(path, times, epochs, sig_min, rng, facility, comment):
    sig = sig_min / 1440.0
    with open(path, "w") as fh:
        fh.write(f"# {comment}\n# epoch  BTJD  sigma_stat[d]  sigma_sys[d]  facility\n")
        for n, t in zip(epochs, times):
            fh.write(f"{int(n):5d}  {t + rng.normal(0, sig):.6f}  {sig:.6f}  0.000000  {facility}\n")


def write_rv(path, t, rv, sig, rng, inst, offset):
    with open(path, "w") as fh:
        fh.write("# time[BTJD]  rv[m/s]  err[m/s]  instrument\n")
        for ti, v in zip(t, rv):
            fh.write(f"{ti:.6f}  {v + offset + rng.normal(0, sig):.3f}  {sig:.3f}  {inst}\n")


def truth_start(truth, b_c=None, transiting_c=True):
    """Start file with the TRUE values (for --eval-only checks), in the parameter names of photodyn2p."""
    st = dict(t_start=T_START, source="synthetic truth", mstar=truth["mstar"], rstar=truth["rstar"],
              dOm=truth["dOm"], q1=truth["q1"], q2=truth["q2"])
    for tag, unit in (("b", 1.0 / MSUN_ME), ("c", 1.0 / MSUN_MJ)):
        t = truth[tag]
        m = (t["m_Mearth"] if tag == "b" else t["m_Mjup"]) * unit
        st.update({f"log_q_{tag}": float(np.log10(m / truth["mstar"])), f"P_{tag}": t["P"], f"T0_{tag}": t["T0"],
                   f"ecosw_{tag}": t["ecosw"], f"esinw_{tag}": t["esinw"], f"rp_{tag}": t["rp"]})
        if tag == "c" and not transiting_c:
            d = dyn_dict(truth, b_c)
            st["cosi_c"] = float(np.cos(np.radians(d["i_c"])))
        else:
            st[f"b_{tag}"] = t["b"] if (tag == "b" or b_c is None) else b_c
    return st


def base_config(name, mode):
    return dict(name=name, mode=mode, outdir="output", t_start=T_START, t_end=T_END, dt=0.08,
                star=dict(mstar=[1.0, 0.05], rstar=[1.0, 0.03]), free_ecc=True, ecc_max=0.5,
                midtimes=dict(floor_min=1.0, jitter="none", exclude_facility_in_photodyn="TESS"),
                search=dict(enabled=True, popsize=15, maxiter=120, seed=1, strategy="best1bin", top=5,
                            polish_nfev=150, checkpoint="prefit_checkpoint.npz"),
                optimize=dict(maxiter_nuis=50, maxiter=300),
                mcmc=dict(enabled=False, nwalkers=0, steps=2000, init_hessian=True, backend="chain.h5"))


def planet_cfg(tag, transiting=True, midtimes=None, **kw):
    t = TRUTH[tag]
    # P = observed mean period (as a user would take it from the mid-times), searched within +-0.3%
    p = dict(name=tag, transiting=transiting, P=round(MEAN_P[tag], 4), P_range=0.003, midtimes=midtimes,
             mass_unit="Mearth" if tag == "b" else "Mjup", phase_window=0.08,
             mass_bounds=[1.0, 60.0] if tag == "b" else [0.1, 3.0], rp=t["rp"], b=0.3)
    p.update(kw)
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outdir", default="examples_synthetic")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    root = a.outdir
    os.makedirs(root, exist_ok=True)

    # ---------------------------------------------------------------- shared observing schedule
    rv_t = np.sort(1350.0 + rng.uniform(0, 60, 30))                     # 30 RVs within 60 d
    rv_sig = 3.0

    # ---------------------------------------------------------------- example 1: both transiting
    d1 = dyn_dict(TRUTH)
    ev1 = P2.run_ttvfast(d1, ["b", "c"], T_START, T_END, 0.02, rv_times=rv_t)
    ex = os.path.join(root, "example1_ttv_both")
    os.makedirs(ex, exist_ok=True)
    sel_b = np.sort(rng.choice(len(ev1["times_b"]), 50, replace=False))
    sel_c = np.sort(rng.choice(len(ev1["times_c"]), 35, replace=False))
    write_midtimes(os.path.join(ex, "midtimes_b.dat"), ev1["times_b"][sel_b], ev1["epoch_b"][sel_b], 4.0, rng,
                   "Ground", "synthetic mid-transit times of planet b (sigma 4 min)")
    write_midtimes(os.path.join(ex, "midtimes_c.dat"), ev1["times_c"][sel_c], ev1["epoch_c"][sel_c], 1.5, rng,
                   "Ground", "synthetic mid-transit times of planet c (sigma 1.5 min)")
    write_rv(os.path.join(ex, "rv.dat"), rv_t, ev1["rv"], rv_sig, rng, "SPEC", 25.0)
    cfg = base_config("Synthetic example 1 (both transiting)", "ttv")
    cfg["planets"] = [planet_cfg("b", True, "midtimes_b.dat"), planet_cfg("c", True, "midtimes_c.dat")]
    cfg["rv"] = dict(file="rv.dat", gp=False, search_jitter=3.0)
    json.dump(cfg, open(os.path.join(ex, "config.json"), "w"), indent=2)
    json.dump(truth_start(TRUTH), open(os.path.join(ex, "truth_start.json"), "w"), indent=2)

    # ---------------------------------------------------------------- example 2: c non-transiting
    d2 = dyn_dict(TRUTH, b_c=C_NONTRANSIT_B)
    ev2 = P2.run_ttvfast(d2, ["b", "c"], T_START, T_END, 0.02, rv_times=rv_t)
    ex = os.path.join(root, "example2_ttv_nontransiting")
    os.makedirs(ex, exist_ok=True)
    sel_b = np.sort(rng.choice(len(ev2["times_b"]), 60, replace=False))
    write_midtimes(os.path.join(ex, "midtimes_b.dat"), ev2["times_b"][sel_b], ev2["epoch_b"][sel_b], 4.0, rng,
                   "Ground", "synthetic mid-transit times of planet b (sigma 4 min); c does not transit")
    write_rv(os.path.join(ex, "rv.dat"), rv_t, ev2["rv"], rv_sig, rng, "SPEC", -12.0)
    cfg = base_config("Synthetic example 2 (c non-transiting)", "ttv")
    cfg["planets"] = [planet_cfg("b", True, "midtimes_b.dat"),
                      planet_cfg("c", False, None, cosi=0.15, forbid_transit=True)]
    cfg["rv"] = dict(file="rv.dat", gp=False, search_jitter=3.0)
    cfg["dOm_bounds"] = [-30.0, 30.0]
    json.dump(cfg, open(os.path.join(ex, "config.json"), "w"), indent=2)
    json.dump(truth_start(TRUTH, C_NONTRANSIT_B, transiting_c=False),
              open(os.path.join(ex, "truth_start.json"), "w"), indent=2)

    # ---------------------------------------------------------------- example 3: photodynamical
    ex = os.path.join(root, "example3_photodyn")
    os.makedirs(ex, exist_ok=True)
    segs = {1: (1100.0, 1127.0), 2: (1600.0, 1627.0)}
    cad, noise = 10.0 / 1440.0, 0.6                                     # 10-min cadence, 0.6 ppt
    ev3 = P2.run_ttvfast(d1, ["b", "c"], T_START, T_END, 0.02, rv_times=rv_t)
    rows = []
    for s, (t0, t1) in segs.items():
        t = np.arange(t0, t1, cad)
        model = np.zeros_like(t)
        for tag in ("b", "c"):
            tt, bb = ev3["times_" + tag], ev3["b_" + tag]
            m = (tt > t0 - 1) & (tt < t1 + 1)
            model += P2.multi_transit_model(t, tt[m], bb[m], d1["P_" + tag], TRUTH[tag]["rp"], d1["aR_" + tag],
                                            TRUTH["q1"], TRUTH["q2"], d1["e_" + tag], d1["w_" + tag], cad)
        flux = 1.0 + (model + rng.normal(0, noise, t.size)) / 1e3
        rows += [(ti, fi, noise / 1e3, s) for ti, fi in zip(t, flux)]
    with open(os.path.join(ex, "lightcurve.csv"), "w") as fh:
        fh.write("# time,flux,flux_err,segment\n")
        for r in rows:
            fh.write(f"{r[0]:.6f},{r[1]:.7f},{r[2]:.7f},{r[3]}\n")
    # ground-based mid-times of c OUTSIDE the light-curve segments (as for TOI-3686)
    tc, ec = ev3["times_c"], ev3["epoch_c"]
    outside = ~np.any([(tc > a_ - 1) & (tc < b_ + 1) for a_, b_ in segs.values()], axis=0)
    sel_c = np.sort(rng.choice(np.where(outside)[0], 30, replace=False))
    write_midtimes(os.path.join(ex, "midtimes_c.dat"), tc[sel_c], ec[sel_c], 1.5, rng, "Ground",
                   "synthetic ground-based mid-transit times of planet c (sigma 1.5 min), outside the segments")
    write_rv(os.path.join(ex, "rv.dat"), rv_t, ev3["rv"], rv_sig, rng, "SPEC", 25.0)
    cfg = base_config("Synthetic example 3 (photodynamical)", "photodyn")
    cfg["planets"] = [planet_cfg("b", True, None), planet_cfg("c", True, "midtimes_c.dat")]
    cfg["rv"] = dict(file="rv.dat", gp=False, search_jitter=3.0)
    cfg["photometry"] = dict(csv="lightcurve.csv", trend="ignore", gp=False, dilution="fixed")
    cfg["start_json"] = "../example1_ttv_both/output/start.json"
    cfg["search"]["enabled"] = False
    json.dump(cfg, open(os.path.join(ex, "config.json"), "w"), indent=2)
    json.dump(truth_start(TRUTH), open(os.path.join(ex, "truth_start.json"), "w"), indent=2)

    # ---------------------------------------------------------------- truth table
    truth = json.loads(json.dumps(TRUTH))
    for tag in ("b", "c"):
        truth[tag]["e"] = float(np.hypot(TRUTH[tag]["ecosw"], TRUTH[tag]["esinw"]))
        truth[tag]["a_over_Rstar"] = float(d1["aR_" + tag])
        e1 = P2.mean_ephemeris(ev1["times_" + tag], ev1["epoch_" + tag])
        truth[tag]["mean_period"] = e1["P"]
        truth[tag]["TTV_halfamp_min"] = e1["oc_halfamp_min"]
    truth["log_q_b"] = float(np.log10(TRUTH["b"]["m_Mearth"] / MSUN_ME / TRUTH["mstar"]))
    truth["log_q_c"] = float(np.log10(TRUTH["c"]["m_Mjup"] / MSUN_MJ / TRUTH["mstar"]))
    truth["example2_c_impact_parameter"] = C_NONTRANSIT_B
    truth["t_start"] = T_START
    json.dump(truth, open(os.path.join(root, "truth.json"), "w"), indent=2)
    print(f"examples written to {root}/")
    for tag in ("b", "c"):
        print(f"  {tag}: mean P {truth[tag]['mean_period']:.5f} d, TTV half-amplitude "
              f"{truth[tag]['TTV_halfamp_min']:.1f} min, a/R* {truth[tag]['a_over_Rstar']:.2f}")


if __name__ == "__main__":
    main()
