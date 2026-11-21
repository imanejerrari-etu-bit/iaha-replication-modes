**To the Editors of the Journal of Systems and Software**

Dear Editors,

We submit the manuscript **"What Replication Modes Cost and Protect: A Measurement Study of Containerised PostgreSQL and Its Implications for Adaptive Mode Selection"** for consideration as a research article.

**What the paper does.** Controllers that select a replication mode for a containerised database usually rely on labels written by hand. We replace them with measurements on a PostgreSQL cluster managed by the CloudNativePG operator: (i) the throughput and latency cost of four replication modes over three workloads, three inter-node delays and, in a separate sweep, 2, 8 and 32 concurrent clients; (ii) the protection each mode gives, measured as the number of acknowledged transactions lost when the primary is isolated from the network and then crashes, for isolation durations of 1, 2 and 5 s, at limited write rates, and for a crash without isolation; and (iii) a replay of controllers on the measured outcomes under three declared requirement policies.

**Main findings.** Asynchronous replication lost about 2,000 acknowledged transactions per second of isolation in all 12 runs, roughly in proportion to the write rate, whereas synchronous replication lost none in 18 runs and a crash without isolation lost none in 10 runs. Synchronous replication costs about one network round trip of latency per commit when the primary is not CPU-saturated, and more under saturation, so its throughput price depends on the load (81%, 68% and 45% at 10 ms with 2, 8 and 32 clients). No fixed mode met the declared requirements in all contexts, a static rule cascade violated them in 13--47% of replayed steps, and one context admitted no feasible durable mode.

**Fit with the journal.** The journal publishes papers on software engineering and related systems issues and asks for validation through experiments or systematic comparisons. Our manuscript is an empirical study of a deployment-time decision in the operation of containerised database systems and of the evidence that self-adaptive controllers need for it. It reports repeated measurements, sensitivity analyses and explicit threats to validity, and it is released with a replication package. [Authors: check this paragraph against the current aims and scope of the journal before submission.]

**Related publications by the authors.** Two earlier papers by the same authors are accepted: *Jerrari and Assayad, Journal of Intelligent & Fuzzy Systems, 2026*, which proposed the framework and the four replication modes, and *Jerrari and Assayad, International Journal of Data Science and Analytics, 2026*, which tested classifier consistency across database engines on synthetic data. The present manuscript uses no synthetic labels and no data from those papers; all measurements, analyses and results reported here are new, and no text, figure or table is reused. Both papers are cited and the differences are stated in the Introduction.

**Limitations, stated in the manuscript.** All experiments ran on one laptop with emulated network delay, three synthetic workloads and nine contexts; requirements are declared rather than measured; transition costs and a closed-loop controller were not evaluated; some results (the excess of the measured loss over write rate times isolation time, and a fixed 103 s recovery delay after a crash without isolation) are reported without explanation.

**Data and code.** Scripts, raw measurements and analysis code are available at https://github.com/imanejerrari-etu-bit/iaha-replication-modes, with an archived release on Zenodo [Authors: add the DOI after the release], under open licences (MIT for code, CC BY 4.0 for data).

**Declarations.** The manuscript has not been published and is not under consideration elsewhere. All authors have approved the submission. The authors declare no competing interests and received no funding. The use of an AI assistant for scripts, analysis and text drafting and editing is declared in the manuscript.

**Suggested reviewers (optional).** [Authors: propose reviewers with relevant expertise and no conflict of interest, or delete this paragraph.]

Sincerely,

Imane Jerrari (corresponding author), imane.jerrari-etu@etu.univh2c.ma  
Ismail Assayad  
Laboratory of Information Systems (LIS), Faculty of Sciences Ain Chock & ENSEM, Hassan II University of Casablanca, Morocco
