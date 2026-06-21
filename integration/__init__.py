# =============================================================================
# integration/ — the glue package (Milestone 1)
# -----------------------------------------------------------------------------
# Responsible for: ALL translation between the vendored teammate tracks and the
#                  brain core. Adapters live here and ONLY here, so neither side is
#                  rewritten: the detector (detector/) and dashboard (dashboard_app/)
#                  stay as-vendored, and the brain's src/ is touched only additively.
# Role in project: The integration seam. detector_adapter -> telemetry/backends ->
#                  loop -> dashboard_projection -> server, wiring real YOLO detections
#                  through the GeoReferencer into the single-writer SearchBrain and out
#                  to the React dashboard.
# Assumptions: Importable as a package from the repo root (same as `src`); heavy
#              detector deps (ultralytics/torch/opencv) are imported lazily by the
#              modules that need them, so importing this package stays cheap.
# =============================================================================
