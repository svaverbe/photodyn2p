#!/usr/bin/env python3
"""Build photodyn2p_manual.pdf: English user manual for the photodyn2p GUI, with worked test examples."""
import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, PageBreak, PageTemplate, Paragraph,
                                Preformatted, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "photodyn2p_manual.pdf")
FIGDIR = os.environ.get("FIGDIR", HERE)

F = "/usr/share/fonts/truetype/dejavu/"
if not os.path.isfile(F + "DejaVuSerif.ttf"):
    import matplotlib
    F = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf") + os.sep
for n, f in (("Serif", "DejaVuSerif.ttf"), ("Serif-B", "DejaVuSerif-Bold.ttf"), ("Serif-I", "DejaVuSerif-Italic.ttf"),
             ("Serif-BI", "DejaVuSerif-BoldItalic.ttf"), ("Sans", "DejaVuSans.ttf"), ("Sans-B", "DejaVuSans-Bold.ttf")):
    pdfmetrics.registerFont(TTFont(n, F + f))
pdfmetrics.registerFontFamily("Serif", normal="Serif", bold="Serif-B", italic="Serif-I", boldItalic="Serif-BI")

ACC = colors.HexColor("#1f3a5f")
body = ParagraphStyle("body", fontName="Serif", fontSize=9.6, leading=13.4, alignment=TA_JUSTIFY, spaceAfter=5)
h1 = ParagraphStyle("h1", fontName="Sans-B", fontSize=15, leading=19, textColor=ACC, spaceBefore=12, spaceAfter=7)
h2 = ParagraphStyle("h2", fontName="Sans-B", fontSize=11.5, leading=15, textColor=ACC, spaceBefore=9, spaceAfter=4)
cell = ParagraphStyle("cell", fontName="Sans", fontSize=8.2, leading=10.6)
cellh = ParagraphStyle("cellh", parent=cell, fontName="Sans-B", textColor=colors.white)
cap = ParagraphStyle("cap", fontName="Sans", fontSize=8.2, leading=10.8, textColor=colors.HexColor("#444444"),
                     spaceBefore=3, spaceAfter=8)
code = ParagraphStyle("code", fontName="Courier", fontSize=7.9, leading=10.2)
note = ParagraphStyle("note", parent=body, fontSize=9.0, leading=12.4, backColor=colors.HexColor("#eef3f8"),
                      borderColor=colors.HexColor("#9fb6cf"), borderWidth=0.5, borderPadding=6, spaceBefore=6,
                      spaceAfter=10)
W = A4[0] - 4.2 * cm
CNT = {'Table': 0, 'Figure': 0}


def P(t, s=body):
    return Paragraph(t, s)


def m(t):
    return f'<font name="Courier" size="8.8">{t}</font>'


def EQ(t):
    return Paragraph(t, ParagraphStyle("eqc", parent=body, alignment=1, fontSize=10.2, leading=15, spaceBefore=3,
                                       spaceAfter=7))


def C(t):
    tb = Table([[Preformatted(t.strip("\n"), code)]], colWidths=[W])
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f5f7")),
                            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8cdd4")),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return tb


def T(rows, widths, caption=None):
    data = [[Paragraph(str(c), cellh if i == 0 else cell) for c in r] for i, r in enumerate(rows)]
    tb = Table(data, colWidths=[w * cm for w in widths], repeatRows=1)
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), ACC), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#b8c2cc")),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f6")]),
                            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    out = [tb]
    if caption:
        CNT["Table"] += 1
        caption = re.sub(r"<b>Table \d+\.</b>", "<b>Table %d.</b>" % CNT["Table"], caption)
        out.append(Paragraph(caption, cap))
    else:
        out.append(Spacer(1, 6))
    return out


def FIG(name, width_cm, caption):
    p = os.path.join(FIGDIR, name)
    from PIL import Image as PI
    w, h = PI.open(p).size
    wd = width_cm * cm
    CNT["Figure"] += 1
    caption = re.sub(r"<b>Figure \d+\.</b>", "<b>Figure %d.</b>" % CNT["Figure"], caption)
    return [KeepTogether([Image(p, width=wd, height=wd * h / w), Paragraph(caption, cap)])]


class Doc(BaseDocTemplate):
    def __init__(self, fn):
        super().__init__(fn, pagesize=A4, leftMargin=2.1 * cm, rightMargin=2.1 * cm, topMargin=2 * cm,
                         bottomMargin=2 * cm, title="photodyn2p GUI — user manual", author="photodyn2p")
        fr = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([PageTemplate(id="p", frames=[fr], onPage=self.deco)])

    def deco(self, c, d):
        c.saveState()
        c.setFont("Sans", 7.5)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawString(2.1 * cm, 1.2 * cm, "photodyn2p GUI — user manual with test examples")
        c.drawRightString(A4[0] - 2.1 * cm, 1.2 * cm, str(d.page))
        c.restoreState()

    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and f.style.name in ("h1", "h2"):
            lvl = 0 if f.style.name == "h1" else 1
            key = "h%d" % id(f)
            self.canv.bookmarkPage(key)
            self.notify("TOCEntry", (lvl, f.getPlainText(), self.page, key))


S = []
S += [Spacer(1, 2.2 * cm),
      P("photodyn2p", ParagraphStyle("t0", fontName="Sans-B", fontSize=30, leading=36, textColor=ACC)),
      P("Graphical user interface — user manual with test examples",
        ParagraphStyle("t1", fontName="Sans", fontSize=15, leading=20, textColor=ACC, spaceAfter=18)),
      P("A TTV and photodynamical model for two planets: transit times, radial velocities and light curves, "
        "with a global search (differential evolution), a maximum-likelihood fit and MCMC. This manual explains "
        "the GUI tab by tab and walks through four test examples with known or reference answers, so that every "
        "part of the program can be checked step by step.", body),
      Spacer(1, 10)]
toc = TableOfContents()
toc.levelStyles = [ParagraphStyle("toc0", fontName="Sans-B", fontSize=9.5, leading=14, leftIndent=0),
                   ParagraphStyle("toc1", fontName="Sans", fontSize=8.8, leading=12, leftIndent=14)]
S += [P("Contents", h2), toc, PageBreak()]

# ============================================================================ 1
S += [P("1. What the program does", h1),
      P("photodyn2p models two gravitationally interacting planets around one star. The dynamics are computed "
        "with the N-body code TTVFast; from it the program predicts transit times, stellar radial velocities "
        "(RVs) and, in photodynamical mode, the light curve with every individual transit placed at its own "
        "predicted time. Either planet may transit or not; a non-transiting planet is detected only through the "
        "transit timing variations (TTVs) it induces on the other planet and through the RVs."),
      P("The program has two parts. The <b>core</b>, " + m("photodyn2p.py") + ", does all the computing and can run "
        "without the GUI from the command line. The <b>GUI</b>, " + m("photodyn2p_gui.py") + ", is a front end: it "
        "reads and writes a JSON configuration file and starts the core as a separate process. Long runs therefore "
        "never block the window, and every run made from the GUI can be repeated exactly from the command line. "
        "The GUI, the log output of the core and this manual are in English."),
      *T([["Mode", "Data used", "Typical use"],
          ["ttv", "mid-transit times (per planet), optionally sector times of a weak planet, RVs",
           "fast (milliseconds per evaluation); global search for the dynamical configuration"],
          ["photodyn", "light curves (per segment, optional GP per segment), mid-times, RVs",
           "slower (tens of ms per evaluation); start from the result of a ttv run"]],
         [2.0, 7.0, 7.8], "<b>Table 1.</b> The two modes."),
      P("<b>Workflow in one sentence.</b> A <i>prefit</i> (global search on a cheap objective) finds the right "
        "dynamical configuration; a <i>maximum-likelihood</i> (ML) fit refines it on the full likelihood; an "
        "optional <i>MCMC</i> gives posterior distributions. Sections 5 and 6 describe the first two stages in full; the examples in Section 7 follow exactly this "
        "path, and Section 8 is a step-by-step recipe for a new object."),
      P("<b>Parameters.</b> Masses are fitted as log10(m/M*), because TTVs and RVs constrain mass ratios; masses in "
        "M⊕ or M_J are derived. Periods, phases and eccentricity vectors are <i>osculating</i> Jacobi elements at "
        "the start time t_start; the summary also reports the mean ephemeris, which is what you compare with "
        "observed periods. Times are BTJD (BJD − 2457000); BJD, BJD − 2450000 and BJD − 2400000 are recognised "
        "automatically.")]

# ============================================================================ 2
S += [P("2. Installation and starting", h1),
      P("The program needs Python 3.7 or newer with numpy, scipy, matplotlib, ttvfast, batman-package, celerite2 "
        "and emcee (h5py for MCMC back-ends), and PyQt5 for the GUI. In the WSL environment used for TOI-3686:"),
      C("""PY=/home/siegfried/anaconda3/envs/science/bin/python
$PY -m pip install pyqt5                      # once, for the GUI
cd /mnt/d/EXPLORE/TOI3686/photodyn2p
$PY photodyn2p_gui.py                         # empty configuration
$PY photodyn2p_gui.py examples_synthetic/example1_ttv_both/config.json   # open an example"""),
      P("On Windows 11, WSL shows Linux windows directly (WSLg); no X server is needed. Keep " + m("photodyn2p.py") +
        ", " + m("photodyn2p_gui.py") + " and " + m("photodyn2p_manual.pdf") + " in the same directory: the GUI "
        "starts the core next to itself, and <b>Help → User manual</b> (F1) opens this manual."),
      P("<b>Test package.</b> The directory " + m("examples_synthetic/") + " contains three synthetic examples with "
        "a known truth (" + m("truth.json") + "); they are generated by " + m("make_synthetic_examples.py") +
        ", which can recreate them at any time:"),
      C("$PY make_synthetic_examples.py --outdir examples_synthetic --seed 42")]

# ============================================================================ 3
S += [P("3. Quick start: the five-minute check", h1),
      P("This check confirms that the installation, the GUI and the core work together, without any long "
        "computation. It evaluates the log-posterior at the true parameters of example 1."),
      P("1. Start the GUI and choose <b>File → Open…</b> " + m("examples_synthetic/example1_ttv_both/config.json") +
        ".<br/>2. On the <b>Run</b> tab, set <b>Start file</b> to " + m("truth_start.json") + ": type the name "
        "(a relative path is taken relative to the configuration file), or click <b>…</b> — the file dialog opens "
        "in the directory of the configuration, where the file is listed — "
        "and <b>Processes</b> to 1.<br/>3. Press <b>Check: lnP at the start</b>. The core starts; after a few "
        "seconds the log ends with:"),
      C("""  mid-times: lnL = 412.1
  RV: lnL = -93.5
Start: lnP = 325.60

[process finished, code 0]"""),
      P("The status next to the buttons changes from <i>not started</i> to <i>running…</i> to <i>finished</i>. If "
        "you see " + m("Start: lnP = 325.60") + ", everything is in order. Clear the start file again before "
        "continuing with Section 7: with a start file, the prefit is skipped.", note)]

