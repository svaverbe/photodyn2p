#!/usr/bin/env python3
"""
photodyn2p_gui - graphical front end (PyQt5) for photodyn2p.py.

Tabs: Object & star | Planets | Data | Fit | Run | Results.
The GUI reads and writes the same JSON configuration as the computational core; a run is started as a
separate process (python photodyn2p.py config.json --nproc N), so long runs do not block the GUI and the
core remains usable without it.

Usage:  python photodyn2p_gui.py [config.json]
"""

from __future__ import annotations

import json
import os
import sys

from PyQt5.QtCore import QProcess, Qt, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices, QFont, QPixmap
from PyQt5.QtWidgets import (QAction, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                             QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
                             QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QTabWidget,
                             QVBoxLayout, QWidget)

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(HERE, "photodyn2p.py")
MANUAL = os.path.join(HERE, "photodyn2p_manual.pdf")
sys.path.insert(0, HERE)
from photodyn2p import DEFAULT_CONFIG, DEFAULT_PLANET, merge  # noqa: E402


# ---------------------------------------------------------------------------- small building blocks
def dspin(lo, hi, val, dec=4, step=None):
    w = QDoubleSpinBox()
    w.setDecimals(dec)
    w.setRange(lo, hi)
    w.setValue(val)
    w.setSingleStep(step if step else 10 ** (-min(dec, 3)))
    w.setKeyboardTracking(False)
    return w


def ispin(lo, hi, val):
    w = QSpinBox()
    w.setRange(lo, hi)
    w.setValue(val)
    return w


def opt_float(text):
    t = text.strip().replace(",", ".")
    return float(t) if t else None


def fmt_opt(v):
    return "" if v is None else repr(v)


class FileField(QWidget):
    """Line edit + browse button; empty = not used."""

    def __init__(self, caption, filt="All files (*)", directory=False, save=False):
        super().__init__()
        self.caption, self.filt, self.directory, self.save = caption, filt, directory, save
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        b = QPushButton("…")
        b.setFixedWidth(30)
        b.clicked.connect(self.browse)
        lay.addWidget(self.edit)
        lay.addWidget(b)

    base_dir_fn = None                      # set by the main window: directory of the open configuration

    def start_dir(self):
        """Directory in which the file dialog opens: that of the current entry (relative entries are taken
        relative to the configuration directory, as the core does), otherwise the configuration directory."""
        base = FileField.base_dir_fn() if FileField.base_dir_fn else os.getcwd()
        t = self.edit.text().strip()
        if t:
            p = t if os.path.isabs(t) else os.path.join(base, t)
            d = p if (self.directory and os.path.isdir(p)) else os.path.dirname(p)
            if os.path.isdir(d):
                return d
        return base if os.path.isdir(base) else os.getcwd()

    def browse(self):
        start = self.start_dir()
        # Qt's own dialog: the native (portal/GTK) dialog can fail or hang under WSL, especially on /mnt drives
        opt = QFileDialog.DontUseNativeDialog
        if self.directory:
            p = QFileDialog.getExistingDirectory(self, self.caption, start, QFileDialog.ShowDirsOnly | opt)
        else:
            p, _ = QFileDialog.getOpenFileName(self, self.caption, start, self.filt, options=opt)
        if p:
            self.edit.setText(p)

    def text(self):
        return self.edit.text().strip() or None

    def setText(self, v):
        self.edit.setText(v or "")


