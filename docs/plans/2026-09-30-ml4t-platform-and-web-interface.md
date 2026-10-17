# Hypervector ML4T platform and web interface plan

Status: Draft for operator review. Implementation paused.

Date: September 30, 2026.

## Objective and operator mandate

Rebuild Hypervector around the complete Machine Learning for Trading, Third
Edition research-to-production workflow, including continuous experimentation,
evaluation and improvement. Replace the TUI with a polished web application that
makes research, ML processing, strategy evolution and trading economics visible.

**Aggressive bankroll building remains the objective.** The rebuild changes how
strategies are discovered, validated and improved; it does not reduce the return
ambition or substitute a defensive investment mandate.

The primary economic objective is to maximize net bankroll growth within the
operator's explicitly configured risk envelope. Research prioritizes meaningful
return potential, opportunity frequency, capital efficiency and scalable exposure.
Evaluate aggressive allocation and leverage explicitly, including venue limits,
liquidation mechanics, correlation, costs and tail outcomes. Increasing leverage
is a hypothesis to test, not a remedy assumed to fix negative expectancy.

Report bankroll growth alongside drawdown, recovery time, tail losses and ruin
probability estimates, with the assumptions and uncertainty of those estimates.
No new defensive allocation, drawdown gate or performance abort condition is
implied. Trials with disappointing results still complete and remain in the
research record; only technical failures abort unless the operator explicitly
configures otherwise. Candidate advancement policies must be explicit and
separate from trial execution.

The operator requested a plan before implementation. This document records that
plan for review; it does not activate a new strategy, change live sizing or
authorize a particular deployment package. Existing local review and economic
diagnostic work predates this planning pause and is not a completed platform.

## Confidence and evidence limits

High confidence: the operator's aggressive mandate and requested product scope
are explicit. The repository already contains trading, research, ledger,
walk-forward and purged-validation components that warrant reuse assessment.

Medium-high confidence: the proposed architecture and delivery sequence are
suitable starting points. Dependency compatibility, capacity and operational
integration require an isolated technical spike before final selection.

Unverified: whether any candidate strategy will achieve sustained profitability
or the desired growth rate. Passing software tests, adopting advanced models or
increasing experiment throughput does not establish an economic edge. Update
the design when reproducible tests show incorrect assumptions or better options.

The initial archive inspected during this discussion contained 172 closed trades,
net PnL of approximately -$429.48 and gross market PnL of approximately -$340.62
before fees and funding. It mixed 24 strategy identities. These are historical
descriptive observations, not estimates of the current policy's future returns.
The first delivery stage must freeze and independently reconcile its own inputs.

## Success criteria

1. Scientific: results are reproducible, point-in-time correct and distinguish
   exploratory tuning from independent confirmation.
2. Economic: candidate improvements are measured after costs against an incumbent
   and appropriate simple benchmarks, with emphasis on net bankroll growth.
3. Product: the operator can watch, inspect and control the workflow through a
   responsive, visually compelling web application driven by real events.
4. Operational: research workloads and UI failures do not interfere with live
   execution, position protection or durable evidence.

Maintain a capability-to-chapter traceability matrix for the third edition.
Implement its complete lifecycle rather than assuming every model technique
must be combined into a single trading strategy.

## 1. Reconstruct the economic baseline

Import existing research and the trade archive into a searchable history,
preserving strategy identities, policy changes and observation windows.

Reconstruct:

- Gross price PnL, fees, funding and execution shortfall.
- Results by strategy, asset, direction, period and deployed policy.
- Size effects, exposure, benchmark returns and winner concentration.
- Backtest-versus-live discrepancies and their technical or statistical causes.
- Hypotheses tested, rejected, inconclusive or subsequently revived.

Legacy experiments with missing trial counts or provenance receive an explicit
incomplete-evidence designation. Previously inspected history cannot become a
fresh sealed holdout through relabeling. Aggregate all-time returns must not be
presented as evidence for a single current policy.

Acceptance: accounting reconciles, and every headline metric links to its trades,
source identity, time window and definition.

## 2. Implement the complete research pipeline

| Layer | Implementation | Acceptance evidence |
| --- | --- | --- |
| Data | Versioned datasets, instrument history, availability timestamps, quality checks and immutable snapshots | Reproducible snapshots; gaps and revisions visible |
| Hypotheses | Economic mechanism, universe, horizon, execution assumptions, falsifiers and search budget | Machine-readable specification before experiments |
| Features and labels | Shared research/production transforms, label maturity and point-in-time joins | Leakage tests and training-serving parity |
| Models | Simple baselines, regularized linear models, gradient boosting and advanced-model adapters | Chronological out-of-sample comparisons |
| Validation | Walk-forward, nested selection where appropriate, purging, appropriate embargo and sealed confirmation windows | Fold results, uncertainty and recorded search breadth |
| Simulation | Fast screening followed by event-driven execution replay | Fees, funding, latency, partial fills and adverse scenarios |
| Portfolio | Allocation, leverage, correlation, turnover, exposure and capacity analysis | Incremental bankroll-growth contribution against simpler alternatives |
| Deployment | Versioned candidate packages, shadow comparison, canary operation and rollback | Reproducible package and execution parity |
| Monitoring | Data, model, execution and economic health | Each alert identifies the affected layer and response |