# ============================================================================ 4
S += [P("4. The GUI tab by tab", h1),
      P("The window has six tabs and three menus. <b>File</b>: New, Open, Save, Save as, Quit (the configuration "
        "is saved as JSON; starting a run saves it first). <b>Run</b>: the same actions as the buttons on the Run "
        "tab. <b>Help</b>: this manual (F1) and an About box."),
      P("4.1 Object & star", h2),
      *FIG("shot_object.png", 15.5, "<b>Figure 1.</b> Tab <i>Object & star</i> with example 1 loaded."),
      *T([["Field", "Meaning"],
          ["Name", "Label of the object; appears in the summary and the figure titles."],
          ["Mode", "ttv or photodyn (Table 1)."],
          ["Output directory", "All results are written here; relative paths are relative to the configuration file."],
          ["t_start, t_end", "Integration window [BTJD]. Empty = 1 d before the first and after the last data point. "
           "<b>Osculating elements hold at t_start</b>: a start file from a run with a different t_start is "
           "only approximately transferable, so set t_start explicitly when several runs must fit together."],
          ["N-body step dt", "TTVFast time step [d]; empty = min(P)/32."],
          ["Star: M*, R*", "Gaussian priors (mean, σ). The transits constrain the stellar density ρ* = M*/R*³; "
           "the priors decide where along that ridge M* and R* end up."]],
         [3.6, 13.2], "<b>Table 2.</b> Fields on the Object & star tab."),
      P("4.2 Planets", h2),
      *FIG("shot_planets.png", 15.5, "<b>Figure 2.</b> Tab <i>Planets</i>: one column per planet. Planet 1 is the "
                                      "reference (Ω = 0); ΔΩ of planet 2 is relative to it."),
      *T([["Field", "Meaning"],
          ["Name", "Letters/digits only (b, c, …); the two names must differ. Used in all parameter names."],
          ["transiting", "Unticked = non-transiting: the planet has cos i instead of b and no transits."],
          ["P [d]", "Observed <b>mean</b> period; also the starting value of the osculating period."],
          ["P search width", "Relative half-width of the osculating period (0.003 = ±0.3%). Keep it realistic: "
           "too wide makes the prefit slow (Sections 5.6 and 11)."],
          ["T0", "Optional transit or conjunction time; empty = taken from the mid-times."],
          ["Mid-times", "File with mid-transit times of this planet (Section 9)."],
          ["Mass unit, Mass (start)", "Display unit (Mearth/Mjup). Starting mass: empty = <i>automatic</i>; the "
           "prefit or a start file sets the actual value."],
          ["Mass (bounds)", "Search range at M* = prior mean."],
          ["Rp/R*, prior", "Radius ratio (photodyn mode); optional Gaussian prior, e.g. from undiluted ground-based "
           "photometry."],
          ["b (start) / cos i (start)", "Impact parameter (transiting) or cos i (non-transiting). <b>For a "
           "non-transiting planet, cos i must exceed R*/a</b>, otherwise the starting geometry transits and is "
           "rejected (Sections 5.2 and 11)."],
          ["no transit (|b| ≥ 1)", "Non-transiting: forbid geometries that would transit."],
          ["e cos ω, e sin ω", "Starting eccentricity vector."],
          ["Prefit: P bounds, Phase window, e-vector", "Explicit P range; half-width of the phase window (fraction of "
           "the orbit); bound on |e cos ω|, |e sin ω| and the cut in e."],
          ["Sector times", "File in the format of b_times.dat: measured transit time and local period of a weak "
           "planet per sector (prefit term)."],
          ["template on the residual photometry", "Prefit term that fits a transit template of this planet to the "
           "residual light curve (Data tab)."]],
         [4.2, 12.6], "<b>Table 3.</b> Fields per planet."),
      P("Below the two columns, <b>Orbits</b> sets free eccentricities, e max, the ΔΩ bounds (automatic: ±45° if "
        "both planets transit, ±180° otherwise) and |b| max for transiting planets."),
      P("4.3 Data", h2),
      *FIG("shot_data.png", 15.5, "<b>Figure 3.</b> Tab <i>Data</i>: mid-time settings, RVs, photometry and the "
                                   "residual photometry for the prefit."),
      *T([["Field", "Meaning"],
          ["Error floor [min]", "Added in quadrature to every mid-time error (ground-based errors are often "
           "underestimated)."],
          ["Timing jitter", "none, or free: a fitted global jitter instead of a fixed floor."],
          ["Omit in photodyn (facility)", "In photodyn mode, mid-times whose facility contains this word are left "
           "out (they are already in the light curve; default TESS)."],
          ["Use radial velocities", "File (time rv err instrument); offset and jitter per instrument are fitted."],
          ["quasi-periodic GP", "Stellar activity in the RVs (RotationTerm); P_rot bounds; share P_rot with a "
           "photometry segment (number) or keep its own."],
          ["Jitter in the search", "RV jitter assumed in the prefit."],
          ["Photometry", "CSV (time, flux, error, segment[, trend]); segments to use; trend column: ignore, or "
           "multiply to rebuild flux × trend for detrended data; GP per segment with P_rot bounds and ln Q0 lower "
           "bound; dilution per segment fixed or free."],
          ["Residual photometry", "For the prefit template term: activity and the other planet removed; template "
           "limb darkening, mask around the other planet's transits, binning."]],
         [4.2, 12.6], "<b>Table 4.</b> Fields on the Data tab."),
      P("4.4 Fit", h2),
      *FIG("shot_fit.png", 15.5, "<b>Figure 4.</b> Tab <i>Fit</i>. The prefit box turns grey with the note "
                                  "<i>[skipped: a start file is set on the Run tab]</i> when a start file is set."),
      *T([["Group / field", "Meaning"],
          ["Prefit", "Global search by differential evolution, then least-squares polishing of the best distinct "
           "solutions. Only runs without a start file. Full description: Section 5."],
          ["popsize, max. generations, seed", "Population = popsize × number of search dimensions (rounded up to a "
           "power of two); generations; random seed."],
          ["phase window", "Default half-width of the phase window for transiting planets."],
          ["also search b/cos i, ΔΩ, M*, R*", "Normally fixed in the prefit; tick to search them too (more "
           "dimensions, slower)."],
          ["strategy", "best1bin (fast convergence) or rand1bin (explores more widely)."],
          ["RV term", "prior: Keplerian fit → mass prior; profiled: N-body RVs with profiled offsets (needed for a "
           "non-transiting planet); auto chooses."],
          ["photometric-term weight", "0 when sector times are used (no double counting)."],
          ["solutions to polish, max. evaluations per polish", "Number of distinct candidates polished, and the "
           "effort per candidate."],
          ["inject (init_json)", "Start files inserted into the population (also when resuming)."],
          ["checkpoint", "File in the output directory; <b>an existing checkpoint is resumed</b>. If it already "
           "reached max. generations, no new generations run (only injection and polishing)."],
          ["Maximum likelihood", "L-BFGS-B: step 1 over the nuisance parameters only, step 2 over all. Full "
           "description: Section 6."],
          ["MCMC", "emcee with DE and snooker moves: walkers (0 = 4 × ndim), steps (<i>additional</i> when "
           "resuming), Laplace start from the Hessian, HDF5 back-end in the output directory, burn-in."]],
         [4.6, 12.2], "<b>Table 5.</b> Fields on the Fit tab."),
      P("4.5 Run", h2),
      *FIG("shot_run.png", 15.5, "<b>Figure 5.</b> Tab <i>Run</i>: start file and number of processes, the four "
                                  "buttons, the status and the live log of the core."),
      P("<b>Start file (optional)</b>: a " + m("start.json") + " or " + m("prefit_start.json") + " of an earlier "
        "run; when set, the prefit is skipped. <b>Processes</b>: number of parallel worker processes (use the "
        "number of physical cores, or the number of threads on a hyper-threaded laptop). Buttons: <b>Start "
        "run</b> (prefit if applicable, ML fit, figures, MCMC if enabled), <b>Prefit only</b>, <b>Check: lnP at "
        "the start</b> (evaluates the start and stops) and <b>Stop</b> (the core shuts down its workers; after "
        "5 s the process is killed). The status shows the latest progress line."),
      P("4.6 Results", h2),
      *FIG("shot_results.png", 15.5, "<b>Figure 6.</b> Tab <i>Results</i> after example 1: the files of the output "
                                      "directory on the left, the selected figure on the right (TTVs of both planets)."),
      P("The list shows the PNG, TXT and JSON files of the output directory; " + m("summary.txt") + " is selected "
        "automatically after a run. Figures appear on the <i>Figure</i> tab, text and JSON on the <i>Text</i> tab. "
        "<b>Refresh</b> re-reads the directory (useful while an MCMC is running).")]

