#!/usr/bin/env python3
"""Build ../paper_computing/ (flat folder, Springer 'smallextended' one-column layout for the journal Computing)
from main.tex, tables/ and figures/.  Run from paper/ after make_tables.py, make_figures.py, make_sweep.py,
make_protection_extra.py and pilot/telemetry_summary.py."""
import os, re, shutil
import numpy as np, pandas as pd

OUT = os.path.join("..", "paper_computing")
shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
s = open("main.tex", encoding="utf-8").read()

def rep(old, new, count=1):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, count)

# ------------------------------------------------------------------ preamble and front matter
pk = s[s.index(r"\usepackage[utf8]"):s.index(r"\journal{")]
pk = pk.replace("\\usepackage[hidelinks]{hyperref}\n", "")
pre = r"""\documentclass[smallextended]{svjour3}
\smartqed
""" + pk + "\\setlength{\\tabcolsep}{3pt}\n\\emergencystretch=3em\n"
abstract = re.search(r"\\begin\{abstract\}\n(.*?)\\end\{abstract\}", s, re.S).group(1).strip()
front = r"""\begin{document}
\title{What Replication Modes Cost and Protect: A Measurement Study of Containerised PostgreSQL and Its Implications for Adaptive Mode Selection}
\titlerunning{What Replication Modes Cost and Protect}
\author{Imane Jerrari \and Ismail Assayad}
\authorrunning{I. Jerrari, I. Assayad}
\institute{I. Jerrari (corresponding author) \at Laboratory of Information Systems (LIS), Faculty of Sciences Ain Chock \& ENSEM, Hassan II University of Casablanca, Casablanca, Morocco \\ \email{imane.jerrari-etu@etu.univh2c.ma} \and
I. Assayad \at Laboratory of Information Systems (LIS), Faculty of Sciences Ain Chock \& ENSEM, Hassan II University of Casablanca, Casablanca, Morocco \\ \email{i.assayad@ensem.ac.ma}}
\date{Received: date / Accepted: date}
\maketitle
\begin{abstract}
""" + abstract + r"""
\end{abstract}
\keywords{replication modes \and PostgreSQL \and Kubernetes \and high availability \and self-adaptive systems \and measurement study}
"""
body = s[s.index(r"\section{Introduction}"):]
s = pre + front + "\n" + body

# ------------------------------------------------------------------ method: AI documentation (required by the journal in the Methods)
rep(r"\section{Method}\label{sec:method}",
    r"""\section{Method}\label{sec:method}
\paragraph{Use of an AI assistant.} An AI assistant (Claude, Anthropic) was used to help write the measurement and analysis scripts, to help analyse the results and to draft and edit parts of the text. The authors ran all experiments on their own testbed, reviewed the scripts and the text, and take full responsibility for the content of this article. The scripts are part of the replication package (see Statements and Declarations).""")

# ------------------------------------------------------------------ declarations
i = s.index(r"\section*{Availability of data and code}"); j = s.index(r"\bibliographystyle{elsarticle-num}")
decl = r"""\section*{Statements and Declarations}
\paragraph{Funding} The authors did not receive support from any organization for the submitted work.
\paragraph{Competing interests} The authors have no relevant financial or non-financial interests to disclose.
\paragraph{Author contributions} Both authors contributed to the study conception. Imane Jerrari ran all experiments, analysed and checked the results and prepared the manuscript with the help of an AI assistant (see Method). Ismail Assayad supervised the work and reviewed the manuscript. Both authors approved the final version.
\paragraph{Data availability} The measurements generated and analysed in this study are available at \url{https://github.com/imanejerrari-etu-bit/iaha-replication-modes} (data under CC BY 4.0).
\paragraph{Code availability} The scripts used to run the experiments and the analysis code are available in the same repository (MIT licence).
\paragraph{Use of AI tools} An AI assistant (Claude, Anthropic) was used to help write the measurement and analysis scripts, to help analyse the results and to draft and edit parts of the text, as described in the Method section. The authors ran all experiments, reviewed the scripts and the text, and take full responsibility for the manuscript's content. No AI tool is listed as an author.

"""
s = s[:i] + decl + s[j:]
rep(r"\bibliographystyle{elsarticle-num}", r"\bibliographystyle{spmpsci}")
rep(r"(see Availability of data and code)", r"(see Statements and Declarations)")

