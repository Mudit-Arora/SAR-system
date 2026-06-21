# Lost-Person-Behavior references (for the map prior)

**Purpose.** Pointers to the standard lost-person-behavior (LPB) literature that shapes the
probability-map prior — how lost people move by terrain and subject category. This is *reference
material*, not a dataset. Use these to ground the prior rather than inventing movement
assumptions (per `docs/SAR_project_plan.md` §7).

> ⚠️ **Numbers are unverified.** High confidence these are the standard references; **low
> confidence on any specific figure** until checked against the primary source. Do not hard-code
> a statistic from memory — pull it from the document and cite it.

## Primary references

- **Koester, Robert J. — *Lost Person Behavior: A Search and Rescue Guide on Where to Look — for
  Land, Air and Water*** (dbS Productions, 2008). The standard field reference. Defines subject
  categories (hiker, hunter, despondent, dementia, child by age band, etc.) and, per category,
  distance-from-IPP distributions, dispersion angles, elevation-change tendencies, and
  find-location features (trails, drainages, structures).
  - Publisher / author hub: https://www.dbs-sar.com/

- **ISRID — International Search & Rescue Incident Database.** The empirical base behind *Lost
  Person Behavior*: tens of thousands of real SAR incidents, aggregated into the
  probability-of-area statistics (e.g. the 25/50/75/95% distance rings per subject category).
  - Background: https://www.dbs-sar.com/SAR_Research/ISRID.htm

## What we actually need from these (for the prior)

1. **Subject category → distance-from-IPP distribution.** The ring percentiles (how far from the
   Initial Planning Point the subject is found, by category) seed the radial shape of the prior.
2. **Mobility / terrain interaction.** Tendencies to follow trails, drainages, ridgelines, or to
   travel downhill — these weight the prior against the terrain (DEM) and land-cover layers.
3. **Find-feature priors.** Where people are actually found (linear features, structures, water)
   — informs how OSM trails/roads/water bias the prior.

## How it connects

These statistics are an *input to the prior model*, documented separately in `docs/prior_model.md`
(referenced by the plan). The terrain layers in `data/terrain/` supply the spatial substrate; the
LPB stats supply the movement priors that get draped over it. Verify specific numbers against the
source before they enter any config (`cell_size_m`, prior weights, etc.).