# ============================================================================ 5 (new)
S += [PageBreak(), P("5. How the prefit works", h1),
      P("The dynamics of two interacting planets are strongly multimodal: many combinations of masses, periods, "
        "phases and eccentricities reproduce part of the data, and a local optimiser started at a random point "
        "almost always ends in the wrong mode. The prefit therefore searches globally, on an objective that is "
        "cheap to evaluate (only TTVFast plus simple sums, no light-curve model and no Gaussian processes), and "
        "hands its best solution to the maximum-likelihood fit (Section 6). This section describes exactly what "
        "it computes. The prefit runs when no start file is set and <b>Prefit</b> is ticked on the Fit tab; "
        "<b>Prefit only</b> stops after it."),
      P("5.1 Free and fixed parameters", h2),
      P("Per planet, five parameters are free: the mass ratio log10(m/M*), the osculating period P, the orbital "
        "phase φ at t_start and the eccentricity vector (e cos ω, e sin ω). The geometry is <b>fixed</b> at its "
        "starting values: the impact parameter b (or cos i for a non-transiting planet), ΔΩ (0), and M* and R* "
        "(the means of their priors). TTVs and RVs depend only weakly on these, and fixing them keeps the search "
        "small: 10 dimensions for two planets. With <b>also search b/cos i, ΔΩ, M*, R*</b> on the Fit tab they "
        "are searched too."),
      *T([["Parameter", "Search range", "Set on"],
          ["log10(m/M*)", "the mass bounds of the planet (converted at M* = prior mean)", "Planets: Mass (bounds)"],
          ["P (osculating)", "P·(1 ∓ P search width), or the explicit P bounds", "Planets: P, P search width, "
           "P bounds"],
          ["φ (phase at t_start)", "planet with mid-times: ± phase window around the phase predicted by the linear "
           "ephemeris of its mid-times (wrapped modulo 1); otherwise the full range 0–1", "Planets: Phase window; "
           "Fit: phase window (default)"],
          ["e cos ω, e sin ω", "± the e-vector bound; candidates with e above the cut are rejected",
           "Planets: e-vector (bound, cut)"]],
         [3.3, 8.7, 4.8], "<b>Table 0.</b> Free parameters of the prefit and their ranges."),
      P("5.2 The objective function", h2),
      P("This section explains, step by step and without assuming prior knowledge, what the prefit computes for "
        "every candidate set of parameters, and how to read the numbers it prints. The worked numbers all come from "
        "example 1 (Section 7.1), so you can check them against your own run."),
      P("<b>Residuals and χ².</b> A <i>residual</i> is the difference between a measurement and what the model "
        "predicts for it. Dividing it by the uncertainty of the measurement turns it into a pure number: a "
        "residual of 1 means ‘one standard deviation off’. Squaring and adding these numbers gives χ² "
        "(‘chi-squared’):"),
      EQ("χ<super>2</super> = Σ<sub><i>i</i></sub> [ (data<sub><i>i</i></sub> − model<sub><i>i</i></sub>) / "
         "σ<sub><i>i</i></sub> ]<super>2</super>"),
      P("A smaller χ² means a better fit. If the model is right and the uncertainties are realistic, each term is "
        "about 1 on average, so a good fit has χ² ≈ the number of measurements N; more precisely about N minus the "
        "number of fitted parameters, because the fit also absorbs a little of the noise. A χ² much larger than N "
        "means the model misses something (or the errors are too small); much smaller means the errors are too large."),
      P("<b>The four terms.</b> The prefit adds four such terms; each is used only when its data are configured:"),
      EQ("χ<super>2</super><sub>pre</sub> = χ<super>2</super><sub>tt</sub> + χ<super>2</super><sub>RV</sub> + "
         "w<sub>phot</sub> Δχ<super>2</super><sub>phot</sub> + χ<super>2</super><sub>sec</sub>"),
      P("It is ‘cheap’ because only the N-body code TTVFast is run for each candidate; no light curve is computed and "
        "no Gaussian process (Section 6.1) is evaluated. The prefit prints the total and its parts for every polished "
        "solution (Section 5.5)."),
      P("<b>Term 1 — mid-transit times, χ²<sub>tt</sub>.</b> A <i>mid-transit time</i> is the moment at which a "
        "planet is exactly in front of the centre of the star, measured from a light curve. If a planet orbited "
        "alone, its transits would be strictly periodic: t<sub>n</sub> = T<sub>0</sub> + nP. The gravitational pull "
        "of the other planet makes them arrive a little early or late: these <i>transit timing variations</i> (TTVs) "
        "carry the information on the masses and orbits. For each candidate, TTVFast integrates the orbits and "
        "returns the model transit times. Each observed time t<sub>i</sub> is paired with the <b>nearest</b> model "
        "transit t<sub>mod</sub> (this needs TTVs smaller than half a period: in example 1 the TTVs of b are 80 min "
        "and half its period is 36 h). Then"),
      EQ("χ<super>2</super><sub>tt</sub> = Σ<sub>planets</sub> Σ<sub><i>i</i></sub> [ (t<sub><i>i</i></sub> − "
         "t<sub>mod</sub>) / s<sub><i>i</i></sub> ]<super>2</super>,    s<sub><i>i</i></sub><super>2</super> = "
         "σ<sub>stat</sub><super>2</super> + σ<sub>sys</sub><super>2</super> + σ<sub>floor</sub><super>2</super>."),
      P("σ<sub>stat</sub> and σ<sub>sys</sub> are the statistical and systematic errors of the file. The "
        "<b>error floor</b> σ<sub>floor</sub> (Data tab) is added in quadrature because published timing errors, "
        "especially from small ground-based telescopes, are often too optimistic. In example 1 the floor is 1 min, so "
        "the 4-min errors of b become s = √(4² + 1²) = 4.12 min and the 1.5-min errors of c become 1.80 min. All "
        "mid-times are used in the prefit, including those from TESS: the prefit does not model the light curve, so "
        "nothing is counted twice."),
      P("<i>Worked example.</i> The prefit first prints the χ² of a plain linear ephemeris (no TTVs) as a "
        "reference: 7056 for the 50 times of b and 428 for the 35 times of c. These huge values show that the TTVs "
        "are strongly detected. At the polished solution the values are 37.6 and 23.2. With the enlarged errors one "
        "expects about 50 × (4/4.12)² ≈ 47 for b and 35 × (1.5/1.80)² ≈ 24 for c: the floor makes χ² smaller than N, "
        "as it should when the floor was not needed (the synthetic errors are exact)."),
      P("<b>Term 2 — radial velocities, χ²<sub>RV</sub>.</b> A planet makes its star move in a small orbit around "
        "their common centre of mass. A spectrograph measures the star’s velocity along the line of sight, the "
        "<i>radial velocity</i> (RV), from the Doppler shift of its spectral lines. For a planet on a circular orbit "
        "the RV is a sine curve with the orbital period of the planet. Its semi-amplitude K (in m/s) is related to "
        "the planet mass m by"),
      EQ("K = (2πG/P)<super>1/3</super> m sin i / M*<super>2/3</super>     (for m much smaller than M*),"),
      P("where G is the gravitational constant, P the orbital period, M* the stellar mass and i the inclination of "
        "the orbit (i = 90° when we see the orbit edge-on). The RVs measure m sin i, not m itself; for a transiting "
        "planet i is close to 90° and sin i ≈ 1, so they measure the mass. Two practical points matter for every "
        "form of the term. First, every spectrograph has its own zero point: when the file is read, the data of each "
        "instrument are shifted so that their weighted mean is zero, and a constant <i>offset</i> per instrument "
        "still has to be determined. Second, the TTVs constrain the planet masses only relative to the stellar mass "
        "(through m/M*), whereas the RVs give an independent handle on the absolute masses: the two kinds of data "
        "complement each other. The prefit can use the RVs in three ways, chosen on the Fit tab (RV term); with "
        "<i>auto</i> the program chooses as described below."),
      P("<b>(a) prior — a mass prior from a sine fit.</b> This form is computed once, when the run starts, and "
        "costs nothing during the search. For every planet that has mid-times, its linear ephemeris (period P and "
        "transit time T from a straight-line fit to its mid-times) fixes when the star moves fastest towards and "
        "away from us; only the amplitude is unknown. The RVs are therefore fitted with one sine curve per planet, "
        "−K sin(2π(t − T)/P), plus one offset per instrument. Because the periods and phases are fixed, this is a "
        "<i>linear</i> least-squares problem: its best values and uncertainties K ± σ<sub>K</sub> follow exactly, "
        "without any search. Each K is converted into a mass m<sub>RV</sub> with the formula above (sin i = 1). That "
        "conversion uses the stellar mass, and the stellar mass is itself uncertain (Object & star tab), so the "
        "uncertainty of the mass combines both sources:"),
      EQ("σ<sub>m</sub><super>2</super> = (m<sub>RV</sub> σ<sub>K</sub> / K)<super>2</super> + "
         "(⅔ m<sub>RV</sub> σ<sub>M*</sub> / M*)<super>2</super>."),
      P("The factor ⅔ comes from m ∝ M*<super>2/3</super>: a 9% uncertainty on M* gives a 6% uncertainty on m. During "
        "the search, every candidate pays a penalty for masses that disagree with these values, "
        "Σ [(m − m<sub>RV</sub>)/σ<sub>m</sub>]<super>2</super>, i.e. one χ² term per planet: a candidate whose mass "
        "is 2σ<sub>m</sub> away from the RV mass pays 4. A planet whose RV signal is not significant (K &lt; "
        "3σ<sub>K</sub>) gets no prior, because a non-detection would only add noise; the log reports this. The "
        "simplifications are acceptable for a search: a circular orbit (the eccentricities of close-in planets are "
        "small, and the full model of Section 6 uses the exact N-body RVs), and fixed periods and phases (the prefit "
        "only needs a rough mass). <i>auto</i> chooses this form when both planets transit and at least one of them "
        "has mid-times."),
      P("<b>(b) profiled — the N-body RVs, with offsets solved directly.</b> If a planet does not transit, its "
        "period and phase are unknown before the search, so no sine curve can be fitted in advance. Instead, for "
        "every candidate the stellar velocity is computed by TTVFast from both planets, including their mutual "
        "interaction, at the times of the RV measurements. The offsets are not searched as extra parameters; for a "
        "given model, the best offset of an instrument is simply the weighted mean of its residuals, and it is "
        "calculated directly (‘profiled’). The errors are enlarged by a fixed <i>jitter</i>, an extra noise term for "
        "stellar and instrumental noise that the quoted errors do not include (Data tab: Jitter in the search, "
        "default 10 m/s). The term is the χ² of the RV residuals. It is slower than the prior form but uses the RVs "
        "fully; for a non-transiting planet it is often the only way to constrain its period and phase besides the "
        "TTVs. <i>auto</i> chooses this form when a planet does not transit."),
      P("<b>(c) none.</b> No RV term, used automatically when no RV file is given. You can also choose it to test "
        "how much the RVs influence the prefit result."),
      *T([["Form", "Computed", "Cost", "auto chooses it when"],
          ["prior", "once: sine fit → mass ± error per planet", "none per candidate",
           "both planets transit and at least one has mid-times"],
          ["profiled", "per candidate: N-body RVs, offsets profiled, fixed jitter", "one RV evaluation",
           "a planet does not transit"],
          ["none", "nothing", "none", "there is no RV file"]],
         [1.8, 6.6, 3.4, 5.0], "<b>Table 0.</b> Summary of the three forms of the RV term."),
      P("<i>Worked example.</i> In example 1 both planets transit, so the prior form is used. The log reports "
        "K = 7.9 ± 0.9 m/s → m sin i = 17.83 ± 2.1 M⊕ for b and K = 66.7 ± 0.8 m/s → 0.6009 ± 0.021 M_J for c. Note "
        "that the mass of b is 9σ<sub>K</sub>-significant in K but only ±12% in mass, partly because of the 5% M* "
        "uncertainty of the example. At the polished solution (m_b = 16.2 M⊕, m_c = 0.592 M_J) the two prior terms "
        "are ((16.2 − 17.83)/2.1)² = 0.6 and ((0.592 − 0.6009)/0.021)² = 0.2, printed as ‘prior m_b 0.7’ and "
        "‘prior m_c 0.2’ (the log rounds the masses). In example 2, c does not transit and the profiled form is used."),
      P("<b>Term 3 — photometric term, Δχ²<sub>phot</sub>.</b> A weak planet may have transits too shallow to "
        "measure individual mid-times, yet visible in the light curve when many transits are combined. This term "
        "lets the prefit use them. It needs a <i>residual light curve</i> (Data tab): the light curve after "
        "removing the stellar variability and the transits of the other planet, so that only the weak planet and "
        "noise remain. It is prepared once:"),
      P("(a) points with a flare flag are removed; (b) points within the mask time around the transits of the other "
        "planet are removed; (c) per segment the median is subtracted, and the errors are multiplied by max(1, s/ē), "
        "where s is the actual scatter and ē the median quoted error, so that the errors match the real noise; "
        "(d) the data are averaged into bins of the bin time. A <i>template</i> ψ(t) is computed: the shape of one "
        "transit of the weak planet (batman, Section 6.1) with its Rp/R* and b from the Planets tab, a/R* from its "
        "period and the stellar priors, and the template limb darkening (Data tab).", ParagraphStyle("ind", parent=body, leftIndent=12)),
      P("For each candidate, TTVFast gives the predicted transit times of the weak planet; the template is placed at "
        "each of them, giving a model ψ<sub>i</sub> at every data point d<sub>i</sub> (with weight w<sub>i</sub> = "
        "1/σ<sub>i</sub><super>2</super>). The true radius of the planet is not known precisely, so the depth is "
        "allowed to scale by a factor A, the same for all segments (one planet has one depth). The best A follows "
        "directly from a weighted average, and the term compares the fit with the model ‘no planet’:"),
      EQ("A = clip( Σ w<sub><i>i</i></sub> ψ<sub><i>i</i></sub> d<sub><i>i</i></sub> / Σ w<sub><i>i</i></sub> "
         "ψ<sub><i>i</i></sub><super>2</super>, 0, 1.5 ),    Δχ<super>2</super><sub>phot</sub> = Σ "
         "w<sub><i>i</i></sub> (d<sub><i>i</i></sub> − A ψ<sub><i>i</i></sub>)<super>2</super> − Σ "
         "w<sub><i>i</i></sub> d<sub><i>i</i></sub><super>2</super>."),
      P("A = 1 means the template depth; A is kept between 0 (a transit cannot make the star brighter) and 1.5 (to "
        "avoid fitting a noise feature with an unphysically deep transit). Δχ²<sub>phot</sub> is never positive. "
        "Without clipping it equals −(S/N)², where S/N is the signal-to-noise ratio with which the transits are seen "
        "at the predicted times. Interpretation: a candidate that puts the transits where the data show dips gets a "
        "strongly negative value (in the TOI-3686 analysis, −32 for S/N 5.7); a candidate that puts them at the wrong "
        "times gets a value near zero. Even without any real transit, the noise gives about −0.5 on average and "
        "rarely below −3, so values above about −3 mean ‘not seen’. The weight w<sub>phot</sub> (Fit tab) is 1, or 0 "
        "when sector times (term 4) are used for the same planet, because both come from the same light curve."),
      P("<b>Term 4 — sector times, χ²<sub>sec</sub>.</b> An alternative way to use a weak planet: first measure, in "
        "each segment (e.g. a TESS sector) separately, when it transits and with which local period, and then "
        "require the model to reproduce these measurements. The file (Planets tab: Sector times) gives per segment "
        "a reference time T<sub>s</sub> ± σ<sub>T</sub>, a local period P<sub>s</sub> ± σ<sub>P</sub>, and their "
        "correlation ρ (how much an error in T tends to go with an error in P; between −1 and 1). For each candidate "
        "the model transits inside the segment are fitted with a straight line, which gives a model time "
        "T<sub>mod</sub> (at the epoch nearest to T<sub>s</sub>) and a model period P<sub>mod</sub>. With the "
        "differences δT = T<sub>mod</sub> − T<sub>s</sub> and δP = P<sub>mod</sub> − P<sub>s</sub>:"),
      EQ("χ<super>2</super><sub>sec</sub> = Σ<sub>segments</sub> [ (δT/σ<sub>T</sub>)<super>2</super> − "
         "2ρ (δT/σ<sub>T</sub>)(δP/σ<sub>P</sub>) + (δP/σ<sub>P</sub>)<super>2</super> ] / (1 − ρ<super>2</super>)."),
      P("For ρ = 0 this is simply the sum of two ordinary χ² terms; the correlation term avoids counting the same "
        "information twice. Example: if the model transit in a segment is 36 min away from a measurement with "
        "σ<sub>T</sub> = 18 min (and the period matches), that segment contributes about (36/18)² = 4. The term is "
        "local: a model that is off by more than half a period in a segment is paired with the wrong transit. Use it "
        "together with good starting points or a wide search."),
      P("<b>What a good total looks like.</b> In example 1 the total at the solution is 37.6 + 23.2 + 0.7 + 0.2 = "
        "61.7. Expected: about 47 + 24 for the mid-times plus about 1 per prior, minus roughly the 10 free "
        "parameters, i.e. about 63. A total close to this expectation, with mid-time rms values close to the errors, "
        "indicates the right solution; a much larger total indicates a wrong mode or underestimated errors."),
      P("<b>Rejected candidates.</b> A candidate gets the penalty value 10<super>9</super> instead of a χ² if it is "
        "physically or practically impossible: outside the search ranges; dynamically unstable by the Hill criterion "
        "(Section 6.1); an eccentricity at or above e max, or above the e-vector cut; a non-transiting planet with "
        "<i>no transit</i> that would transit; a failure of TTVFast; or fewer than 80% of the expected number of "
        "transits of a planet with mid-times (the planet would miss transits). A population that consists only of "
        "10<super>9</super> values means that every candidate is forbidden: check the fixed geometry first "
        "(Section 11)."),
      P("5.3 The global search: differential evolution", h2),
      P("The search uses the differential-evolution solver of scipy. The population has popsize × N members "
        "(N = number of free parameters), rounded up to a power of two because it is initialised with a Sobol "
        "sequence that covers the search ranges evenly (popsize 15 and N = 10 give 256 members). In every "
        "generation each member gets a trial vector: a difference of two other members, scaled by a random "
        "factor between 0.5 and 1.0 (dithering), is added to the best member (best1bin) or to a random member "
        "(rand1bin), and each coordinate is taken from the trial with probability 0.7 (recombination). The trial "
        "replaces the member if its χ²<sub>pre</sub> is lower. With several processes, all trials of a "
        "generation are evaluated in parallel (deferred updating)."),
      P("The search always runs the full number of generations (no convergence test). Every 5 generations the "
        "population, its χ² values and the generation number are saved to the checkpoint in the output "
        "directory, and the log prints the best and the median value. A new run with the same checkpoint resumes "
        "from it, provided the free parameters are the same; if it already completed max. generations, only "
        "injection and polishing are done. The random seed is the configured seed plus the number of completed "
        "generations, so a resumed run does not repeat the same random numbers. <b>Inject (init_json)</b> places "
        "the given start files into the population, replacing its worst members; this also works when resuming."),
      P("5.4 Polishing", h2),
      P("Differential evolution finds the right region but converges slowly inside it. The best <b>solutions to "
        "polish</b> are therefore refined by a local least-squares fit. Candidates are taken in order of "
        "χ²<sub>pre</sub>, and a candidate is skipped if it duplicates one already chosen, i.e. if all its phases "
        "are within 0.02 and all its periods within a relative 10<super>−3</super> of that one. Each candidate is "
        "polished with scipy’s least_squares (trust-region reflective, with the search ranges as bounds) on the "
        "vector of all normalised residuals behind χ²<sub>pre</sub>: the mid-time residuals, the RV prior or "
        "profiled RV residuals, the weighted photometric residuals and the whitened sector-time residuals. For a "
        "planet with a photometric term, the depth factor A is an explicit extra parameter (0–1.5); at the optimum "
        "this is equivalent to solving it analytically. Parameter scales are 5 × the typical step of each "
        "parameter; the effort per candidate is <b>max. evaluations per polish</b>."),
      P("The polished candidates are ranked by their total. The best becomes the starting point of the ML fit; "
        "its Rp/R* is set from the fitted depth, Rp/R* = (template Rp/R*) × √A with A limited to 0.25–1.5."),
      P("5.5 Reading the prefit output", h2),
      C("""Prefit: 10 free parameters (log_q_b, P_b, phi_b, ecosw_b, esinw_b, log_q_c, P_c, phi_c,
        ecosw_c, esinw_c); fixed: b/cos i, dOm, M*, R*
  mid-times b: 50 (all facilities), linear ephemeris chi2 = 7056.4
  mid-times c: 35 (all facilities), linear ephemeris chi2 = 428.2
  RV prior b: K = 7.9 ± 0.9 m/s -> m sin i = 17.83 ± 2.1 Mearth
  RV prior c: K = 66.7 ± 0.8 m/s -> m sin i = 0.6009 ± 0.021 Mjup
Global search: population 256 members, strategy best1bin, generations 0 -> 120, 4 process(es)
  generation    5: best   77553.6  median 5708120.8  (12 s)
  ...
  generation  120: best    2878.7  median   16224.6  (241 s)
Polishing 5 solutions (max. 150 evaluations each):
  1/5: total 61.7
Polished solutions, best first:
  total 61.7 | chi2_b 37.6 (rms 3.6 min) | chi2_c 23.2 (rms 1.5 min) | prior m_b 0.7 | prior m_c 0.2 |
  m_b 16.2 e_b 0.046 | m_c 0.592 e_c 0.025 | TTV_b 1.32 h | TTV_c 0.16 h"""),
      P("The log first states the free parameters and, per planet, the χ² of a <b>linear</b> ephemeris: a "
        "reference for how strong the TTVs are. In example 1 it is 7056 for b and 428 for c; the dynamical solution "
        "brings the total down to 61.7. Next come the RV mass priors (here for both planets: m sin i = 17.8 ± 2.1 "
        "M⊕ and 0.601 ± 0.021 M_J). For each polished solution the ranking lists the total "
        "and its parts: χ² and rms of the mid-times per planet, the RV prior term (or the profiled RV χ²), "
        "Δχ²<sub>phot</sub> with the depth A, the sector-time χ², and mass, e and TTV half-amplitude per planet. "
        "A good solution has a total close to the number of data points (here 85 mid-times and 2 priors → 61.7; "
        "the free parameters absorb part of the noise) and mid-time rms values close to the errors (3.6 and 1.5 "
        "min against 4 and 1.5 min). In this run all five polished candidates reached the same total."),
      P("Several candidates with the same total are the same solution found from different starts, which is a "
        "good sign. Candidates with clearly higher totals are other modes; they stay in " + m("prefit_results.json") +
        " for comparison. <b>prefit_results.json</b> contains the RV prior used and all polished solutions with "
        "their diagnostics; <b>prefit_start.json</b> is the best one as a start file. With the command-line option "
        + m("--prefit-eval START.json") + " the same diagnostics are printed for any start file, without a "
        "search: useful to compare a candidate from elsewhere."),
      P("5.6 Practical settings", h2),
      *T([["Setting", "Advice"],
          ["P, P search width", "Use the observed mean period and a width of ~0.003 (±0.3%). The osculating period "
           "differs from the mean one by much less than that; a wider range costs many generations."],
          ["Phase window", "0.05–0.15 for planets with mid-times. Planets without mid-times always search the full "
           "phase range."],
          ["Mass bounds", "Physically plausible, about a factor 10–50 wide; the search is in log10(m/M*)."],
          ["popsize, max. generations", "15 and 100–400. Judge the result after polishing: the best DE value may "
           "still be far above the polished total."],
          ["Strategy, seed", "best1bin converges fastest. If the polished solutions do not agree or look poor, "
           "repeat with rand1bin and another seed, each with its own checkpoint, and inject good candidates."],
          ["Solutions to polish", "5–10. More candidates show more of the alternative modes."],
          ["Non-transiting planet", "cos i (start) must exceed R*/a (geometry fixed!); RV term profiled (auto)."]],
         [3.6, 13.2], "<b>Table 0.</b> Practical prefit settings.")]