# ------------------------------------------------------------------ tables: flat inputs, compact generators
for tab in ["grid", "telemetry", "telemetry_text"]:
    shutil.copy(os.path.join("tables", tab + ".tex"), os.path.join(OUT, tab + ".tex"))
tel = open(os.path.join(OUT, "telemetry.tex"), encoding="utf-8").read()
tel = tel.replace("\\resizebox{\\textwidth}{!}{\\begin{tabular}", "\\begin{tabular}").replace("\\end{tabular}}", "\\end{tabular}")
tel = tel.replace("\\centering\\small", "\\centering\\footnotesize")
tel = tel.replace("CPU of primary, \\% of limit [range over delays]", "CPU, \\% of limit (range)").replace("Memory, \\% of limit", "Memory, \\%").replace("Active connections", "Connections")
tel = tel.replace("[", "(").replace("]", ")") if False else tel
open(os.path.join(OUT, "telemetry.tex"), "w", encoding="utf-8").write(tel)
s = s.replace("tables/", "").replace("figures/", "")
# figures regenerated at the column width (122 mm) with 7 pt text, so that their fonts match the running text
import matplotlib
matplotlib.use("Agg")
def run_patched(script, subs):
    src = "import os\n" + open(script, encoding="utf-8").read()
    for a, b in subs:
        assert a in src, (script, a)
        src = src.replace(a, b)
    exec(compile(src, script, "exec"), {"__name__": "__main__"})
run_patched("make_figures.py", [("figsize=(7.2, 4.2)", "figsize=(4.8, 3.9)"), ("figsize=(7.0, 2.7)", "figsize=(4.8, 3.0)"),
    ('"font.size": 8', '"font.size": 7'), ("figures/fig_grid.pdf", "../paper_computing/fig_grid.pdf"),
    ("figures/fig_loss.pdf", "../paper_computing/fig_loss.pdf"), ("figures/fig_replay.pdf", "../paper_computing/fig_replay.pdf"),
    ('[o.replace("fixed ", "fixed\\n") for o in order]', '[{"fixed PERFORMANCE": "fixed\\nperf.", "fixed CONSISTENCY": "fixed\\ncons.", "fixed AVAILABILITY": "fixed\\navail.", "fixed ECONOMIC": "fixed\\necon."}.get(o, o) for o in order]'),
    ('ax[1][2].text(10, 103, "bound 100 ms", ha="right"', 'ax[1][2].text(0.2, 103, "bound 100 ms", ha="left"')])
run_patched("make_sweep.py", [("figsize=(7.2, 2.9)", "figsize=(4.8, 3.1)"), ('"font.size": 8', '"font.size": 7'),
    ("figures/fig_sweep.pdf", "../paper_computing/fig_sweep.pdf"), ('open("tables/sweep.tex", "w")', 'open(os.devnull, "w")'),
    ("ncol=5, fontsize=6.5", "ncol=5, fontsize=5.8"), ("(0.5, -0.07)", "(0.5, -0.10)")])
shutil.copy("refs.bib", os.path.join(OUT, "refs.bib"))

def write(name, text):
    open(os.path.join(OUT, name), "w", encoding="utf-8").write(text)

# sweep: split into loss table and fit table (parse the generated rows)
rows = [l for l in open("tables/sweep.tex", encoding="utf-8").read().splitlines() if re.match(r"^\d+ &", l)]
loss = "\\begin{tabular}{rccc}\n\\toprule\nClients & 0\\,ms & 5\\,ms & 10\\,ms \\\\\n\\midrule\n"
fit = "\\begin{tabular}{rccc}\n\\toprule\nClients & $k$ (95\\% CI) & $L_0$ (ms) & CPU (\\%) \\\\\n\\midrule\n"
for r in rows:
    c = [x.strip().rstrip("\\").strip() for x in r.split("&")]
    cc = lambda t: t.replace("[", "(").replace("]", ")").replace(", ", "--")
    loss += f"{c[0]} & {cc(c[1])} & {cc(c[2])} & {cc(c[3])} \\\\\n"
    fit += f"{c[0]} & {cc(c[4])} & {c[5]} & {c[6]} \\\\\n"
