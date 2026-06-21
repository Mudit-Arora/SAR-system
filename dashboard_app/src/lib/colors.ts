// Probability heat color scale: very low (deep blue) -> very high (red),
// matching the legend in the SAR mockup. t in [0,1].
const STOPS: [number, [number, number, number]][] = [
  [0.0, [12, 26, 64]], // deep navy / very low
  [0.25, [22, 90, 170]], // blue
  [0.45, [30, 180, 180]], // cyan/teal
  [0.6, [70, 200, 90]], // green
  [0.75, [240, 210, 60]], // yellow
  [0.88, [240, 140, 40]], // orange
  [1.0, [230, 50, 40]], // red / very high
]

export function heatColor(t: number): [number, number, number] {
  const x = Math.max(0, Math.min(1, t))
  for (let i = 0; i < STOPS.length - 1; i++) {
    const [a, ca] = STOPS[i]
    const [b, cb] = STOPS[i + 1]
    if (x >= a && x <= b) {
      const f = (x - a) / (b - a)
      return [
        Math.round(ca[0] + (cb[0] - ca[0]) * f),
        Math.round(ca[1] + (cb[1] - ca[1]) * f),
        Math.round(ca[2] + (cb[2] - ca[2]) * f),
      ]
    }
  }
  return STOPS[STOPS.length - 1][1]
}

export const HEAT_GRADIENT_CSS =
  'linear-gradient(90deg,' +
  STOPS.map(([s, c]) => `rgb(${c[0]},${c[1]},${c[2]}) ${Math.round(s * 100)}%`).join(',') +
  ')'