# ============================================================================ 6 (new)
S += [PageBreak(), P("6. How the maximum-likelihood fit works", h1),
      P("The ML fit maximises the full log-posterior over all parameters, starting from the prefit solution or "
        "from a start file. The log line " + m("prefit solution in the full model: lnP = ...") + " shows the "
        "value of the prefit solution in this full model. The fit then runs in two steps and writes "
        + m("start.json") + ", " + m("results.json") + ", " + m("summary.txt") + " and the figures."),
      P("6.1 The log-posterior", h2),
      P("The prefit uses a simplified χ²; the maximum-likelihood fit uses the full statistical model. This section "
        "builds it up from the basic ideas; no prior knowledge is assumed."),
      P("<b>Likelihood.</b> The <i>likelihood</i> L is the probability of obtaining the observed data if the model "
        "with given parameters were true. For one measurement x with a Gaussian (normal) error of standard deviation "
        "σ around the model value μ, this probability density is"),
      EQ("L = (2πσ<super>2</super>)<super>−1/2</super> exp[ −(x − μ)<super>2</super> / 2σ<super>2</super> ],   so   "
         "ln L = −½ (x − μ)<super>2</super>/σ<super>2</super> − ½ ln(2πσ<super>2</super>)."),
      P("For independent measurements the likelihoods multiply, so the logarithms add. The first part is −½ times "
        "the χ² of Section 5.2; the second part does not depend on the model but on the uncertainties. Maximising "
        "ln L is therefore the same as minimising χ² as long as the uncertainties are fixed; the second part "
        "matters when uncertainties are themselves fitted (jitter, Section 6.1, ‘RVs’). Working with logarithms "
        "avoids numbers that are too small for a computer (a product of thousands of probabilities)."),
      P("<b>Why ln L can be positive.</b> A probability density can exceed 1 when σ is small. Mid-times are "
        "expressed in days, so σ ≈ 0.003 d gives −½ ln(2πσ²) ≈ +5 per measurement. In example 1 the normalisation of "
        "the 85 mid-times adds up to about +449; with χ² = 73 at the true parameters this gives ln L = 449 − 73/2 = "
        "412.1, the value printed by the quick start (Section 3). Only <i>differences</i> in ln p between models or "
        "parameter sets are meaningful; the absolute value depends on units and on the number of data points."),
      P("<b>Prior and posterior.</b> The <i>prior</i> π(θ) expresses what is known about the parameters θ before "
        "looking at these data (for instance the stellar mass from spectroscopy). Bayes’ theorem combines both into "
        "the <i>posterior</i>, the probability of the parameters given the data: p(θ | data) ∝ L(data | θ) π(θ). "
        "The program maximises the logarithm of this product:"),
      EQ("ln p = ln π + Σ<sub>segments</sub> ln L<sub>phot</sub> + ln L<sub>tt</sub> + ln L<sub>sec</sub> + "
         "ln L<sub>RV</sub>"),
      P("Strictly speaking, maximising ln p (which includes the priors) gives the <i>maximum a posteriori</i> "
        "(MAP) solution; the program calls it the ML fit, as is common. Each term is described below."),
      P("<b>Photometry, ln L<sub>phot</sub></b> (photodyn mode; one term per segment). The light curve is "
        "normalised by its median and expressed in parts per thousand (ppt): y = 1000 (flux/median − 1), so the "
        "star out of transit is near 0 and a transit is a negative dip. The model has three parts. "
        "(1) <i>Transits.</i> Every transit is computed separately with the code batman, at its own mid-time from "
        "TTVFast and with its own impact parameter b (the projected distance between planet and star centre in "
        "units of R*, taken from the sky positions of TTVFast; it can change slowly if the orbits precess). The "
        "transit shape is set by the radius ratio Rp/R* (depth ≈ (Rp/R*)²), by b and a/R* (duration and shape), and "
        "by <i>limb darkening</i>: the stellar disc is darker at the edge, which rounds the bottom of the transit. "
        "The program uses the quadratic law with coefficients u1 = 2√q1 q2 and u2 = √q1 (1 − 2q2); any q1, q2 "
        "between 0 and 1 gives a physically possible star (Kipping 2013). For long exposures (more than 14.4 min) "
        "the model is averaged over the exposure (7 sub-points), because a transit changes during one exposure. "
        "(2) <i>Dilution</i> D multiplies the transit depths: light from another star in the aperture makes transits "
        "shallower (D &lt; 1). (3) A <i>zero point</i> F0 shifts the whole segment. The residual is"),
      EQ("r<sub><i>i</i></sub> = y<sub><i>i</i></sub> − F0 − D Σ<sub>planets</sub> transit<sub><i>i</i></sub>."),
      P("<i>Without a GP</i>, the residuals are treated as independent Gaussian noise with variance "
        "σ<sub><i>i</i></sub><super>2</super> + σ<sub>jit</sub><super>2</super>: the quoted error plus a fitted "
        "<i>jitter</i> for noise that the errors do not include; ln L is the sum of the per-point expression above. "
        "<i>With a GP</i> (Gaussian process), the residuals may also contain correlated noise: a spotted star "
        "rotates and its brightness rises and falls smoothly over days. Neighbouring points then deviate in the "
        "same direction, which independent noise cannot describe. A GP models this through a <i>covariance</i>: how "
        "strongly two points correlate as a function of their time difference. The program uses the RotationTerm of "
        "celerite2, which describes rotation as two damped oscillations, at the rotation period P_rot and at "
        "P_rot/2 (spots on opposite hemispheres). Its parameters are: σ, the amplitude of the variability (ppt); "
        "P_rot; Q0, how coherent the oscillation at P_rot/2 is (large Q0: many cycles before the pattern changes); "
        "ΔQ, the extra coherence of the main oscillation; and f, the relative strength of the P_rot/2 oscillation. "
        "The log-likelihood is that of a multivariate Gaussian, ln L = −½ r<super>T</super> K<super>−1</super> r − "
        "½ ln|K| − (n/2) ln 2π, where K is the covariance matrix (GP plus σ<sub><i>i</i></sub><super>2</super> + "
        "σ<sub>jit</sub><super>2</super> on the diagonal); celerite2 computes it in a time proportional to the "
        "number of points. In this way the GP and the transits are fitted <i>together</i>, so the stellar "
        "variability cannot be mistaken for a transit or the other way round."),
      P("<i>Worked example.</i> In example 3 (no GP, white noise of 0.6 ppt) each of the ~3900 points of a segment "
        "contributes on average −½ ln(2π · 0.6²) − ½ ≈ −0.91, so about −3530 per segment; the program prints −3555 "
        "and −3571 at the true parameters, slightly lower because the jitter keeps its default starting value there."),
      P("<b>Mid-times, ln L<sub>tt</sub>.</b> The same Gaussian expression for every mid-time used, with variance "
        "v<sub><i>i</i></sub> = s<sub><i>i</i></sub><super>2</super> from Section 5.2, plus a fitted timing jitter "
        "squared if <i>Timing jitter = free</i> (then the data themselves determine how much extra scatter there "
        "is, instead of a fixed floor):"),
      EQ("ln L<sub>tt</sub> = −½ Σ<sub><i>i</i></sub> [ (t<sub><i>i</i></sub> − t<sub>mod</sub>)<super>2</super> / "
         "v<sub><i>i</i></sub> + ln(2π v<sub><i>i</i></sub>) ]."),
      P("In photodyn mode, mid-times whose facility contains the omit word (default TESS) are left out: those "
        "transits are already in the light curve, and using both would count the same information twice."),
      P("<b>Sector times, ln L<sub>sec</sub></b> (ttv mode only): the term of Section 5.2 as a Gaussian "
        "log-likelihood (−½ χ²<sub>sec</sub> plus its normalisation). In photodyn mode the light curve itself is "
        "fitted, so this term is not used."),
      P("<b>RVs, ln L<sub>RV</sub>.</b> The model RV is the stellar velocity computed by TTVFast from the two "
        "planets (including their mutual interaction). The residual of measurement i of instrument k is r = "
        "rv<sub><i>i</i></sub> − rv<sub>N-body</sub>(t<sub><i>i</i></sub>) − offset<sub><i>k</i></sub>; every "
        "instrument has its own offset and its own jitter σ<sub>jit,<i>k</i></sub>, which collects stellar "
        "‘noise’ (granulation, pulsations) and instrumental effects not in the quoted errors. Without a GP, ln L is "
        "the Gaussian sum with variance err² + σ<sub>jit,<i>k</i></sub><super>2</super>; with a GP, the same "
        "RotationTerm describes activity-induced RV variations, with its own P_rot or the P_rot of a photometry "
        "segment observed at the same time (Data tab: Share P_rot with segment). In example 1 the RV term at the true "
        "parameters is −93.5 for 30 RVs with 3 m/s errors."),
      P("<b>Priors, ln π.</b>", body),
      *T([["Parameter", "Prior", "Meaning"],
          ["Most parameters", "uniform within the bounds", "No preference inside the allowed range."],
          ["M*, R*", "Gaussian (Object & star tab)", "Knowledge from stellar characterisation; ln π gets "
           "−½((M* − μ)/σ)² and the same for R*."],
          ["log10(m/M*), ln σ, ln P_rot, ln Q0, …", "uniform in the logarithm", "‘Scale-free’: every factor 10 is "
           "equally likely a priori, appropriate when even the order of magnitude is uncertain."],
          ["Rp/R*", "optional Gaussian (Planets tab)", "E.g. from undiluted ground-based photometry; breaks the "
           "degeneracy between Rp/R* and the dilution D."],
          ["e cos ω, e sin ω", "uniform, corrected by −ln e", "Sampling the e-vector uniformly would favour large e "
           "(a ring of radius e has an area ∝ e); subtracting ln e makes the prior uniform in e."],
          ["Hard rejections", "ln π = −∞", "Orbits closer than 2√3 ≈ 3.46 mutual Hill radii (a stability criterion "
           "for two planets, Gladman 1993; the mutual Hill radius is ((m1 + m2)/3M*)<super>1/3</super> × the mean "
           "semi-major axis); e ≥ e max; a non-transiting planet with <i>no transit</i> that would transit."]],
         [3.6, 3.8, 9.4], "<b>Table 0.</b> Priors of the full model."),
            P("6.2 Parameters of the noise models", h2),
      P("Besides the planets and the star, the full model contains parameters that describe the noise and the "
        "calibration of the data. They appear in " + m("start.json") + " and " + m("results.json") + " under the "
        "names given below; N is the segment number (e.g. " + m("s18_ln_sig") + " for segment 18) and k the "
        "instrument number (instruments are numbered alphabetically from 0, as listed in the log). Parameters "
        "whose name starts with ln are natural logarithms: the fit works with ln σ instead of σ, so that a step of "
        "0.1 always means a 10% change, whatever the size of σ, and a uniform prior on ln σ treats every order of "
        "magnitude equally."),
      P("<b>The quasi-periodic Gaussian process.</b> Starspots make a star brighter and fainter as it rotates, with "
        "a pattern that repeats roughly every rotation period but slowly changes as spots appear and disappear. The "
        "GP (RotationTerm of celerite2) describes this as the sum of two <i>damped oscillators</i>, one at the "
        "rotation period P_rot and one at P_rot/2. A damped oscillator is a signal that oscillates with a fixed "
        "period but whose phase and amplitude drift randomly: it ‘forgets’ its pattern over a damping time. Its "
        "quality factor Q sets that time: the oscillation stays coherent for about Q·P/π, i.e. roughly Q/3 cycles. "
        "Q = ½ is the smallest value (no oscillation, just a smooth random curve); Q = 10 means a pattern that "
        "survives a few cycles. For the two components:"),
      EQ("primary component, period P_rot:   Q<sub>1</sub> = ½ + Q0 + ΔQ,   variance σ<super>2</super> / (1 + f)"),
      EQ("secondary component, period P_rot/2:   Q<sub>2</sub> = ½ + Q0,   variance f σ<super>2</super> / (1 + f)"),
      P("So σ<super>2</super> is the total variance of the stellar signal, divided between the two components in "
        "the ratio 1 : f; Q0 sets the coherence of the secondary component, and ΔQ makes the primary component more "
        "coherent than the secondary (ΔQ ≥ 0 because it is fitted as ln ΔQ)."),
      *T([["Name", "Symbol, unit", "Range; start", "Meaning"],
          ["sN_ln_sig", "ln σ, σ in ppt", "ln 0.1 – ln 50; start ln 7 (or gp_start)",
           "Standard deviation of the stellar variability in segment N."],
          ["sN_ln_Prot", "ln P_rot, days", "ln of the P_rot bounds (Data tab, default 4–20 d); start: geometric mean",
           "Rotation period. The RV GP may share it (Data tab: Share P_rot with segment)."],
          ["sN_ln_Q0", "ln Q0", "ln Q0 lower bound (Data tab, default ln 0.1 = −2.30) – 5; start 2.5",
           "Coherence of the P_rot/2 component (Q2 = ½ + Q0)."],
          ["sN_ln_dQ", "ln ΔQ", "−10 – 10; start 0",
           "Extra coherence of the main component (Q1 = Q2 + ΔQ). Very negative: both components equally coherent."],
          ["sN_f_gp", "f", "0.001 – 1; start 0.3", "Variance of the P_rot/2 component relative to the P_rot component."],
          ["sN_ln_jit", "ln σ<sub>jit</sub>, ppt", "ln 0.001 – ln 10; start ln 0.05",
           "White noise added in quadrature to the flux errors (also without GP)."],
          ["sN_F0", "F0, ppt", "−30 – 30; start 0", "Zero point of the segment (the out-of-transit level)."],
          ["sN_D", "D", "0.5 – 1.5; start 1 (only with dilution = free)",
           "Factor on all transit depths of the segment: D &lt; 1 if other stars dilute the light."],
          ["rv_ln_sig", "ln σ, σ in m/s", "ln 0.05 – ln 50; start ln 30", "Amplitude of the activity signal in the RVs."],
          ["rv_ln_Prot", "ln P_rot, days", "ln of the RV P_rot bounds", "Only if the RV GP does not share P_rot."],
          ["rv_ln_Q0, rv_ln_dQ, rv_f_gp", "as above", "0 – 10 (start 2); −10 – 10 (0); 0.001 – 1 (0.4)",
           "Coherence and shape of the RV activity signal."],
          ["rv_off_k", "offset, m/s", "−100 – 100; start 0", "Zero point of instrument k (after subtracting its mean)."],
          ["rv_ln_jit_k", "ln σ<sub>jit</sub>, m/s", "ln 0.1 – ln 100; start ln 5", "Extra white noise of instrument k."],
          ["ln_ttjit", "ln σ<sub>tt</sub>, days", "ln 10<super>−5</super> – ln 0.1; start ln 10<super>−3</super>",
           "Only with Timing jitter = free: extra scatter of the mid-times, instead of a fixed floor."]],
         [3.1, 2.6, 4.7, 6.4], "<b>Table 0.</b> Parameters of the noise models (N = segment, k = instrument)."),
      P("<b>Starting values and practical advice.</b> The GP parameters of a segment can be given starting values "
        "in the configuration (photometry.gp_start, per segment number), for example from an earlier detrending "
        "of the light curve; otherwise the starts in the table are used, and step 1 of the optimiser (Section 6.3) "
        "adjusts them before the planets move. A GP parameter at a bound is not necessarily a problem: ln Q0 at its "
        "lower bound simply means a smooth, non-oscillating variability, and the low end of Q hardly changes the "
        "model. P_rot at a bound is worth a look: widen the bounds (the true period should lie well inside them). "
        "A jitter at its upper bound or an F0 far from zero usually points to a data problem (a wrong segment, a "
        "trend that was not removed). For TOI-3686, for comparison, the fits give P_rot ≈ 5.4 d and σ ≈ 7–10 ppt in "
        "the TESS sectors."),
      P("6.3 The optimiser", h2),
      P("<b>Two steps.</b> Parameters are either dynamical (mass ratios, P, φ, e-vectors, b/cos i, ΔΩ, M*, R*) or "
        "nuisance parameters (Rp/R*, q1, q2, GP and jitter parameters, F0, D, RV offsets and jitters, timing "
        "jitter). <b>Step 1</b> optimises only the nuisance parameters with the dynamics fixed; TTVFast results are "
        "cached, so an evaluation costs only the non-dynamical parts (light curves, GPs, RVs); in example 1 "
        "an evaluation took 1.1 ms in step 1 against 7.9 ms in step 2. This puts "
        "the noise model in place before the dynamics move. <b>Step 2</b> optimises all parameters together. The "
        "maximum numbers of iterations are set on the Fit tab (iterations step 1 and step 2)."),
      P("<b>Algorithm.</b> Both steps use L-BFGS-B (scipy) on −ln p, with the parameter bounds as box constraints. "
        "To make the problem well conditioned, every parameter is rescaled, u = (x − x<sub>min</sub>)/τ, with a "
        "typical scale τ (Table 11): one unit of u is a physically meaningful step for every parameter. The "
        "gradient is a forward difference with step 10<super>−4</super> in u (backward at an upper bound); its "
        "N + 1 evaluations are spread over the worker processes, which is where <b>Processes</b> speeds up the "
        "fit. The objective is divided by the norm of the starting gradient, so that the convergence criteria "
        "of L-BFGS-B mean the same for every problem. A step result is accepted only if it improves ln p."),
      *T([["Parameter", "Scale τ", "Parameter", "Scale τ"],
          ["log10(m/M*)", "0.02", "b (transiting)", "0.01"],
          ["P", "8 × 10<super>−6</super> P", "cos i (non-transiting)", "0.005"],
          ["φ", "2 × 10<super>−4</super>", "ΔΩ", "0.5°"],
          ["e cos ω, e sin ω", "0.005", "all others", "1/20 of the range"]],
         [3.4, 3.0, 4.0, 3.0], "<b>Table 0.</b> Typical scales used by the optimiser."),
      P("<b>Messages.</b> Each step reports ln p before and after, the iterations, evaluations, time per "
        "evaluation and the stop message of L-BFGS-B. <i>CONVERGENCE</i>: the gradient or the relative change "
        "became small — converged. <i>STOP: TOTAL NO. OF ITERATIONS REACHED LIMIT</i>: the maximum was reached; "
        "run again from " + m("start.json") + " or raise the limit. <i>ABNORMAL</i>: the line search could not "
        "find a better point, usually on a flat or slightly noisy optimum; check ln p and the residuals. In "
        "example 1, step 1 converged after 16 iterations and step 2 ended ABNORMAL at ln p = 351.76 after 77 "
        "iterations; a restart from its start.json gave 351.76 again (step 2: 0 iterations), so that end "
        "point is the optimum."),
      P("6.4 Output and checks", h2),
      P(m("start.json") + " holds all ML parameters as a start file (for a photodyn run, a restart or an MCMC); "
        + m("results.json") + " adds the derived quantities; " + m("summary.txt") + " gives per planet the mass, "
        "the osculating elements at t_start, the <b>mean ephemeris</b> (fitted to all model transits, with the "
        "TTV half-amplitude), e, ω, i, the impact parameter at conjunction, a/R*, the RV semi-amplitude K and, "
        "for planets with mid-times, n, rms, maximum and χ² of their residuals; and ΔΩ, the mutual inclination "
        "and the mean period ratio. Checklist for a good ML solution:"),
      *T([["Check", "What to look for"],
          ["Mid-times", "rms close to the errors (including the floor); χ² close to n."],
          ["RVs", "Residuals without structure in rv.png; K plausible."],
          ["Photometry", "Rp/R* not at a bound; transits of the weak planet visible in photometry.png."],
          ["Parameters at bounds", "Look in results.json. GP parameters at a bound are often harmless; geometry or "
           "masses at a bound are not: widen the bound or check the start."],
          ["Stability of the optimum", "Run again from start.json: ln p should not increase by more than ~1."],
          ["Comparison with the prefit", "The ML ln p is higher than the prefit value printed before step 1; "
           "masses and TTV amplitudes should not move far. A large jump means the prefit solution was not good."]],
         [3.6, 13.2], "<b>Table 0.</b> Checklist for an ML solution.")]