write("sweep_loss.tex", loss + "\\bottomrule\n\\end{tabular}\n"); write("sweep_fit.tex", fit + "\\bottomrule\n\\end{tabular}\n")

# rate: short headers
r = pd.read_csv("data_summary/rpo_rate.csv"); r["exp"] = r.rate_tps * r.isolate_s
t = "\\begin{tabular}{rrrrrr}\n\\toprule\nRate (tps) & Runs & Lost, mean & Lost, min--max & Rate$\\times$2\\,s & Ratio \\\\\n\\midrule\n"
for rate, g in r.groupby("rate_tps"):
    t += f"{rate:.0f} & {len(g)} & {g.lost.mean():.0f} & {g.lost.min():.0f}--{g.lost.max():.0f} & {g.exp.iloc[0]:.0f} & {g.lost.mean()/g.exp.iloc[0]:.2f} \\\\\n"
write("rate.tex", t + "\\bottomrule\n\\end{tabular}\n")

# rpo + crash merged
d = pd.read_csv("data_summary/rpo_results.csv"); sm = pd.read_csv("data_summary/rpo_summary.csv")
order_lvl = {"ASYNC": 0, "SYNC_1": 1, "SYNC_2": 2}
keys = sorted(d.groupby(["scenario", "level", "isolate_s"]).groups, key=lambda k: (k[0] != "CRASH", k[2], order_lvl[k[1]]))
t = ("\\begin{tabular}{llcccc}\n\\toprule\nScenario & Level & Runs (loss) & Lost, mean (CI) & Unack.\\ (runs) & Resume, s \\\\\n\\midrule\n")
for sc, lvl, iso in keys:
    g = d[(d.scenario == sc) & (d.level == lvl) & (d.isolate_s == iso)]
    name = "crash only" if sc == "CRASH" else f"isol.\\ {iso:g}\\,s"
    if sc == "ISOLATE" and lvl == "ASYNC":
        x = sm[(sm.level == lvl) & (sm.isolate_s == iso)].iloc[0]
        lost = f"{x.mean_lost:.0f} ({x.ci_lo:.0f}--{x.ci_hi:.0f})"
    else:
        lost = f"{g.lost.mean():.0f}"
    res = f"{g.t_write_s.median():.1f} ({g.t_write_s.min():.1f}--{g.t_write_s.max():.1f})"
    t += f"{name} & {lvl.replace('_', '-').lower()} & {len(g)} ({(g.lost > 0).sum()}) & {lost} & {int(g.extra.sum())} ({int((g.extra > 0).sum())}) & {res} \\\\\n"
write("rpo.tex", t + "\\bottomrule\n\\end{tabular}\n")

# replay: compact intervals
p = pd.read_csv("data_summary/replay_summary.csv")
order = ["fixed PERFORMANCE", "fixed CONSISTENCY", "fixed AVAILABILITY", "fixed ECONOMIC", "RULES", "MODEL", "ORACLE"]
names = {"fixed PERFORMANCE": "Fixed \\textsc{perf.}", "fixed CONSISTENCY": "Fixed \\textsc{cons.}", "fixed AVAILABILITY": "Fixed \\textsc{avail.}",
         "fixed ECONOMIC": "Fixed \\textsc{econ.}", "RULES": "Rule cascade", "MODEL": "Random forest", "ORACLE": "Oracle"}
t = ("\\begin{tabular}{lccccc}\n\\toprule\nController & \\multicolumn{3}{c}{Steps in violation, \\% (95\\% CI)} & Cost & Switches \\\\\n\\cmidrule(lr){2-4}\n"
     " & \\textsc{balanced} & \\textsc{default} & \\textsc{strict} & & \\\\\n\\midrule\n")