# ---------------------------------------------------------------------------- planet
class PlanetBox(QGroupBox):
    def __init__(self, title):
        super().__init__(title)
        f = QFormLayout(self)
        self.name = QLineEdit()
        self.transiting = QCheckBox("transiting")
        self.P = dspin(0.1, 1e5, 1.0, 6)
        self.P_range = dspin(0.0001, 0.5, 0.02, 4, 0.005)
        self.T0 = QLineEdit()
        self.T0.setPlaceholderText("optional")
        self.midtimes = FileField("Mid-transit times", "Text (*.dat *.txt *.csv);;All (*)")
        self.mass_unit = QComboBox()
        self.mass_unit.addItems(["Mearth", "Mjup"])
        self.mass_guess = QLineEdit()
        self.mass_guess.setPlaceholderText("automatic")
        self.mass_lo = dspin(1e-5, 1e5, 0.1, 4)
        self.mass_hi = dspin(1e-5, 1e6, 3000.0, 3)
        self.rp = dspin(0.001, 0.5, 0.02, 5)
        self.rp_prior_on = QCheckBox("Gaussian prior")
        self.rp_mu = dspin(0.0, 0.5, 0.02, 5)
        self.rp_sig = dspin(0.0, 0.5, 0.001, 5)
        self.b = dspin(-1.5, 1.5, 0.3, 3)
        self.cosi = dspin(-1.0, 1.0, 0.0, 3)
        self.forbid = QCheckBox("no transit (|b| ≥ 1)")
        self.ecosw = dspin(-0.9, 0.9, 0.0, 4)
        self.esinw = dspin(-0.9, 0.9, 0.0, 4)
        self.pb_on = QCheckBox("explicit")
        self.pb_lo, self.pb_hi = dspin(0.01, 1e5, 1.0, 5), dspin(0.01, 1e5, 1.0, 5)
        self.phwin = QLineEdit()
        self.phwin.setPlaceholderText("default (Fit tab)")
        self.ecc_b, self.ecc_cut = dspin(0.01, 0.9, 0.4, 3), dspin(0.01, 0.95, 0.45, 3)
        self.segt = FileField("Sector times (b_times.dat format)", "Text (*.dat *.txt);;All (*)")
        self.phot_term = QCheckBox("template on the residual photometry")
        mrow = QWidget()
        ml = QHBoxLayout(mrow)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(self.mass_lo)
        ml.addWidget(QLabel("–"))
        ml.addWidget(self.mass_hi)
        rrow = QWidget()
        rl = QHBoxLayout(rrow)
        rl.setContentsMargins(0, 0, 0, 0)
        for w in (self.rp_prior_on, QLabel("μ"), self.rp_mu, QLabel("σ"), self.rp_sig):
            rl.addWidget(w)
        f.addRow("Name", self.name)
        f.addRow("", self.transiting)
        f.addRow("P [d]", self.P)
        f.addRow("P search width", self.P_range)
        f.addRow("T0 [BTJD]", self.T0)
        f.addRow("Mid-times", self.midtimes)
        f.addRow("Mass unit", self.mass_unit)
        f.addRow("Mass (start)", self.mass_guess)
        f.addRow("Mass (bounds)", mrow)
        f.addRow("Rp/R*", self.rp)
        f.addRow("Rp/R* prior", rrow)
        f.addRow("b (start)", self.b)
        f.addRow("cos i (start)", self.cosi)
        f.addRow("", self.forbid)
        f.addRow("e cos ω (start)", self.ecosw)
        f.addRow("e sin ω (start)", self.esinw)
        pbrow = QWidget()
        pl_ = QHBoxLayout(pbrow)
        pl_.setContentsMargins(0, 0, 0, 0)
        for w_ in (self.pb_on, self.pb_lo, self.pb_hi):
            pl_.addWidget(w_)
        erow = QWidget()
        el_ = QHBoxLayout(erow)
        el_.setContentsMargins(0, 0, 0, 0)
        for w_ in (QLabel("bound"), self.ecc_b, QLabel("cut"), self.ecc_cut):
            el_.addWidget(w_)
        f.addRow(QLabel("<b>Prefit</b>"))
        f.addRow("P bounds [d]", pbrow)
        f.addRow("Phase window", self.phwin)
        f.addRow("e-vector", erow)
        f.addRow("Sector times", self.segt)
        f.addRow("", self.phot_term)
        self.pb_on.toggled.connect(self.update_enabled)
        f.setRowWrapPolicy(QFormLayout.WrapLongRows)
        tips = {self.P: "observed (mean) period; also the starting value of the osculating period",
                self.P_range: "relative search width of the osculating period (0.02 = ±2%)",
                self.T0: "a conjunction or transit time in BTJD; empty = from the mid-times",
                self.mass_lo: "bounds at M* = prior mean; internally log10(m/M*)",
                self.mass_guess: "empty = automatic (geometric mean of the bounds); the prefit or a start file "
                                 "sets the actual starting value",
                self.cosi: "non-transiting: cos i (uniform = isotropic orientation)",
                self.b: "transiting: impact parameter; for planet 1 (reference) b ≥ 0",
                self.rp_prior_on: "e.g. from undiluted ground-based photometry (photodyn mode)"}
        for w_, t_ in tips.items():
            w_.setToolTip(t_)
        self.transiting.toggled.connect(self.update_enabled)
        self.rp_prior_on.toggled.connect(self.update_enabled)

    def update_enabled(self):
        tr = self.transiting.isChecked()
        for w in (self.midtimes, self.rp, self.rp_prior_on, self.b):
            w.setEnabled(tr)
        for w in (self.rp_mu, self.rp_sig):
            w.setEnabled(tr and self.rp_prior_on.isChecked())
        for w in (self.cosi, self.forbid):
            w.setEnabled(not tr)
        for w in (self.segt, self.phot_term, self.phwin):
            w.setEnabled(tr)
        for w in (self.pb_lo, self.pb_hi):
            w.setEnabled(self.pb_on.isChecked())

    def load(self, p):
        p = merge(DEFAULT_PLANET, p)
        self.name.setText(p["name"])
        self.transiting.setChecked(bool(p["transiting"]))
        self.P.setValue(float(p["P"] or 1.0))
        self.P_range.setValue(float(p["P_range"]))
        self.T0.setText(fmt_opt(p["T0"]))
        self.midtimes.setText(p["midtimes"])
        self.mass_unit.setCurrentText(p["mass_unit"])
        mb = p["mass_bounds"] or ([0.1, 3000.0] if p["mass_unit"] == "Mearth" else [3e-4, 10.0])
        self.mass_lo.setValue(mb[0])
        self.mass_hi.setValue(mb[1])
        self.mass_guess.setText(fmt_opt(p["mass_guess"]))
        self.rp.setValue(p["rp"])
        self.rp_prior_on.setChecked(bool(p["rp_prior"]))
        if p["rp_prior"]:
            self.rp_mu.setValue(p["rp_prior"][0])
            self.rp_sig.setValue(p["rp_prior"][1])
        self.b.setValue(p["b"])
        self.cosi.setValue(p["cosi"])
        self.forbid.setChecked(bool(p["forbid_transit"]))
        self.ecosw.setValue(p["ecosw"])
        self.esinw.setValue(p["esinw"])
        self.pb_on.setChecked(bool(p["P_bounds"]))
        pbv = p["P_bounds"] or [p["P"] * (1 - p["P_range"]), p["P"] * (1 + p["P_range"])]
        self.pb_lo.setValue(pbv[0])
        self.pb_hi.setValue(pbv[1])
        self.phwin.setText(fmt_opt(p["phase_window"]))
        self.ecc_b.setValue(p["ecc_search"][0])
        self.ecc_cut.setValue(p["ecc_search"][1])
        self.segt.setText(p["segment_times"])
        self.phot_term.setChecked(bool(p["phot_term"]))
        self._segment_halfwidth = p["segment_halfwidth"]
        self.update_enabled()

    def dump(self):
        tr = self.transiting.isChecked()
        return dict(name=self.name.text().strip(), transiting=tr, P=self.P.value(), P_range=self.P_range.value(),
                    T0=opt_float(self.T0.text()), midtimes=self.midtimes.text() if tr else None,
                    mass_unit=self.mass_unit.currentText(), mass_guess=opt_float(self.mass_guess.text()),
                    mass_bounds=[self.mass_lo.value(), self.mass_hi.value()], rp=self.rp.value(),
                    rp_prior=[self.rp_mu.value(), self.rp_sig.value()] if (tr and self.rp_prior_on.isChecked())
                    else None, b=self.b.value(), cosi=self.cosi.value(), forbid_transit=self.forbid.isChecked(),
                    ecosw=self.ecosw.value(), esinw=self.esinw.value(),
                    P_bounds=[self.pb_lo.value(), self.pb_hi.value()] if self.pb_on.isChecked() else None,
                    phase_window=opt_float(self.phwin.text()), ecc_search=[self.ecc_b.value(), self.ecc_cut.value()],
                    segment_times=self.segt.text() if tr else None, phot_term=tr and self.phot_term.isChecked(),
                    segment_halfwidth=self._segment_halfwidth)