# ============================================================================ 5
S += [PageBreak(), P("7. Test examples step by step", h1),
      P("The three synthetic examples share one system, generated with the physics of the program itself: a "
        "sub-Neptune b and a warm Jupiter c just wide of the 2:1 resonance (period ratio 2.049), around a solar-type "
        "star. Because the truth is known, each example tests whether a part of the program recovers it. The "
        "fourth example checks the GUI against the TOI-3686 analysis."),
      *T([["Quantity", "Planet b", "Planet c"],
          ["Osculating P at t_start = 999.0 [d]", "3.0000", "6.1500"],
          ["Mean period [d]", "3.00127", "6.14895"],
          ["Mass", "15.0 M⊕", "0.600 M_J"],
          ["e cos ω, e sin ω (e)", "0.030, −0.040 (0.050)", "0.010, 0.015 (0.018)"],
          ["Impact parameter b; Rp/R*", "0.30; 0.030", "0.20; 0.100 (example 2: b = 1.60, no transit)"],
          ["TTV half-amplitude", "80.4 min", "8.9 min"],
          ["Star; limb darkening", "M* = 1.00 M☉, R* = 1.00 R☉", "q1 = 0.36, q2 = 0.30"]],
         [5.2, 5.0, 6.6], "<b>Table 6.</b> True parameters of the synthetic system (examples_synthetic/truth.json)."),
      P("The run times below were measured with 4 processes; with 8 threads on a laptop they are similar. The "
        "prefit is stochastic: with the same seed and number of processes it is reproducible, but small "
        "differences in the last digits between machines are normal."),
      P("7.1 Example 1 — ttv mode, both planets transiting", h2),
      P("<b>Data</b>: 50 mid-times of b (σ = 4 min), 35 of c (σ = 1.5 min), 30 RVs (σ = 3 m/s, one instrument). "
        "<b>Tests</b>: the prefit, the ML fit, the TTV and RV figures."),
      P("1. <b>File → Open…</b> " + m("examples_synthetic/example1_ttv_both/config.json") + ". Check the Planets tab: "
        "P = 3.0013 and 6.1490 d (the mean periods), P search width 0.003, mass bounds 1–60 M⊕ and 0.1–3 M_J."
        "<br/>2. Run tab: leave the start file empty; Processes = 4 (or 8).<br/>3. Press <b>Start run</b>. The "
        "log shows the generations of the prefit, then the polishing, the ML fit and the figures."),
      C("""  generation    5: best   77553.6  median 5708120.8  (12 s)
  ...                                   (the best value falls steadily; at generation 120 it is
  generation  120: best    2878.7  median   16224.6  (241 s)      still in the thousands - normal)
Polishing 5 solutions (max. 150 evaluations each):
  1/5: total 61.7                       <- polishing reaches the solution: all five give 61.7
  prefit solution in the full model: lnP = 330.41
  step 1 (nuisance parameters): lnP 330.4 -> 351.4  (16 iterations, ...)
  step 2 (all parameters): lnP 351.4 -> 351.8  (77 iterations, ...)
Done -> .../output  (start.json, results.json, summary.txt, figures)"""),
      P("<b>Expected result</b> (about 5.5 min: prefit 4.5 min, ML 1 min): lnP = 351.76; the truth gives 325.60, "
        "so the fit is better than the truth. Part of the difference is the fit to the noise (about half the number "
        "of free parameters, ~8.5); the rest comes from the RV offset and jitter, which the truth start file does not "
        "contain (they keep their default values there: the log reports 15 of 17 parameters read)."),
      *T([["Quantity", "Truth", "Fit (ML)"],
          ["m_b; m_c", "15.0 M⊕; 0.600 M_J", "16.3 M⊕; 0.597 M_J"],
          ["e_b; e_c", "0.050; 0.018", "0.047; 0.022"],
          ["Mean periods", "3.00127; 6.14895 d", "3.001265; 6.148951 d"],
          ["TTV half-amplitudes", "80.4; 8.9 min", "78.4; 9.5 min"],
          ["rms of the mid-times", "4 min; 1.5 min (input σ)", "3.7 min; 1.45 min"]],
         [4.5, 5.6, 6.7], "<b>Table 7.</b> Example 1: truth and ML result."),
      P("In ttv mode the impact parameters stay at their starting values (0.30): mid-times do not constrain them. "
        "The mass of b deviates by 8%, within what the data allow; an MCMC (tick MCMC on the Fit tab) gives its "
        "uncertainty."),
      P("7.2 Example 2 — ttv mode, planet c not transiting", h2),
      P("<b>Data</b>: 60 mid-times of b and 30 RVs; c is seen only through the TTVs of b and the RVs. <b>Tests</b>: "
        "the non-transiting option, cos i, the profiled RV term."),
      P("1. Open " + m("examples_synthetic/example2_ttv_nontransiting/config.json") + ". On the Planets tab, c has "
        "<i>transiting</i> unticked, <i>no transit</i> ticked and cos i (start) = 0.15.<br/>2. Start run as "
        "before (about 7 min)."),
      *FIG("shot_planets_ex2.png", 15.0, "<b>Figure 7.</b> Example 2: planet c is non-transiting; cos i replaces b."),
      *T([["Quantity", "Truth", "Fit (ML)"],
          ["m_b; m_c", "15.0 M⊕; 0.600 M_J", "13.8 M⊕; 0.615 M_J"],
          ["e_b; e_c", "0.050; 0.018", "0.055; 0.018"],
          ["TTV half-amplitude b", "80.4 min", "76.6 min"],
          ["lnP (truth; fit)", "180.56", "206.67"]],
         [4.5, 5.6, 6.7], "<b>Table 8.</b> Example 2: truth and ML result."),
      P("The inclination of c is barely constrained (cos i stays near its start, 0.150; truth 0.113): the TTVs "
        "depend on it only weakly. <b>Why cos i = 0.15?</b> The prefit keeps the geometry fixed at its start. With "
        "a/R* = 14 for c, cos i = 0.05 would give an impact parameter of 0.7, i.e. a transit, and the <i>no "
        "transit</i> option would reject every candidate: the prefit then reports only penalty values of 10⁹. "
        "Choose cos i &gt; R*/a.", note),
      P("7.3 Example 3 — photodynamical mode", h2),
      P("<b>Data</b>: light curves of two 27-day segments (10-min cadence, white noise 0.6 ppt), 30 ground-based "
        "mid-times of c outside the segments, 30 RVs. Planet b has no mid-times: it is seen only in the light "
        "curve, as TOI-3686 b. <b>Tests</b>: photodyn mode, start from a ttv run, transit shapes."),
      P("1. Run example 1 first: this example starts from its " + m("output/start.json") + " (the configuration "
        "points there; both use t_start = 999.0).<br/>2. Open " + m("examples_synthetic/example3_photodyn/config.json") +
        ". The Fit tab shows the prefit greyed out (a start file is set).<br/>3. Optional check: set the start "
        "file to " + m("truth_start.json") + " and press <b>Check: lnP at the start</b>; expected −7048.98, with "
        "segment log-likelihoods near −3550 each (what white noise of 0.6 ppt gives for ~3900 points). Then set "
        "the start file back to " + m("../example1_ttv_both/output/start.json") + ".<br/>4. Start run (about "
        "5 min; no prefit)."),
      *T([["Quantity", "Truth", "Fit (ML)"],
          ["m_b; m_c", "15.0 M⊕; 0.600 M_J", "16.4 M⊕; 0.606 M_J"],
          ["Rp/R* b; c", "0.030; 0.100", "0.0304; 0.1016"],
          ["b_b; b_c", "0.30; 0.20", "0.31; 0.29"],
          ["q1; q2", "0.36; 0.30", "0.11; 0.92"],
          ["lnP (truth; fit)", "−7048.98", "−7011.13"]],
         [4.5, 5.6, 6.7], "<b>Table 9.</b> Example 3: truth and ML result."),
      P("Radius ratios and masses are recovered well. The impact parameter of c and the limb darkening are not: "
        "b, q1, q2 and the stellar density all shape the transit and are correlated, and an ML fit can settle "
        "anywhere along that degeneracy. This is a property of the data, not an error; an MCMC shows the "
        "resulting width. It is a useful reminder to judge such parameters by their posterior, not by the ML point."),
      P("7.4 Example 4 — TOI-3686: reference check and full run", h2),
      P("This example applies the program to real data: the hot Jupiter TOI-3686 c (P = 5.08 d) and its inner "
        "sub-Neptune b (P = 2.54 d) near the 2:1 resonance, using three TESS sectors (18, 58, 85), mid-transit times of "
        "c and RVs from NEID and MAROON-X. The configuration " + m("examples_toi3686/toi3686_photodyn_check.json") +
        " expects the project files two directories up (the detrended TESS light curve, the RV file, the mid-times of "
        "c) and the start file " + m("start_bounds_ml.json") + " (the best ML solution of the earlier analysis with "
        "toi3686_photodynamical_ttvfast_v3). If your directory layout differs, adjust the paths on the Data and "
        "Planets tabs (the GUI shows absolute paths after loading)."),
      P("<b>Step 1: the reference check.</b> Open the configuration, check that the Run tab shows the start file, and "
        "press <b>Check: lnP at the start</b> (one process is enough; about 20 s). The result must equal the "
        "log-posterior of the same parameters in the v3 analysis, term by term: −80467.8. This shows that the general "
        "program and the dedicated TOI-3686 code compute the same model."),
      P("<b>Step 2: the full run.</b> With MCMC ticked on the Fit tab (walkers 0, i.e. 4 × 57 = 228; 3000 steps) press "
        "<b>Start run</b>. The prefit is skipped (a start file is set), the ML fit improves the start to ln p = "
        "−80464.77, and the MCMC follows (roughly 1–2 s per step with 8 processes, so an hour or two). The figures and "
        "numbers below come from the run in " + m("examples_toi3686/output_check/") + " of the author of this manual. "
        "It was made with version 1.0 of the core, which wrote Dutch output; version 1.1 reproduces its ML point "
        "exactly (ln p = −80464.77, term by term), so the figures shown here were redrawn with version 1.1 from the "
        "same parameters, and the posterior values are those of the original run."),
      *FIG("toi_photometry.png", 15.5, "<b>Figure 0.</b> TOI-3686: TESS photometry of the three sectors (grey) with the "
           "model of the ML solution (red: GP plus transits). The blue curve, offset downwards, shows the transits "
           "alone: the deep transits of c and the shallow ones of b (about 0.5 ppt) at their own predicted times."),
      *FIG("toi_ttv.png", 14.5, "<b>Figure 0.</b> TOI-3686: TTVs of the ML solution with respect to the mean ephemeris. "
           "Planet b (top) has no individual mid-times; its TTVs of about ±5 h follow from the photometry. Planet c "
           "(bottom): filled points are the ground-based mid-times in the likelihood, open points the TESS times, "
           "which are left out because their transits are in the light curve."),
      *FIG("toi_rv.png", 14.5, "<b>Figure 0.</b> TOI-3686: RVs after subtracting the instrument offsets and the "
           "activity GP, with the N-body model (dominated by c, K = 61 m/s) and the residuals."),
      *FIG("toi_corner.png", 15.5, "<b>Figure 0.</b> TOI-3686: posterior distributions of the main dynamical parameters "
           "and M* (corner.png of the MCMC run). Note the skewed distribution of b_b and the correlation between "
           "log_q_c and ΔΩ."),
      P("<b>Comparison with the discovery paper.</b> The system was presented by Yee et al. (2026, submitted to AJ; "
        "arXiv:2610.28533) with an independent "
        "photodynamical analysis (another N-body code, Hamiltonian Monte Carlo instead of emcee, and a somewhat larger "
        "data set). Table 17 compares the posteriors."),
      *T([["Quantity", "This run (median, 68%)", "Yee et al. (2026)"],
          ["m_b", "9.6 ± 0.8 M⊕", "10.5 +1.3/−1.2 M⊕"],
          ["m_c", "0.557 +0.038/−0.042 M_J", "0.564 +0.036/−0.040 M_J"],
          ["m_b/M*; m_c/M*", "2.62 × 10<super>−5</super>; 4.82 × 10<super>−4</super>",
           "2.79 × 10<super>−5</super>; 4.76 × 10<super>−4</super>"],
          ["e_b; e_c", "0.1594 ± 0.0008; 0.0015 +0.0019/−0.0008", "0.1595 +0.0013/−0.0016; 0.0012 +0.0005/−0.0011"],
          ["ΔΩ; mutual inclination", "−7.0 +2.1/−2.3°; 7.2° (ML)", "−7.1 +2.7/−2.9°; 7.5 +2.3/−2.8°"],
          ["TTV peak-to-peak b; c", "9.8 h; 39 min (ML)", "10 h; 40 min"],
          ["Mean period ratio P_c/P_b", "2.00275 (ML)", "2.0025"],
          ["M*; R*", "1.100 +0.073/−0.081 M☉; 1.149 ± 0.031 R☉", "1.130 ± 0.075 M☉; 1.130 +0.030/−0.027 R☉"],
          ["ρ* = M*/R*³", "0.72 +0.06/−0.05 ρ☉", "0.78 ρ☉ (from the medians)"],
          ["b_b; b_c", "0.70 +0.11/−0.20; 0.37 +0.05/−0.06", "0.41 +0.18/−0.24; 0.287 +0.066/−0.056"],
          ["Rp/R* b; c", "0.0208 ± 0.0015; 0.103 +0.005/−0.004", "0.0231 ± 0.0015; 0.11575 ± 0.0005 (prior)"],
          ["Dilution D (S18, S58, S85)", "1.28, 1.24, 1.27 (± 0.12)", "1.06, 1.00, 1.05"],
          ["Transit depth D (Rp/R*)² b; c", "5.46 × 10<super>−4</super>; 1.334 × 10<super>−2</super>",
           "5.54 × 10<super>−4</super>; 1.391 × 10<super>−2</super>"],
          ["P_rot of the GP (S18, S58, S85)", "5.4, 5.48, 5.42 d", "5.60, 5.37, 5.55 d"],
          ["Data", "20 ground mid-times of c (to 2024); 44 RVs", "ground mid-times to 2026; 54 RVs"]],
         [4.3, 6.4, 6.1], "<b>Table 0.</b> TOI-3686: this run compared with Yee et al. (2026, arXiv:2610.28533, Table 3 and "
                          "Section 5). Masses scale with M*; the mass ratios m/M* are what the TTVs measure directly."),
      P("<b>What agrees.</b> The dynamical quantities agree within their uncertainties: the mass ratios (c to 1%, b to "
        "6%, i.e. 1σ), the eccentricities (e_b to 0.0001), ΔΩ and the mutual inclination, the TTV amplitudes, and the "
        "rotation periods of the stellar activity, and the mean period ratio (2.0028 against 2.0025). Both analyses "
        "find the same resonant configuration from different "
        "codes, samplers and data sets; Yee et al. show that this configuration is "
        "deep in the 2:1 mean-motion resonance."),
      P("<b>Dilution and radius: a degeneracy, and how to remove it.</b> The largest differences are the dilution "
        "factors (about 1.27 here, against 1.00–1.06) and the radius ratios (about 10% smaller here). They are two sides "
        "of one degeneracy: a transit depth is D·(Rp/R*)², and the light curve measures only that product. The products "
        "agree to 2% (b) and 4% (c). This run uses free dilution without any constraint on Rp/R*, so the data cannot "
        "decide how to split the depth between D and Rp/R*. Yee et al. fix this with a Gaussian prior Rp/R* = 0.1158 ± "
        "0.0005 for c from ground-based photometry, which resolves the bright star from its neighbours. In "
        "photodyn2p the same prior is set on the Planets tab (Rp/R* prior: Gaussian, μ = 0.1158, σ = 0.0005, planet c); "
        "the dilution is then determined, and the radius of b follows. Alternatively choose dilution = fixed if no "
        "contamination is expected."),
      P("<b>Stellar parameters and impact parameters.</b> M* and R* both lie within 1σ of the published values, but "
        "the stellar density is 8% lower, and b_b is higher (0.70 against 0.41) with a skewed posterior. The transit "
        "durations constrain combinations of ρ*, b and limb darkening, and with free dilution these are less well "
        "pinned; the prior on Rp/R* of c is expected to reduce this as well. b_b is the least constrained parameter "
        "in both analyses."),
      P("<b>Convergence.</b> The chain is not converged by the strict criterion: τ_max ≈ 307 steps for a chain of 3000, "
        "so N/τ ≈ 10, and the autocorrelation estimates are similar for all 57 parameters, a sign that τ is still "
        "growing with the chain length. The posterior values above are therefore preliminary: medians are usually "
        "already reliable at this stage, the widths less so. Extend the chain (start the same run again; the steps are "
        "added) and check it with tools/block_check.py (Section 8, step 7) before using the numbers."),
      P("<b>Different data.</b> The published analysis includes ground-based mid-times up to 2026 and ten more RVs. "
        "This affects mainly the mass of c and the RV activity term (the RV GP amplitude is 12 +9/−7 m/s here, against "
        "31 m/s in the paper)."),
]