for c in order:
    cells = []
    for pol in ["BALANCED", "DEFAULT", "STRICT"]:
        x = p[(p.policy == pol) & (p.controller == c)].iloc[0]
        cells.append(f"{x.viol:.1f} ({x.lo:.1f}--{x.hi:.1f})")
    b = p[(p.policy == "BALANCED") & (p.controller == c)].iloc[0]
    t += " & ".join([names[c]] + cells + [f"{b.cost:.2f}", f"{b.trans:.1f}"]) + " \\\\\n"
    if c == "fixed ECONOMIC":
        t += "\\midrule\n"
write("replay.tex", t + "\\bottomrule\n\\end{tabular}\n")

# ------------------------------------------------------------------ table environments in the text
s = s.replace("\\centering\\small", "\\centering\\footnotesize")
s = re.sub(r"\\resizebox\{[^}]*\}\{!\}\{\\input\{([^}]*)\}\}", r"\\input{\1}", s)
# crash table removed (merged into the isolation table); references redirected
s = re.sub(r"\\begin\{table\}\[t\]\n\\centering\\footnotesize\n\\input\{crash\.tex\}\n\\caption\{.*?\}\\label\{tab:crash\}\n\\end\{table\}\n", "", s, flags=re.S)
s = s.replace(r"Table~\ref{tab:crash}", r"Table~\ref{tab:rpo}")
rep(r"""\caption{Isolation-then-crash results at 5\,ms delay. Lost = acknowledged transactions absent from the new primary. Writes resume = median [min--max] seconds from the crash to the first successful write; promotion = median seconds to a new primary.}\label{tab:rpo}""",
    r"""\caption{All protection runs at 5\,ms delay (isolation then crash, and crash only). Runs (loss) = runs, and runs with at least one lost acknowledged transaction; Lost = acknowledged transactions absent from the new primary; Unack.\ rows = rows present on the new primary but not acknowledged to a client (sum over runs, with the number of runs concerned); Resume = median (min--max) seconds from the stop of the primary to the first successful write.}\label{tab:rpo}""")