Deep time-series models, latent factors, text features, causal methods and
execution/hedging reinforcement learning remain in scope through defined
adapters and evaluation protocols. Complexity must demonstrate its contribution
against a baseline under the same evidence and cost assumptions.

## 3. Continuous improvement and evolution

The recurring process is:

```text
Observe outcomes -> Diagnose failure -> Propose hypothesis
       ^                                      |
       |                                      v
Deployment decision <- Shadow <- Independent evaluation <- Bounded experiments
                                      |
                                      v
                           Evidence and research memory
                                      |
                                      +-> Next hypothesis
```

Each cycle:

1. Detect a specific change in data quality, prediction quality, execution costs
   or economic performance.
2. Select the investigation appropriate to that failure class.
3. Generate a bounded experiment family changing one intended component.
4. Execute in isolated workers with explicit resource and spending budgets.
5. Independently compare candidate and incumbent on matching evidence.
6. Record the conclusion, uncertainty, failure conditions and provenance.
7. Prepare the next experiment or a concrete deployment package.

Research agents receive typed tools, structured outputs and source-backed
evidence. An independent evaluator owns scoring. Proposing agents cannot revise
their evaluation criteria after observing results. Research agents have no
direct order authority or trading credentials.

Persistent research memory stores what was learned, supporting evidence,
validity conditions and what would overturn the lesson. Duplicate hypotheses
are detected before spending more compute. Lessons can expire or be revised;
they do not become permanent rules merely because an agent wrote them.

Track improvement in economic contribution, evidence quality and time to a
reliable decision. Model accuracy, number of experiments and version count are
supporting diagnostics, not the optimization objective.

## 4. Broaden strategy discovery by return mechanism

Organize research by source of return rather than indicator names:

- Funding and financing constraints.
- Liquidity provision and temporary inventory pressure.
- Forced-flow dislocations and recovery.
- Predictable institutional or mechanical flows.
- Cross-market information transmission.
- Directional risk premia and trend.
- Conditional relative value.

Each family must name its executable mechanism, required data, cost sensitivity,
capacity and primary failure modes. Previously rejected versions remain visible.

The funding-carry investigation is one research candidate, not a replacement
for the aggressive mandate. Evaluate whether its capital efficiency and return
capacity contribute meaningfully to bankroll growth before prioritizing it.
Historical funding receipts alone are not strategy profit: basis movement,
hedging, fees, custody, asynchronous fills and margin stress need evaluation.

## 5. Web product and visual direction

Replace the TUI with a premium web workspace: graphite surfaces, crisp typography,
restrained luminous accents, rich charts, smooth transitions and an expansive
animated workflow canvas. Make real progress visually rewarding and easy to
understand. Motion represents actual data arrivals, stage transitions, completed
folds, candidate branches and failures; it does not fabricate activity.

Lead with bankroll trajectory, deployed capital, opportunity throughput and
strategy contribution, with the ML workflow immediately accessible underneath.
Losses, stalled work, stale evidence and uncertainty remain clearly visible.

| Workspace | Experience |
| --- | --- |
| Overview | Bankroll economics, deployed capital, opportunities, active experiments, health and next consequential decision |
| Live Workflow | Zoomable graph of running nodes, dependencies, progress, resource use and failures |
| Research Lab | Hypothesis cards, specifications, trial comparisons and research history |
| Model Observatory | Feature distributions, calibration, drift, fold performance and attribution |
| Strategy Arena | Incumbent/challenger comparisons, cost sensitivity, exposure and growth contribution |
| Operations | Positions, protection, fills, deployment identity, alerts and operational controls |

Selecting a node opens its inputs, outputs, dataset identity, metrics, logs and
artifacts. A timeline replays how a candidate evolved. Live, simulated and
historical results are labeled distinctly.

Acceptance: real backend events drive the interface; reconnect restores state;
keyboard navigation and reduced motion work; stale data is unmistakable. Visual
review covers the principal screens and loading, empty, failure and recovery
states. Browser closure does not stop trading.

## 6. Proposed architecture

| Component | Proposal |
| --- | --- |
| Web application | React, TypeScript, Vite, Tailwind and React Flow |
| API and event stream | Python API, typed contracts and resumable server events |
| Workflow execution | Prefect with isolated research workers |
| Experiment/model tracking | MLflow behind the custom interface |
| Market artifacts | Existing Parquet/DuckDB infrastructure and immutable manifests |
| Operational metadata | PostgreSQL for concurrent workflow state and audit records |
| Execution | Existing Python backend behind a narrow command boundary |