S += [PageBreak(), P("8. A new object step by step", h1),
      P("This chapter is a complete recipe for analysing a new two-planet system, from the raw data to posterior "
        "distributions. It assumes nothing beyond Sections 1–7. As an illustration, take a star ‘TOI-XXXX’ with a "
        "transiting planet b with clear transits and a second planet c that is either weak in the photometry or does "
        "not transit at all."),
      P("Step 1 — Collect and prepare the data", h2),
      P("Make a new project directory with a subdirectory for the data. You need, in the formats of Section 9:"),
      P("• <b>Mid-transit times</b> of every planet whose individual transits you can measure: one file per planet, "
        "one line per transit (epoch, time, error, optionally systematic error and facility). Obtain them by fitting "
        "each transit separately with a transit model (any transit-fitting code, or AstroImageJ for ground-based "
        "data), with a common shape and a free mid-time per transit. Number the epochs from any reference transit; "
        "the program checks that epochs and period agree. Give each telescope a one-word facility name.<br/>"
        "• <b>Radial velocities</b>, if available: time, RV, error, instrument.<br/>"
        "• <b>Light curves</b> for the photodynamical mode: a CSV with time, normalised flux, error and segment "
        "number (one segment per TESS sector or per observing season). If you detrended the data, keep the trend in "
        "a fifth column and use trend = multiply, so that the GP models the variability again together with the "
        "transits.<br/>"
        "• For a planet too weak for individual mid-times: a <b>residual light curve</b> (activity and the other "
        "planet removed) for the prefit template term, and/or <b>sector times</b> measured per segment (for "
        "TOI-3686 with make_b_times.py of the TOI-3686 project; Section 5.2, term 4).", ParagraphStyle("bul", parent=body, leftIndent=8)),
      P("Step 2 — Star and starting values", h2),
      P("Take M* and R* with their uncertainties from a stellar characterisation (spectroscopy plus isochrones, or a "
        "catalogue). For every planet with mid-times, fit a straight line t = T0 + nP to its mid-times: P is the "
        "mean period and T0 a transit time (the prefit prints the χ² of this fit; a value much larger than the number "
        "of mid-times shows the TTVs). For a planet without mid-times, take P from a periodogram (e.g. the period at "
        "which its transits or its TTV-induced signal appear). Choose mass bounds that are physically plausible, "
        "about a factor 10–50 wide, and Rp/R* from the transit depth (depth ≈ (Rp/R*)²)."),
      P("Step 3 — Create the configuration in the GUI", h2),
      P("Start the GUI, choose <b>File → New</b> and immediately <b>File → Save as…</b> into the project directory "
        "(e.g. " + m("toixxxx_ttv.json") + "), so that relative paths are relative to it. Then fill in: "
        "<b>Object & star</b>: name, mode <i>ttv</i>, output directory (e.g. " + m("out_ttv") + "), M* and R*, and "
        "an explicit t_start (1 d before your first data point, rounded) so that later runs share it. "
        "<b>Planets</b>: name, transiting or not, P (the mean period), P search width 0.003, mid-times file, mass "
        "unit and bounds, b (or cos i &gt; R*/a for a non-transiting planet, Section 5.2), and the sector times or "
        "template option for a weak planet. <b>Data</b>: error floor (1–2 min for ground-based timings), the RV file "
        "(GP only if the RVs show activity), and, for a weak planet, the residual photometry. <b>Fit</b>: prefit on, "
        "popsize 15, 200–400 generations, strategy best1bin, solutions to polish 5–10; MCMC off for now."),
      P("Step 4 — Check that everything is read correctly", h2),
      P("On the Run tab press <b>Check: lnP at the start</b>. The log lists what was read: the number of mid-times "
        "per planet (and how many are used), the RVs per instrument, the segments, t_start and t_end. Compare these "
        "counts with your files. An error message names the missing or unreadable file. The value of ln p itself "
        "is not meaningful at this stage (the starting values are rough)."),
      P("Step 5 — Prefit and maximum likelihood in ttv mode", h2),
      P("Press <b>Start run</b>. Judge the prefit as in Section 5.5: the polished totals should be close to the "
        "number of data points, the mid-time rms close to the errors, and several candidates should reach the same "
        "total. Then check the ML result with the checklist of Section 6.4 and look at " + m("ttv_oc.png") + " (the "
        "model must follow the O−C of both planets) and " + m("rv.png") + ". If the candidates disagree or the totals "
        "are poor: repeat with strategy rand1bin and another seed, each with its own checkpoint name, and compare; "
        "widen bounds that a solution touches; inject good candidates from earlier runs. Keep the best "
        + m("start.json") + "."),
      P("Step 6 — Photodynamical fit (if you have light curves)", h2),
      P("Choose <b>File → Save as…</b> " + m("toixxxx_photodyn.json") + " and change: mode <i>photodyn</i>; a new "
        "output directory (" + m("out_photodyn") + "); the light curve on the Data tab (GP per segment for an active "
        "star, P_rot bounds around the rotation period, dilution free only if contamination is possible and an "
        "Rp/R* prior is available); on the Run tab the start file " + m("out_ttv/start.json") + ". Keep the same "
        "t_start. The prefit box turns grey (a start file is set). First press <b>Check: lnP at the start</b>, then "
        "<b>Start run</b> (minutes to an hour, depending on the number of photometric points). Check "
        + m("photometry.png") + ": the transits of every planet must sit on the model; check that Rp/R* is not at a "
        "bound and that the GP parameters are sensible (Section 6.2)."),
      P("Step 7 — MCMC", h2),
      P("Tick MCMC on the Fit tab: walkers 0 (= 4 × the number of parameters), steps 3000, Laplace start on, "
        "backend chain.h5. Long chains are best run from the command line in the background (Section 12), e.g. "
        + m("nohup python photodyn2p.py toixxxx_photodyn.json --nproc 8 --mcmc &gt; mcmc.log 2&gt;&amp;1 &amp;") +
        ". Running the same command again extends the chain (steps are then additional). Judge convergence with "
        + m("tools/block_check.py") + " on a copy of the chain: the block means of the masses, M*, R* and the "
        "angles must stop drifting, their spreads must be stable, and the autocorrelation time τ must stop growing "
        "with the chain length. emcee recommends at least 50 τ after the burn-in; a practical minimum is an effective "
        "sample size of several hundred per parameter (number of walkers × (N − burn)/τ)."),
      P("Step 8 — Report and check", h2),
      P("Report the posterior medians and 68% intervals from " + m("results.json") + " and " + m("summary.txt") +
        ": masses (and the mass ratios, which the TTVs measure directly), radii, eccentricities, the mean periods, "
        "the TTV amplitudes, ΔΩ and the mutual inclination. Check that the masses agree with the RV-only estimates, "
        "that the system is far from the Hill limit, and that no parameter of interest sits at a bound. Keep "
        + m("config_used.json") + " with the results: it documents every setting of the run."),
      *T([["Step", "Typical time (8 processes)", "Output to keep"],
          ["1–4 data, configuration, check", "hours (data preparation); check: seconds", "data files, configuration"],
          ["5 prefit + ML (ttv)", "5–30 min", "out_ttv/start.json, prefit_results.json"],
          ["6 photodynamical ML", "10 min – 1 h", "out_photodyn/start.json, figures"],
          ["7 MCMC", "hours to a night per few thousand steps", "chain.h5, results.json"],
          ["8 report", "—", "summary.txt, config_used.json"]],
         [4.8, 6.0, 6.0], "<b>Table 0.</b> Overview of the scenario."),
]

