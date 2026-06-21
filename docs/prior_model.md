# The Prior Probability Map — Construction Rule

**Status: pre-event design draft.** This specifies how the *initial* probability map is built
before the search loop runs — the "prior" the judge sees at `t0` that explains where to look
and why. It is the concrete combination rule that `docs/demo_scenario.md` §3 leans on and that
`docs/interfaces.md` §5.5 named but deferred. Grounded in standard SAR probability-of-area (POA)
practice (Koester / ISRID) and Bayesian search theory (Koopman, Stone).

> **No-build rule.** Design only — no implementation before Saturday. Numbers below are
> defaults to ratify, several flagged to be replaced by real Koester data (the Tier-1 gather).

---

## 1. What the prior represents

A probability mass function over the grid: `p_i = P(person in cell i)`, plus a reserved
`p_out` ("subject left the searched region"), with `Σ_i p_i + p_out = 1`. This is the **POC /
containment prior** in search-theory terms; the loop then applies detection probability (POD)
and the Bayesian update from `interfaces.md` §5.

The prior is **not** uniform and **not** just a ring around the last-known-position (LKP). It
fuses how-far-people-go statistics with where-the-terrain-lets-them-go and where-corridors-pull-them.

## 2. The combination rule (recommended)

**Per-cell, multiplicative, then normalized:**

```
prior_i  ∝  D(dist_i) · A_i · C_i
P_i = (1 − p_out) · prior_i / Σ_j prior_j          # normalize in-region mass
                                                    # p_out held separately so Σ P_i + p_out = 1
```

**Why multiplicative, not a weighted sum (the load-bearing modeling choice):** terrain is
*non-compensatory* — a cliff or deep-water cell should get ~zero probability **regardless** of
how close it is to the LKP. A product enforces that (any near-zero factor kills the cell); a
weighted sum would let proximity "buy back" an impassable cell. Multiplication is also how real
SAR terrain models (Jacobs/MRA "PDEN" layers) and Koester's factor maps actually stack. Keep a
single `combine(layers, mode="product")` seam so individual layers could switch to compensatory
later without a rewrite. *(Maps to your "explicit over clever" + "build seams, not futures".)*

### Term definitions and default values

| Term | Meaning | Default / source | Confidence |
|------|---------|------------------|-----------|
| `dist_i` | Distance from LKP to cell i. **Euclidean first** (one line); **Tobler cost-distance** is the clean upgrade (§4). | — | — |
| `D(dist)` | Distance decay. **Half-normal:** `D = exp(−dist² / (2σ²))`. | `σ ≈ 2.6 km` for a Hiker (see §3). **FLAG: replace with real per-ecoregion Koester quantiles.** | med |
| `A_i` | Accessibility ∈ [ε, 1] from slope + land cover. Impassable (cliff, deep water) → **0**. Merely-hard terrain → small `ε ≈ 0.05` (discouraged, not forbidden). | `A = Tobler_speed_i / max_speed`, or a reclassed land-cover table | med |
| `C_i` | Corridor attraction ∈ [1, k]. Boost cells on/near trails, roads, **drainages/streams** (downstream pull), ridgelines; decay to 1 within ~1–2 cells. | `k ≈ 3`. **FLAG: k is a tunable guess, not data.** | low |
| `p_out` | Reserved "left the region" mass. | `0.05–0.10`, planner-set | low |

Optional **`M_i` (explicit downhill bias): skip for v1.** Tobler cost-distance already makes
downhill cheaper to reach, so adding a separate downhill term double-counts. Build the seam,
defer the term.

## 3. Setting `σ` from Koester's Hiker data

Koester's *Lost Person Behavior* (ISRID database) gives distance-from-LKP quantiles by subject
category and ecoregion. **Hiker, Mountain/Temperate** (the scenario's terrain):

| Quantile | 25% | 50% | 75% | 95% |
|----------|-----|-----|-----|-----|
| Distance from LKP | 1.1 km | **3.1 km** | 5.8 km | 11.3 km |

For a 2-D half-normal, the 50% radius ≈ `1.177 · σ`, so **`σ ≈ 3.1 / 1.177 ≈ 2.6 km`**.
Sanity-check that `D`'s ~95% mass lands near 11.3 km. **Caveats, flagged:** these numbers are
specific to the Mountain/Temperate ecoregion — do **not** reuse them for other terrain; the
half-normal is a smooth approximation of an empirical CDF; ~5% of subjects fall beyond the 95%
radius (the prior should not hard-zero the far field — `p_out` and a non-zero tail cover this).

## 4. Distance metric: Euclidean now, cost-distance as the upgrade

- **Baseline (build first):** straight-line Euclidean distance from the LKP. One line of NumPy.
- **Upgrade (behind the same `dist_i`):** a **cost-distance / least-cost-path** from a friction
  surface — per-cell traversal cost from slope via **Tobler's hiking function**
  `W = 6·exp(−3.5·|slope + 0.05|)` km/h (flat ≈ 5 km/h; peaks ~6 km/h at a gentle downhill of
  slope ≈ −0.05 — which is the downhill pull, for free), friction = `1/W`, off-trail ×3/5,
  impassable = very high cost / NoData. Accumulate cost outward from the LKP. This makes "how
  far could they realistically have gotten" terrain-aware instead of as-the-crow-flies.

Swapping Euclidean → cost-distance changes only what feeds `dist_i`; `D`, `A`, `C`, and the
normalization are untouched. Same seam, higher fidelity.

## 5. How the prior connects to the loop

- **Invariants (don't break):** mass sums to 1 including `p_out`; impassable cells get zero
  prior; the same grid (`GridSpec`) the loop uses.
- **Stage-appropriate (expected to evolve):** `σ`, `k`, `ε`, `p_out`, the corridor decay width,
  Euclidean-vs-cost-distance — all config, all tunable Saturday.
- The Bayesian update (`interfaces.md` §5) takes this prior as `p_i⁽⁰⁾` and applies
  detection/non-detection evidence; the searched-cell unsuccessful-search update
  `p' = p(1−q)/(1−pq)` (q = POD) renormalizes correctly against `p_out`.

## 6. Honest limitations to state in the demo

The `σ→quantile` mapping assumes a half-normal the empirical data only approximates; `k` and `ε`
are unvalidated defaults; Euclidean distance ignores terrain until cost-distance is added; the
Hiker/Mountain-Temperate numbers must be swapped for the actual ecoregion if the region changes.
All stage-appropriate — the principled invariants are the normalization, the zeroing of
impassable cells, and the multiplicative (non-compensatory) structure.

## 7. Key references (verify specific numbers before relying on them)

- Koester Hiker quantiles (reproduces the 2008 ISRID table): Mansfield et al., *A Pragmatic
  Approach to Applied Search Theory*, J. Search & Rescue v4 (2020).
- Jacobs, *Terrain Based Probability Models for SAR* (MRA, 2015) — multiplicative PDEN layers.
- Bayesian search theory / update formula — Stone, *Theory of Optimal Search*; Koopman (1946).
- Tobler's hiking function — for the cost-distance friction surface.

> Provenance for the gathered behavior numbers lives in `data/behavior/koester_references.md`.
