#!/usr/bin/env python3
"""
Stationarity check of an emcee HDF5 back-end written by photodyn2p (or toi3686_photodynamical_ttvfast_v3).
Run it on a COPY if the chain is still running.

Per block of steps it prints the acceptance (fraction of walkers that moved), the median ln p and the mean +- sd
over the walkers of selected parameters; then the integrated autocorrelation time tau for growing chain lengths.
A chain is usable when the block means no longer drift, the spreads are stable, tau stops growing with N, and
(N - burn)/tau_max is large (>= 50 is the strict emcee rule).

Usage:
  cp output/chain.h5 /tmp/chain_copy.h5
  HDF5_USE_FILE_LOCKING=FALSE python tools/block_check.py /tmp/chain_copy.h5 --names output/chain.h5.names.json
  options: --block 500  --params mstar rstar log_q_b log_q_c dOm  --burn 1000
"""
import argparse
import json

import h5py
import numpy as np


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backend")
    ap.add_argument("--names", required=True, help="<backend>.names.json")
    ap.add_argument("--block", type=int, default=500)
    ap.add_argument("--params", nargs="+", default=None,
                    help="parameters to show (default: all log_q_*, mstar, rstar, dOm*)")
    ap.add_argument("--burn", type=int, default=None, help="for the tau table; default: one third of the chain")
    a = ap.parse_args()

    with h5py.File(a.backend, "r") as f:
        g = f["mcmc"]
        n = int(g.attrs["iteration"])
        chain = g["chain"][:n]
        lnp = g["log_prob"][:n]
    names = json.load(open(a.names))
    ix = {k: i for i, k in enumerate(names)}
    sel = a.params or [k for k in names if k.startswith("log_q_") or k.startswith("log_mp_")
                       or k in ("mstar", "rstar") or k.startswith("dOm")]
    sel = [k for k in sel if k in ix]
    print(f"{a.backend}: {n} steps, {chain.shape[1]} walkers, {chain.shape[2]} parameters\n")
    print(f"{'steps':>11s} {'acc':>5s} {'ln p med':>9s} " + " ".join(f"{k:>17s}" for k in sel))
    for s0 in range(0, n, a.block):
        s = slice(s0, min(s0 + a.block, n))
        if s.stop - s.start < 2:
            continue
        acc = np.mean(np.any(np.diff(chain[s], axis=0) != 0, axis=2))
        row = " ".join(f"{chain[s, :, ix[k]].mean():9.5f}±{chain[s, :, ix[k]].std():<7.5f}" for k in sel)
        print(f"{s.start:5d}-{s.stop - 1:<5d} {acc:5.3f} {np.median(lnp[s]):9.1f} {row}")
    try:
        import emcee
    except ImportError:
        return
    burn = a.burn if a.burn is not None else n // 3
    print(f"\ntau after burn-in {burn} for growing chain length (over all parameters):")
    for frac in (0.25, 0.5, 0.75, 1.0):
        m = burn + int(frac * (n - burn))
        if m - burn < 50:
            continue
        tau = emcee.autocorr.integrated_time(chain[burn:m], quiet=True)
        print(f"  N - burn = {m - burn:6d}: tau_max = {np.nanmax(tau):7.0f}  tau_median = {np.nanmedian(tau):7.0f}"
              f"  (N - burn)/tau_max = {(m - burn) / np.nanmax(tau):5.1f}")
    print("  A tau that grows in proportion to N - burn is not yet measurable: extend the chain.")


if __name__ == "__main__":
    main()