# ---------------------------------------------------------------------------- main window
class Main(QMainWindow):
    def __init__(self, path=None):
        super().__init__()
        self.path = None
        self.proc = None
        self.setWindowTitle("photodyn2p – TTV/photodynamical model for two planets")
        FileField.base_dir_fn = lambda: os.path.dirname(self.path) if self.path else os.getcwd()
        self.resize(1150, 820)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self._build_object()
        self._build_planets()
        self._build_data()
        self._build_fit()
        self._build_run()
        self._build_results()
        self._build_menu()
        self.new_cfg()
        if path:
            self.open_path(path)

    # --- layout ------------------------------------------------------------------
    def _build_menu(self):
        m = self.menuBar().addMenu("&File")
        for txt, fn, key in (("&New", self.new_cfg, "Ctrl+N"), ("&Open…", self.open_cfg, "Ctrl+O"),
                             ("&Save", self.save_cfg, "Ctrl+S"), ("Save &as…", self.save_cfg_as, None),
                             ("&Quit", self.close, "Ctrl+Q")):
            a = QAction(txt, self)
            if key:
                a.setShortcut(key)
            a.triggered.connect(fn)
            m.addAction(a)
        r = self.menuBar().addMenu("&Run")
        for txt, fn in (("&Start", self.start_run), ("&Prefit only", lambda: self.start_run(["--prefit-only"])),
                        ("Check: lnP at the start only", self.start_eval),
                        ("S&top", self.stop_run)):
            a = QAction(txt, self)
            a.triggered.connect(fn)
            r.addAction(a)
        h = self.menuBar().addMenu("&Help")
        for txt, fn, key in (("User &manual", self.open_manual, "F1"), ("&About photodyn2p", self.about, None)):
            a = QAction(txt, self)
            if key:
                a.setShortcut(key)
            a.triggered.connect(fn)
            h.addAction(a)

    def _page(self, *widgets):
        w = QWidget()
        lay = QVBoxLayout(w)
        for x in widgets:
            lay.addWidget(x)
        lay.addStretch(1)
        sa = QScrollArea()
        sa.setWidget(w)
        sa.setWidgetResizable(True)
        return sa

    def _build_object(self):
        g = QGroupBox("Object and run")
        f = QFormLayout(g)
        self.name = QLineEdit()
        self.mode = QComboBox()
        self.mode.addItems(["ttv", "photodyn"])
        self.mode.setToolTip("ttv: mid-times (+ RVs), fast, with a global search.\n"
                             "photodyn: light curves + mid-times (+ RVs); preferably start from the start.json "
                             "of a ttv run.")
        self.outdir = FileField("Output directory", directory=True)
        self.t_start = QLineEdit()
        self.t_start.setPlaceholderText("automatic: 1 d before the first data point")
        self.t_end = QLineEdit()
        self.t_end.setPlaceholderText("automatic: 1 d after the last data point")
        self.dt = QLineEdit()
        self.dt.setPlaceholderText("automatic: min(P)/32")
        f.addRow("Name", self.name)
        f.addRow("Mode", self.mode)
        f.addRow("Output directory", self.outdir)
        f.addRow("t_start [BTJD]", self.t_start)
        f.addRow("t_end [BTJD]", self.t_end)
        f.addRow("N-body step dt [d]", self.dt)
        s = QGroupBox("Star (Gaussian priors)")
        fs = QFormLayout(s)
        self.ms_mu, self.ms_sig = dspin(0.05, 10, 1.0, 4), dspin(0.001, 5, 0.1, 4)
        self.rs_mu, self.rs_sig = dspin(0.05, 100, 1.0, 4), dspin(0.001, 10, 0.05, 4)
        for lab, a, b in (("M* [M☉]: μ, σ", self.ms_mu, self.ms_sig), ("R* [R☉]: μ, σ", self.rs_mu, self.rs_sig)):
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(a)
            hl.addWidget(b)
            fs.addRow(lab, row)
        info = QLabel("Times in BTJD (BJD − 2457000); BJD, BJD − 2450000 and BJD − 2400000 are recognised "
                      "automatically. Masses are fitted as log10(m/M*); the masses in M⊕/M_J are derived.")
        info.setWordWrap(True)
        self.tabs.addTab(self._page(g, s, info), "Object && star")

    def _build_planets(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        self.pbox = [PlanetBox("Planet 1 (Ω = 0, reference)"), PlanetBox("Planet 2")]
        for b in self.pbox:
            lay.addWidget(b)
        g = QGroupBox("Orbits")
        f = QFormLayout(g)
        self.free_ecc = QCheckBox("free eccentricities")
        self.ecc_max = dspin(0.01, 0.95, 0.5, 3)
        self.dom_auto = QCheckBox("automatic (±45° if both planets transit, otherwise ±180°)")
        self.dom_lo, self.dom_hi = dspin(-180, 180, -45, 1), dspin(-180, 180, 45, 1)
        self.b_max = dspin(0.1, 2.0, 1.0, 3)
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        for x in (self.dom_auto, self.dom_lo, self.dom_hi):
            hl.addWidget(x)
        self.dom_auto.toggled.connect(lambda on: (self.dom_lo.setEnabled(not on), self.dom_hi.setEnabled(not on)))
        f.addRow("", self.free_ecc)
        f.addRow("e max", self.ecc_max)
        f.addRow("ΔΩ bounds [°]", row)
        f.addRow("|b| max (transiting)", self.b_max)
        self.tabs.addTab(self._page(w, g), "Planets")

    def _build_data(self):
        g = QGroupBox("Mid-transit times (per planet on the Planets tab)")
        f = QFormLayout(g)
        self.floor = dspin(0.0, 60.0, 2.0, 2, 0.5)
        self.jitter = QComboBox()
        self.jitter.addItems(["none", "free"])
        self.excl = QLineEdit()
        self.excl.setToolTip("In photodyn mode, times with this word in the facility column are omitted "
                             "(they are already in the photometry). Empty = omit nothing.")
        f.addRow("Error floor [min]", self.floor)
        f.addRow("Timing jitter", self.jitter)
        f.addRow("Omit in photodyn (facility)", self.excl)
        self.rv_box = QGroupBox("Use radial velocities")
        self.rv_box.setCheckable(True)
        fr = QFormLayout(self.rv_box)
        self.rv_file = FileField("RV file", "Text (*.dat *.txt *.csv);;All (*)")
        self.rv_gp = QCheckBox("quasi-periodic GP (stellar activity)")
        self.rv_plo, self.rv_phi = dspin(0.1, 1000, 4.0, 2), dspin(0.1, 1000, 20.0, 2)
        self.rv_share = QLineEdit()
        self.rv_share.setPlaceholderText("empty = own P_rot; otherwise a segment number (photodyn)")
        self.rv_sjit = dspin(0.0, 500.0, 10.0, 1)
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.rv_plo)
        hl.addWidget(self.rv_phi)
        fr.addRow("File (time rv err instrument)", self.rv_file)
        fr.addRow("", self.rv_gp)
        fr.addRow("P_rot bounds [d]", row)
        fr.addRow("Share P_rot with segment", self.rv_share)
        fr.addRow("Jitter in the search [m/s]", self.rv_sjit)
        self.ph_box = QGroupBox("Photometry (photodyn mode only)")
        fp = QFormLayout(self.ph_box)
        self.ph_csv = FileField("Light curve (CSV)", "CSV (*.csv *.txt);;All (*)")
        self.ph_segs = QLineEdit()
        self.ph_segs.setPlaceholderText("empty = all segments; e.g. 18, 58, 85")
        self.ph_trend = QComboBox()
        self.ph_trend.addItems(["ignore", "multiply"])
        self.ph_trend.setToolTip("multiply: reconstruct flux × trend (5th column), so that the GP models the "
                                 "activity again together with the transits")
        self.ph_gp = QCheckBox("GP per segment")
        self.ph_plo, self.ph_phi = dspin(0.1, 1000, 4.0, 2), dspin(0.1, 1000, 20.0, 2)
        self.ph_lnq0 = dspin(-10, 5, -2.302585, 8)
        self.ph_dil = QComboBox()
        self.ph_dil.addItems(["fixed", "free"])
        row2 = QWidget()
        hl2 = QHBoxLayout(row2)
        hl2.setContentsMargins(0, 0, 0, 0)
        hl2.addWidget(self.ph_plo)
        hl2.addWidget(self.ph_phi)
        fp.addRow("CSV (time, flux, error, segment[, trend])", self.ph_csv)
        fp.addRow("Segments", self.ph_segs)
        fp.addRow("Trend column", self.ph_trend)
        fp.addRow("", self.ph_gp)
        fp.addRow("P_rot bounds [d]", row2)
        fp.addRow("ln Q0 lower bound", self.ph_lnq0)
        fp.addRow("Dilution per segment", self.ph_dil)
        self.res_box = QGroupBox("Residual photometry for the prefit (activity and the other planet removed)")
        fq = QFormLayout(self.res_box)
        self.res_csv = FileField("Residual photometry (CSV)", "CSV (*.csv *.txt);;All (*)")
        self.res_u1, self.res_u2 = dspin(0, 1, 0.4, 3), dspin(-1, 1, 0.2, 3)
        self.res_mask = dspin(0, 48, 3.0, 2)
        self.res_bin = dspin(0, 120, 10.0, 1)
        urow = QWidget()
        ul_ = QHBoxLayout(urow)
        ul_.setContentsMargins(0, 0, 0, 0)
        ul_.addWidget(self.res_u1)
        ul_.addWidget(self.res_u2)
        fq.addRow("CSV (time, flux, error, segment[, flare flag])", self.res_csv)
        fq.addRow("Template limb darkening (u1, u2)", urow)
        fq.addRow("Mask other transits [h]", self.res_mask)
        fq.addRow("Bin to [min]", self.res_bin)
        self.tabs.addTab(self._page(g, self.rv_box, self.ph_box, self.res_box), "Data")

    def _build_fit(self):
        self.s_box = QGroupBox("Prefit: global search (differential evolution + polishing; only without a start file)")
        self.s_box.setCheckable(True)
        f = QFormLayout(self.s_box)
        self.s_pop, self.s_iter, self.s_seed = ispin(4, 200, 15), ispin(1, 100000, 400), ispin(0, 10**6, 1)
        self.s_win = dspin(0.01, 0.5, 0.15, 3)
        self.s_geom = QCheckBox("also search b/cos i, ΔΩ, M*, R* (more dimensions)")
        self.s_strat = QComboBox()
        self.s_strat.addItems(["best1bin", "rand1bin", "currenttobest1bin", "best2bin", "rand2bin"])
        self.s_strat.setToolTip("rand1bin explores more widely and is less likely to get stuck in one mode")
        self.s_rv = QComboBox()
        self.s_rv.addItems(["auto", "prior", "profiled", "none"])
        self.s_rv.setToolTip("prior: Keplerian fit -> mass prior (v3); profiled: N-body RV with profiled offsets "
                             "(needed for a non-transiting planet); auto chooses")
        self.s_wph = dspin(0, 10, 1.0, 2)
        self.s_wph.setToolTip("weight of the photometric term; 0 with sector times (no double counting, like --no-b-phot)")
        self.s_top, self.s_pol = ispin(1, 100, 10), ispin(1, 10000, 150)
        self.s_init = QLineEdit()
        self.s_init.setPlaceholderText("start files to insert into the population; separated by ;")
        self.s_ck = QLineEdit()
        f.addRow("popsize (members = popsize × ndim)", self.s_pop)
        f.addRow("max. generations", self.s_iter)
        f.addRow("seed", self.s_seed)
        f.addRow("phase window (transiting)", self.s_win)
        f.addRow("", self.s_geom)
        f.addRow("strategy", self.s_strat)
        f.addRow("RV term", self.s_rv)
        f.addRow("photometric-term weight", self.s_wph)
        f.addRow("solutions to polish", self.s_top)
        f.addRow("max. evaluations per polish", self.s_pol)
        f.addRow("inject (init_json)", self.s_init)
        f.addRow("checkpoint (in the output directory; resumes)", self.s_ck)
        o = QGroupBox("Maximum likelihood (L-BFGS-B)")
        fo = QFormLayout(o)
        self.o_nuis, self.o_all = ispin(0, 10000, 50), ispin(0, 10000, 400)
        fo.addRow("iterations step 1 (nuisance parameters)", self.o_nuis)
        fo.addRow("iterations step 2 (all)", self.o_all)
        self.m_box = QGroupBox("MCMC (emcee, DE + snooker)")
        self.m_box.setCheckable(True)
        fm = QFormLayout(self.m_box)
        self.m_nw, self.m_steps = ispin(0, 100000, 0), ispin(1, 10**7, 3000)
        self.m_hess = QCheckBox("Laplace start (Hessian)")
        self.m_back = QLineEdit()
        self.m_burn = QLineEdit()
        self.m_burn.setPlaceholderText("automatic: min(3 τ_max, half the chain)")
        fm.addRow("walkers (0 = 4 × ndim)", self.m_nw)
        fm.addRow("steps (additional when resuming)", self.m_steps)
        fm.addRow("", self.m_hess)
        fm.addRow("backend (in the output directory)", self.m_back)
        fm.addRow("burn-in", self.m_burn)
        self.s_title = self.s_box.title()
        self.tabs.addTab(self._page(self.s_box, o, self.m_box), "Fit")

    def _build_run(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        sg = QGroupBox("Start and computing power")
        fs = QFormLayout(sg)
        self.start_json = FileField("Start file", "JSON (*.json);;All (*)")
        self.start_json.setToolTip("e.g. the start.json of a ttv run; when a start file is set, the prefit "
                                   "(global search) is skipped")
        self.nproc = ispin(1, 256, min(8, os.cpu_count() or 1))
        fs.addRow("Start file (optional)", self.start_json)
        fs.addRow("Processes (--nproc)", self.nproc)
        self.start_json.edit.textChanged.connect(self.update_search_state)
        lay.addWidget(sg)
        bar = QHBoxLayout()
        self.b_start = QPushButton("Start run")
        self.b_eval = QPushButton("Check: lnP at the start")
        self.b_pre = QPushButton("Prefit only")
        self.b_stop = QPushButton("Stop")
        self.b_stop.setEnabled(False)
        self.status = QLabel("not started")
        for b in (self.b_start, self.b_pre, self.b_eval, self.b_stop):
            bar.addWidget(b)
        bar.addWidget(self.status, 1)
        self.b_start.clicked.connect(self.start_run)
        self.b_eval.clicked.connect(self.start_eval)
        self.b_pre.clicked.connect(lambda: self.start_run(["--prefit-only"]))
        self.b_stop.clicked.connect(self.stop_run)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Monospace", 9))
        self.log.setMaximumBlockCount(20000)
        lay.addLayout(bar)
        lay.addWidget(self.log)
        self.tabs.addTab(w, "Run")

    def _build_results(self):
        sp = QSplitter()
        left = QWidget()
        ll = QVBoxLayout(left)
        self.files = QListWidget()
        rb = QPushButton("Refresh")
        rb.clicked.connect(self.refresh_results)
        ll.addWidget(self.files)
        ll.addWidget(rb)
        self.viewer_img = QLabel()
        self.viewer_img.setAlignment(Qt.AlignCenter)
        self.img_area = QScrollArea()
        self.img_area.setWidget(self.viewer_img)
        self.img_area.setWidgetResizable(True)
        self.viewer_txt = QPlainTextEdit()
        self.viewer_txt.setReadOnly(True)
        self.viewer_txt.setFont(QFont("Monospace", 9))
        right = QTabWidget()
        right.addTab(self.img_area, "Figure")
        right.addTab(self.viewer_txt, "Text")
        self.right = right
        sp.addWidget(left)
        sp.addWidget(right)
        sp.setSizes([250, 900])
        self.files.currentTextChanged.connect(self.show_file)
        self.tabs.addTab(sp, "Results")

    # --- configuration <-> widgets -------------------------------------------------
    def load_cfg(self, cfg):
        cfg = merge(DEFAULT_CONFIG, cfg)
        self.name.setText(cfg["name"])
        self.mode.setCurrentText(cfg["mode"])
        self.outdir.setText(cfg["outdir"])
        self.t_start.setText(fmt_opt(cfg["t_start"]))
        self.t_end.setText(fmt_opt(cfg["t_end"]))
        self.dt.setText(fmt_opt(cfg["dt"]))
        self.ms_mu.setValue(cfg["star"]["mstar"][0])
        self.ms_sig.setValue(cfg["star"]["mstar"][1])
        self.rs_mu.setValue(cfg["star"]["rstar"][0])
        self.rs_sig.setValue(cfg["star"]["rstar"][1])
        pls = cfg["planets"] + [dict(DEFAULT_PLANET, name="c", P=6.0)] * (2 - len(cfg["planets"]))
        for box, p in zip(self.pbox, pls[:2]):
            box.load(p)
        self.free_ecc.setChecked(bool(cfg["free_ecc"]))
        self.ecc_max.setValue(cfg["ecc_max"])
        self.dom_auto.setChecked(cfg["dOm_bounds"] is None)
        if cfg["dOm_bounds"]:
            self.dom_lo.setValue(cfg["dOm_bounds"][0])
            self.dom_hi.setValue(cfg["dOm_bounds"][1])
        self.b_max.setValue(cfg["b_max"])
        mt = cfg["midtimes"]
        self.floor.setValue(float(mt.get("floor_min") or 0.0))
        self.jitter.setCurrentText(mt.get("jitter") or "none")
        self.excl.setText(mt.get("exclude_facility_in_photodyn") or "")
        rv = cfg["rv"] or {}
        self.rv_box.setChecked(bool(rv.get("file")))
        self.rv_file.setText(rv.get("file"))
        self.rv_gp.setChecked(bool(rv.get("gp")))
        pb = rv.get("prot_bounds", [4.0, 20.0])
        self.rv_plo.setValue(pb[0])
        self.rv_phi.setValue(pb[1])
        self.rv_share.setText("" if rv.get("share_prot_with") is None else str(rv["share_prot_with"]))
        self.rv_sjit.setValue(float(rv.get("search_jitter", 10.0)))
        ph = cfg["photometry"] or {}
        self.ph_csv.setText(ph.get("csv"))
        self.ph_segs.setText(", ".join(str(s) for s in (ph.get("segments") or [])))
        self.ph_trend.setCurrentText(ph.get("trend", "ignore"))
        self.ph_gp.setChecked(bool(ph.get("gp", True)))
        pb = ph.get("prot_bounds", [4.0, 20.0])
        self.ph_plo.setValue(pb[0])
        self.ph_phi.setValue(pb[1])
        self.ph_lnq0.setValue(float(ph.get("lnq0_min", -2.302585)))
        self.ph_dil.setCurrentText(ph.get("dilution", "fixed"))
        self.res_csv.setText(ph.get("residuals_csv"))
        u = ph.get("ld_u", [0.4, 0.2])
        self.res_u1.setValue(u[0])
        self.res_u2.setValue(u[1])
        self.res_mask.setValue(float(ph.get("mask_hours", 3.0)))
        self.res_bin.setValue(float(ph.get("bin_min", 10.0)))
        sc = cfg["search"]
        self.s_box.setChecked(bool(sc.get("enabled", True)))
        self.s_pop.setValue(int(sc["popsize"]))
        self.s_iter.setValue(int(sc["maxiter"]))
        self.s_seed.setValue(int(sc.get("seed", 1)))
        self.s_win.setValue(float(sc.get("phase_window", 0.15)))
        self.s_geom.setChecked(bool(sc.get("free_geometry", False)))
        self._search_tol = float(sc.get("tol", 1e-7))
        self.s_strat.setCurrentText(sc.get("strategy", "best1bin"))
        self.s_rv.setCurrentText(sc.get("rv_term", "auto"))
        self.s_wph.setValue(float(sc.get("phot_weight", 1.0)))
        self.s_top.setValue(int(sc.get("top", 10)))
        self.s_pol.setValue(int(sc.get("polish_nfev", 150)))
        self.s_init.setText("; ".join(sc.get("init_json") or []))
        self.s_ck.setText(sc.get("checkpoint") or "prefit_checkpoint.npz")
        self.o_nuis.setValue(int(cfg["optimize"]["maxiter_nuis"]))
        self.o_all.setValue(int(cfg["optimize"]["maxiter"]))
        mc = cfg["mcmc"]
        self.m_box.setChecked(bool(mc.get("enabled")))
        self.m_nw.setValue(int(mc.get("nwalkers") or 0))
        self.m_steps.setValue(int(mc.get("steps", 3000)))
        self.m_hess.setChecked(bool(mc.get("init_hessian", True)))
        self.m_back.setText(mc.get("backend") or "")
        self.m_burn.setText(fmt_opt(mc.get("burn")))
        self.start_json.setText(cfg.get("start_json"))
        self.update_search_state()

    def update_search_state(self):
        """The core skips the prefit when a start file is given: show that on the Fit tab."""
        has_start = bool(self.start_json.text())
        self.s_box.setEnabled(not has_start)
        self.s_box.setTitle(self.s_title + ("  [skipped: a start file is set on the Run tab]" if has_start else ""))

    def dump_cfg(self):
        segs = [int(s) for s in self.ph_segs.text().replace(",", " ").split()] or None
        share = self.rv_share.text().strip()
        cfg = dict(
            name=self.name.text().strip() or "object", mode=self.mode.currentText(),
            outdir=self.outdir.text() or "p2p_output", t_start=opt_float(self.t_start.text()),
            t_end=opt_float(self.t_end.text()), dt=opt_float(self.dt.text()),
            star=dict(mstar=[self.ms_mu.value(), self.ms_sig.value()], rstar=[self.rs_mu.value(), self.rs_sig.value()]),
            planets=[b.dump() for b in self.pbox],
            dOm_bounds=None if self.dom_auto.isChecked() else [self.dom_lo.value(), self.dom_hi.value()],
            free_ecc=self.free_ecc.isChecked(), ecc_max=self.ecc_max.value(), b_max=self.b_max.value(),
            midtimes=dict(floor_min=self.floor.value(), jitter=self.jitter.currentText(),
                          exclude_facility_in_photodyn=self.excl.text().strip() or None),
            rv=dict(file=self.rv_file.text(), gp=self.rv_gp.isChecked(),
                    prot_bounds=[self.rv_plo.value(), self.rv_phi.value()],
                    share_prot_with=int(share) if share else None, search_jitter=self.rv_sjit.value())
            if self.rv_box.isChecked() and self.rv_file.text() else None,
            photometry=dict(csv=self.ph_csv.text(), segments=segs, trend=self.ph_trend.currentText(),
                            gp=self.ph_gp.isChecked(), prot_bounds=[self.ph_plo.value(), self.ph_phi.value()],
                            lnq0_min=self.ph_lnq0.value(), dilution=self.ph_dil.currentText(),
                            residuals_csv=self.res_csv.text(), ld_u=[self.res_u1.value(), self.res_u2.value()],
                            mask_hours=self.res_mask.value(), bin_min=self.res_bin.value())
            if (self.ph_csv.text() or self.res_csv.text()) else None,
            search=dict(enabled=self.s_box.isChecked(), popsize=self.s_pop.value(), maxiter=self.s_iter.value(),
                        seed=self.s_seed.value(), phase_window=self.s_win.value(),
                        free_geometry=self.s_geom.isChecked(), tol=self._search_tol,
                        strategy=self.s_strat.currentText(), rv_term=self.s_rv.currentText(),
                        phot_weight=self.s_wph.value(), top=self.s_top.value(), polish_nfev=self.s_pol.value(),
                        init_json=[v.strip() for v in self.s_init.text().split(";") if v.strip()],
                        checkpoint=self.s_ck.text().strip() or "prefit_checkpoint.npz"),
            optimize=dict(maxiter_nuis=self.o_nuis.value(), maxiter=self.o_all.value()),
            mcmc=dict(enabled=self.m_box.isChecked(), nwalkers=self.m_nw.value(), steps=self.m_steps.value(),
                      init_hessian=self.m_hess.isChecked(), backend=self.m_back.text().strip() or None,
                      burn=int(opt_float(self.m_burn.text())) if self.m_burn.text().strip() else None),
            start_json=self.start_json.text())
        return cfg

    def validate(self, cfg):
        errs = []
        names = [p["name"] for p in cfg["planets"]]
        if len(set(names)) != 2 or not all(n.isidentifier() for n in names):
            errs.append("Planet names must be different and consist of letters/digits.")
        if not any(p["transiting"] for p in cfg["planets"]):
            errs.append("At least one planet must transit.")
        for p in cfg["planets"]:
            if p["transiting"] and not p["midtimes"] and not p["segment_times"] and cfg["mode"] == "ttv":
                errs.append(f"Planet {p['name']}: transiting but without mid-times or sector times "
                            "(required in ttv mode).")
            if p["mass_guess"] is not None and not (p["mass_bounds"][0] < p["mass_guess"] < p["mass_bounds"][1]):
                errs.append(f"Planet {p['name']}: the starting mass is not between the bounds.")
        if cfg["mode"] == "photodyn" and not cfg["photometry"]:
            errs.append("Photodyn mode requires a photometry file (Data tab).")
        if self.rv_box.isChecked() and not self.rv_file.text():
            errs.append("RVs are checked but no file is given.")
        return errs

    # --- files --------------------------------------------------------------------
    def new_cfg(self):
        self.path = None
        self.load_cfg(merge(DEFAULT_CONFIG, {"planets": [dict(DEFAULT_PLANET, name="b", P=3.0),
                                                         dict(DEFAULT_PLANET, name="c", P=6.0)]}))
        self.setWindowTitle("photodyn2p – new")

    def open_cfg(self):
        start = os.path.dirname(self.path) if self.path else os.getcwd()
        p, _ = QFileDialog.getOpenFileName(self, "Open configuration", start, "JSON (*.json)",
                                           options=QFileDialog.DontUseNativeDialog)
        if p:
            self.open_path(p)

    def open_path(self, p):
        p = os.path.abspath(p)                    # the core runs in the configuration directory: keep paths absolute
        try:
            with open(p) as fh:
                cfg = json.load(fh)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Error", f"Cannot read {p}:\n{e}")
            return
        base = os.path.dirname(os.path.abspath(p))
        cfg = self._abs_paths(cfg, base)
        self.path = p
        self.load_cfg(cfg)
        self.setWindowTitle(f"photodyn2p – {os.path.basename(p)}")
        self.refresh_results()

    @staticmethod
    def _abs_paths(cfg, base):
        """Relative paths in a configuration -> absolute (the core resolves them relative to the configuration directory)."""
        def ab(v):
            return v if (not v or os.path.isabs(v)) else os.path.normpath(os.path.join(base, v))
        cfg = json.loads(json.dumps(cfg))
        cfg["outdir"] = ab(cfg.get("outdir"))
        cfg["start_json"] = ab(cfg.get("start_json"))
        for p in cfg.get("planets", []):
            p["midtimes"] = ab(p.get("midtimes"))
            p["segment_times"] = ab(p.get("segment_times"))
        if cfg.get("rv"):
            cfg["rv"]["file"] = ab(cfg["rv"].get("file"))
        if cfg.get("photometry"):
            for key in ("csv", "residuals_csv"):
                cfg["photometry"][key] = ab(cfg["photometry"].get(key))
        if cfg.get("search"):
            cfg["search"]["init_json"] = [ab(v) for v in (cfg["search"].get("init_json") or [])]
        return cfg

    def save_cfg(self):
        if not self.path:
            return self.save_cfg_as()
        cfg = self.dump_cfg()
        with open(self.path, "w") as fh:
            json.dump(cfg, fh, indent=2)
        self.statusBar().showMessage(f"saved: {self.path}", 4000)
        return True

    def save_cfg_as(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save configuration", self.path or os.getcwd(), "JSON (*.json)",
                                           options=QFileDialog.DontUseNativeDialog)
        if not p:
            return False
        if not p.endswith(".json"):
            p += ".json"
        self.path = os.path.abspath(p)
        self.setWindowTitle(f"photodyn2p – {os.path.basename(p)}")
        return self.save_cfg()

    # --- runs -----------------------------------------------------------------------
    def start_run(self, extra=None):
        if self.proc is not None:
            QMessageBox.information(self, "Busy", "A run is already in progress.")
            return
        cfg = self.dump_cfg()
        errs = self.validate(cfg)
        if errs:
            QMessageBox.warning(self, "Incomplete configuration", "\n".join(errs))
            return
        if not self.save_cfg():
            return
        args = [CORE, self.path, "--nproc", str(self.nproc.value())] + (extra or [])
        self.log.clear()
        self.log.appendPlainText("$ " + " ".join([sys.executable] + args) + "\n")
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.setWorkingDirectory(os.path.dirname(os.path.abspath(self.path)))
        self.proc.readyReadStandardOutput.connect(self.read_output)
        self.proc.finished.connect(self.finished)
        env = self.proc.processEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        self.proc.setProcessEnvironment(env)
        self.proc.start(sys.executable, args)
        self.b_start.setEnabled(False)
        self.b_eval.setEnabled(False)
        self.b_pre.setEnabled(False)
        self.b_stop.setEnabled(True)
        self.status.setText("running…")
        self.tabs.setCurrentIndex(4)

    def open_manual(self):
        if os.path.isfile(MANUAL):
            QDesktopServices.openUrl(QUrl.fromLocalFile(MANUAL))
        else:
            QMessageBox.information(self, "User manual", f"The manual was not found:\n{MANUAL}\n\n"
                                    "Place photodyn2p_manual.pdf next to photodyn2p_gui.py.")

    def about(self):
        QMessageBox.about(self, "About photodyn2p",
                          "photodyn2p — TTV and photodynamical model for two planets.\n\n"
                          "Graphical front end for photodyn2p.py (TTVFast + batman + celerite2 + emcee). "
                          "The GUI writes a JSON configuration and runs the core as a separate process.\n\n"
                          "See Help > User manual (F1) for a step-by-step guide with test examples.")

    def start_eval(self):
        self.start_run(["--eval-only"])

    def stop_run(self):
        if self.proc is None:
            return
        self.proc.terminate()                             # SIGTERM: the core shuts down its workers
        QTimer.singleShot(5000, lambda: self.proc.kill() if self.proc is not None else None)
        self.status.setText("stopping…")

    def read_output(self):
        txt = bytes(self.proc.readAllStandardOutput()).decode(errors="replace").replace("\r", "\n")
        for line in txt.splitlines():
            if line.strip():
                self.log.appendPlainText(line)
                # progress lines of the core: prefit generations, optimisation steps and MCMC steps
                if "MCMC step" in line or "generation" in line or "step " in line:
                    self.status.setText(line.strip()[:110])

    def finished(self, code, _status):
        self.read_output()
        self.log.appendPlainText(f"\n[process finished, code {code}]")
        self.proc = None
        self.b_start.setEnabled(True)
        self.b_eval.setEnabled(True)
        self.b_pre.setEnabled(True)
        self.b_stop.setEnabled(False)
        self.status.setText("finished" if code == 0 else f"stopped / error (code {code})")
        self.refresh_results()

    # --- results ---------------------------------------------------------------------
    def outdir_abs(self):
        o = self.outdir.text() or "p2p_output"
        if not os.path.isabs(o) and self.path:
            o = os.path.join(os.path.dirname(os.path.abspath(self.path)), o)
        return o

    def refresh_results(self):
        self.files.clear()
        o = self.outdir_abs()
        if os.path.isdir(o):
            for f in sorted(os.listdir(o)):
                if f.endswith((".png", ".txt", ".json")):
                    self.files.addItem(f)
            items = self.files.findItems("summary.txt", Qt.MatchExactly)
            if items:
                self.files.setCurrentItem(items[0])

    def show_file(self, name):
        if not name:
            return
        p = os.path.join(self.outdir_abs(), name)
        if name.endswith(".png"):
            pm = QPixmap(p)
            w = max(400, self.img_area.viewport().width() - 20)
            self.viewer_img.setPixmap(pm.scaledToWidth(min(w, pm.width()), Qt.SmoothTransformation)
                                      if pm.width() > w else pm)
            self.right.setCurrentIndex(0)
        else:
            try:
                with open(p) as fh:
                    self.viewer_txt.setPlainText(fh.read())
            except OSError as e:
                self.viewer_txt.setPlainText(str(e))
            self.right.setCurrentIndex(1)

    def closeEvent(self, ev):
        if self.proc is not None:
            r = QMessageBox.question(self, "Run in progress", "A run is still in progress. Stop it and quit?")
            if r != QMessageBox.Yes:
                ev.ignore()
                return
            self.proc.kill()
        ev.accept()


def main():
    app = QApplication(sys.argv)
    w = Main(sys.argv[1] if len(sys.argv) > 1 else None)
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
