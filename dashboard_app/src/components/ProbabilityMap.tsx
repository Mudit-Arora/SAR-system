// DEMO MODE: the central map shows a pre-rendered animation of the 3-drone search + guide-home
// run (demo_output/search_and_guide_3drones.gif, copied into public/). This stands in for the
// live server-rendered map (/map_base.png + vector overlays) so the dashboard can be demoed
// without the integration server running. The gif already bakes in the terrain, posterior heat,
// the drone fleet + trails, and the guide-home route, so no live overlays are drawn over it.
const DEMO_GIF = '/search_and_guide_3drones.gif'

export default function ProbabilityMap() {
  return (
    <div className="panel relative flex-1 overflow-hidden bg-base-950">
      {/* The map content is a centered SQUARE (matching the demo gif's aspect), so it is never
          stretched into the panel's rectangle. */}
      <div className="absolute inset-0 grid place-items-center">
        <div className="relative aspect-square h-full max-w-full">
          <img
            src={DEMO_GIF}
            alt="3-drone search and guide-home demo"
            draggable={false}
            className="absolute inset-0 h-full w-full object-contain"
          />
        </div>
      </div>

      {/* Compass */}
      <div className="absolute right-3 top-3 grid h-9 w-9 place-items-center rounded-full bg-base-900/80 text-[10px] font-bold text-slate-300 ring-1 ring-white/10">
        <span className="text-accent-red">N</span>
      </div>

    </div>
  )
}