# ============================================================================ 6
S += [P("9. Input file formats", h1),
      *T([["File", "Format", "Notes"],
          ["Mid-times", "epoch  time  σ_stat[d]  [σ_sys[d]]  [facility]", "Errors in days, added in quadrature; "
           "facility one word (spaces → underscores); duplicate epochs allowed; time in BTJD or BJD."],
          ["Sector times", "sector  T_ref  σ_T[d]  P_loc[d]  σ_P[d]  ρ  [S/N  note]", "b_times.dat format."],
          ["RVs", "time  rv[m/s]  err[m/s]  instrument", "The weighted mean per instrument is subtracted; offsets "
           "are fitted."],
          ["Photometry", "time, flux, error, segment[, trend]", "Comma- or space-separated; header allowed; each "
           "segment is normalised by its median."],
          ["Residual photometry", "time, flux, error, segment[, flare flag]", "For the prefit template term."],
          ["Start file", "JSON: t_start and parameter values", "start.json, prefit_start.json, or v3 start files "
           "(log_mp_*, dOm_c, T0_* are converted)."]],
         [3.0, 5.8, 8.0], "<b>Table 10.</b> Input formats."),
      C("""# epoch  BTJD  sigma_stat[d]  sigma_sys[d]  facility
    1  1003.248462  0.002778  0.000000  Ground
   17  1051.335195  0.002778  0.000000  Ground""")]