# sweep table -> two tables
a = s.index("\\begin{table}[t]\n\\centering\\footnotesize\n\\input{sweep.tex}")
b = s.index("\\end{table}", a) + len("\\end{table}")
s = s[:a] + r"""\begin{table}[t]
\centering\footnotesize
\input{sweep_loss.tex}
\caption{Client-count sweep (write workload, five repetitions): throughput loss (\%) of \cons\ relative to \perf\ at each one-way delay, with percentile bootstrap 95\% intervals over repetitions.}\label{tab:sweep}
\end{table}
\begin{table}[t]
\centering\footnotesize
\input{sweep_fit.tex}
\caption{Client-count sweep: slope $k$ and intercept $L_0$ of the fit $L=L_0+k\cdot\mathrm{RTT}$ for \cons, and mean CPU of the primary under \perf.}\label{tab:sweepfit}
\end{table}""" + s[b:]
s = s.replace(r"Table~\ref{tab:sweep} and Figure~\ref{fig:sweep} give the sweep.", r"Tables~\ref{tab:sweep} and~\ref{tab:sweepfit} and Figure~\ref{fig:sweep} give the sweep.")
# remaining inline tables: compact the pilot table
s = s.replace("\\resizebox{\\textwidth}{!}{\\begin{tabular}{rcccc}", "\\begin{tabular}{rcccc}").replace("\\end{tabular}}\n\\caption{Pilot", "\\end{tabular}\n\\caption{Pilot")
s = s.replace("\\resizebox{\\textwidth}{!}{\\begin{tabular}{llll}", "\\begin{tabular}{llll}").replace("\\end{tabular}}\n\\caption{Labels", "\\end{tabular}\n\\caption{Labels")
s = s.replace("\\resizebox{\\textwidth}{!}{\\begin{tabular}", "\\begin{tabular}")
# modes table: short headers
s = s.replace("Mode & Instances & Sync.\\ replicas (min/max) & Reads served by & Durable & HA & Cost", "Mode & Inst. & Sync.\\ (min/max) & Reads by & Dur. & HA & Cost")
# pilot table: restructured, compact
a = s.index("\\begin{tabular}{rcccc}"); b = s.index("\\end{tabular}", a) + len("\\end{tabular}")
s = s[:a] + r"""\begin{tabular}{lcc}
\toprule
One-way delay & 0\,ms & 5\,ms \\
\midrule
\perf, tps (CV, \%) & 533 (1.4) & 540 (1.9) \\
\cons, tps (CV, \%) & 424 (6.5) & 265 (2.8) \\
Change in tps (\%) & $-20.5$ ($-24.2$, $-17.5$) & $-50.9$ ($-52.1$, $-49.7$) \\
Change in p95 (\%) & $+6.8$ ($+2.6$, $+12.3$) & $+65.3$ ($+62.5$, $+68.8$) \\
\bottomrule
\end{tabular}""" + s[b:]
s = s.replace("The change had the same sign in all eight blocks at both delays.}", "Change = paired \\cons-versus-\\perf\\ change with bootstrap 95\\% intervals; it had the same sign in all eight blocks at both delays.}") if False else s
# labels table: one label per workload (identical at the three delays)
a = s.index("\\begin{tabular}{llll}"); b = s.index("\\end{tabular}", a) + len("\\end{tabular}")
s = s[:a] + r"""\begin{tabular}{llcc}
\toprule
Workload & Requirements & Label (same at 0, 5, 10\,ms) & Confidence, \% (0, 5, 10\,ms) \\
\midrule
\textsc{low} & none & \econ & 100, 100, 100 \\
\textsc{readmostly} & HA & \perf & 100, 100, 100 \\
\textsc{write} & durable, HA & \cons & 96, 99, 100 \\
\bottomrule
\end{tabular}""" + s[b:]
s = s.replace(r"\includegraphics[width=0.55\textwidth]{fig_loss.pdf}", r"\includegraphics[width=0.8\textwidth]{fig_loss.pdf}")
write("main.tex", s)

# ------------------------------------------------------------------ bibliography inlined (the submission system has no spmpsci.bst)
import subprocess, tempfile
def inline_bibliography(text):
    tmp = tempfile.mkdtemp()
    for f in os.listdir(OUT):
        shutil.copy(os.path.join(OUT, f), tmp)
    emu = (r"\documentclass[10pt,a4paper]{article}" "\n" r"\newcommand{\smartqed}{}\newcommand{\institute}[1]{}\newcommand{\at}{}\newcommand{\email}[1]{}"
           r"\newcommand{\authorrunning}[1]{}\newcommand{\titlerunning}[1]{}\renewcommand{\date}[1]{}\newcommand{\keywords}[1]{}" "\n")
    t = text.replace(r"\documentclass[smallextended]{svjour3}" "\n" r"\smartqed" "\n", emu, 1)
    t = t.replace(r"\bibliographystyle{spmpsci}", r"\bibliographystyle{unsrt}")
    open(os.path.join(tmp, "stub.tex"), "w", encoding="utf-8").write(t)
    for cmd in (["pdflatex", "-interaction=nonstopmode", "stub.tex"], ["bibtex", "stub"]):
        subprocess.run(cmd, cwd=tmp, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    bbl = open(os.path.join(tmp, "stub.bbl"), encoding="utf-8").read()
    assert r"\begin{thebibliography}" in bbl and bbl.count(r"\bibitem") >= 20, "bibliography not generated"
    return text.replace(r"\bibliographystyle{spmpsci}" "\n" r"\bibliography{refs}", bbl.strip())
s = open(os.path.join(OUT, "main.tex"), encoding="utf-8").read()
write("main.tex", inline_bibliography(s))
print("written", OUT, "| leftover resizebox:", s.count("resizebox"), "| tables/ refs:", s.count("tables/"))