These are proposed choices, subject to compatibility and load testing. Assess
existing modules before adding competing registries, validation engines or data
stores. Define the authority for each record type and avoid dual writers.

Separate research, application and live execution dependencies. Research work
uses its own environment and explicit CPU, memory, disk and spending budgets.
The earlier observation of roughly 16 GiB available disk makes capacity planning
part of the first stage; remeasure before scheduling substantial jobs.

The browser never stores trading credentials. Commands retain backend-owned
validation, identity, idempotency and audit records. Workflow state and trading
lifecycle state remain distinct. Interface or research-worker failure must not
remove live protection or alter configured execution policy.

## 7. Delivery sequence

| Stage | Deliverable | Completion criterion |
| --- | --- | --- |
| A. Baseline and architecture | Economic reconstruction, reuse inventory, chapter mapping, schemas and dependency decisions | Reconciled evidence and executable acceptance specifications |
| B. Product design | Detailed screen designs and interactive prototype | Visual direction and essential operator journeys reviewed |
| C. First complete workflow | One real hypothesis from dataset through evaluation, visible in the new UI | Reproducible result, live progress and inspectable artifacts |
| D. Research breadth | Model/feature adapters, realistic simulation, portfolio evaluation and experiment registry | Multiple mechanisms evaluated through shared contracts |
| E. Continuous improvement | Scheduled diagnosis, bounded experiments, independent evaluator and memory | Demonstrated propose-test-compare-learn cycle |
| F. Production feedback | Shadow comparisons, execution attribution, deployment packages and rollback | Replay parity and recovery exercises pass |
| G. TUI retirement | Web operations and installation become the primary interface | Necessary operational parity verified; TUI removed from normal operation |

Build Stage C early, then expand the same working system. This produces visible
progress while avoiding a collection of disconnected tools. The full lifecycle
remains the delivery scope; an attractive dashboard alone is not completion.

The TUI removal is sequenced after its necessary operational functions are
covered. Retain recoverable release artifacts for rollback, but remove TUI
dependencies from normal operator workflows at cutover.

## 8. Validation and failure handling

Required experiments include:

- Deliberately leaked features are detected.
- Future or immature labels cannot enter training prematurely.
- Dataset revisions and missing observations are explicit.
- Interrupted workers resume without duplicate experiments or artifacts.
- An independent evaluator reproduces results from recorded identities.
- Research load does not delay live execution or protection.
- UI metrics reconcile with backend evidence and recover after disconnection.
- Inspected historical windows cannot silently become out-of-sample validation.
- Deployment rollback restores the exact model, features and associated contracts.
- Claimed economic improvements face realistic cost and timing perturbations.

Use hermetic unit tests for business logic, integration tests for artifact and
service boundaries, execution replay for trading behavior, and browser tests
plus visual inspection for the interface. Keep network calls out of unit tests.
Record baseline failures separately from regressions.

Distinguish technical failures from statistical or economic failures. Fix data
or execution defects at their source; do not respond to inflated execution costs
by blindly retraining a model. Run-age growth, resource exhaustion and untested
rollback are explicit operational failure modes.

## 9. Tradeoffs and decisions to finalize

| Option | Benefit | Limitation | Recommendation |
| --- | --- | --- | --- |
| Continue small isolated revisions | Lowest immediate migration effort | Does not establish a unified learning process | Retain necessary maintenance only during transition |
| Dashboard over current files | Fast visual improvement | Incomplete provenance and workflow control remain | Use only as an early integration surface |
| Integrated ML4T platform with staged delivery | Shared evidence, evaluation, feedback and compelling visibility | Significant integration and operational work | Recommended |
| Wholesale execution rewrite | Maximum architectural freedom | Adds migration risk and delays economic learning | Reuse verified execution components unless tests justify replacement |

Finalize return horizon, risk envelope, research resource budget and deployment
policies as explicit configuration, using existing operator choices where
available. Do not silently reduce the aggressive mandate or invent new limits.
Technical estimates follow the Stage A inventory rather than a speculative
calendar promise.

The next authorized action after plan review is implementation of the agreed
stages. Until then, implementation remains paused. Saving this document is a
documentation action, not activation of the proposed system.

## Sources

- [ML4T third-edition companion repository](https://github.com/stefan-jansen/machine-learning-for-trading): end-to-end research, production and feedback workflow.
- [React Flow documentation](https://reactflow.dev/): proposed interactive graph foundation.
- [Prefect documentation](https://docs.prefect.io/v3/get-started/index): proposed workflow orchestration.
- [MLflow documentation](https://mlflow.org/docs/latest/ml/): proposed experiment and model tracking.
- `docs/reviews/2026-09-29-v95-sweep-assessment.md`: current reliability findings and evidence limitations.
- `docs/plans/2026-09-30-economic-reset.md`: earlier bounded economic diagnostic work; this document expands the proposed scope to the full platform.