# ============================================================================ 7
S += [P("10. Output files", h1),
      *T([["File", "Content"],
          ["config_used.json", "The configuration as the core used it (with defaults filled in)."],
          ["prefit_results.json, prefit_start.json", "Ranked polished prefit solutions; the best as a start file."],
          ["prefit_checkpoint.npz", "Population of the prefit (resumed by the next run)."],
          ["start.json", "ML parameters as a start file (for a photodyn run or an MCMC)."],
          ["results.json", "lnP, ML parameters, derived quantities, posterior and MCMC diagnostics."],
          ["summary.txt", "Readable summary: star, per planet mass, osculating and mean ephemeris, TTV amplitude, "
           "e, ω, i, a/R*, K, rms of the mid-times; ΔΩ, mutual inclination, period ratio."],
          ["ttv_oc.png, rv.png, photometry.png", "O−C of both planets against the mean ephemeris; RVs; light curves "
           "(photodyn mode)."],
          ["chain.h5 (+ .names.json), chain.npy, corner.png", "MCMC back-end (resumable), thinned samples, corner plot."]],
         [5.2, 11.6], "<b>Table 11.</b> Files in the output directory.")]

# ============================================================================ 8
S += [P("11. Troubleshooting", h1),
      *T([["Symptom", "Cause and remedy"],
          ["Prefit: every value is 1000000000.0", "Every candidate is rejected. Most common cause: a non-transiting "
           "planet whose starting cos i makes it transit (cos i &lt; R*/a) while <i>no transit</i> is ticked. "
           "Increase cos i (start). Also check that the period bounds contain the true period."],
          ["Prefit: best value stays high for hundreds of generations", "Search space too wide. Use the observed "
           "mean periods with P search width ~0.003 and realistic mass bounds. Judge the prefit after polishing: "
           "the generations alone may still be in the thousands when polishing reaches the solution."],
          ["Prefit finishes immediately without generations", "The checkpoint already reached max. generations. "
           "Use a new checkpoint name or raise max. generations."],
          ["The prefit box is grey", "A start file is set on the Run tab; the core skips the prefit. Clear the "
           "start file to run the prefit."],
          ["Warning: t_start of the start file differs", "Osculating elements belong to their own t_start. Set "
           "t_start explicitly and equal in both configurations."],
          ["'Configuration incomplete' when starting", "The message lists what is missing (planet names, mid-times "
           "in ttv mode, photometry file in photodyn mode, RV file)."],
          ["ML step 2 ends with ABNORMAL", "Common at the end of L-BFGS-B on a flat optimum; check lnP and the "
           "residuals. If in doubt, run again from start.json."],
          ["Parameters at a bound (b, limb darkening, GP)", "Often a degeneracy (Section 7.3). Look at the MCMC "
           "posterior before interpreting the ML value."],
          ["File dialog (…) opens in the wrong directory or cannot be navigated", "Fixed in GUI version 1.1: "
           "dialogs open in the directory of the configuration and use Qt's own dialog, which works under WSL also "
           "on /mnt drives. You can always type a path instead; relative paths are relative to the configuration."],
          ["Run from a relative path fails (file not found)", "Fixed in GUI version 1.1: configurations are "
           "kept with absolute paths. With an older GUI, open the configuration with File → Open."]],
         [5.0, 11.8], "<b>Table 12.</b> Common problems.")]

# ============================================================================ 9
S += [P("12. Running without the GUI", h1),
      P("Every action of the GUI is a command of the core; the first line of the Run log shows it. Useful for long "
        "runs in the background:"),
      C("""python photodyn2p.py config.json --nproc 8                  # prefit (if no start file) + ML + figures
python photodyn2p.py config.json --nproc 8 --prefit-only    # stop after the prefit
python photodyn2p.py config.json --start-json s.json --eval-only   # lnP at the start
python photodyn2p.py config.json --nproc 8 --mcmc --steps 3000     # also run/extend the MCMC
nohup python photodyn2p.py config.json --nproc 8 > run.log 2>&1 &  # in the background"""),
      P("Other options: --outdir, --mode, --no-search, --no-mcmc, --prefit-eval START.json (prefit objective at a "
        "start file).")]

S += [P("References", h1)] + [P(r, ParagraphStyle("ref", parent=body, fontSize=8.8, leading=12, leftIndent=12,
                                                    firstLineIndent=-12, alignment=0)) for r in (
    "Deck K. M., Agol E., Holman M. J., Nesvorný D. 2014, ApJ, 787, 132 — TTVFast.",
    "Foreman-Mackey D., Hogg D. W., Lang D., Goodman J. 2013, PASP, 125, 306 — emcee.",
    "Foreman-Mackey D., Agol E., Ambikasaran S., Angus R. 2017, AJ, 154, 220 — celerite (celerite2 implements "
    "the RotationTerm used here).",
    "Gladman B. 1993, Icarus, 106, 247 — Hill stability of two planets.",
    "Kipping D. M. 2013, MNRAS, 435, 2152 — the (q1, q2) limb-darkening parameterisation.",
    "Kreidberg L. 2015, PASP, 127, 1161 — batman.",
    "Yee S. W., Dziire T., Collins K. A., et al. 2026, ‘TOI-3686: A Hot Jupiter and Sub-Neptune In A 2:1 "
    "Mean-Motion Resonance’, submitted to AJ, arXiv:2610.28533 (version 1, 20 October 2026).",
    "Storn R., Price K. 1997, J. Global Optim., 11, 341 — differential evolution.")]


doc = Doc(OUT)
doc.multiBuild(S)
print("->", OUT)
