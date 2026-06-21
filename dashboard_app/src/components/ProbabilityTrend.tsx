import { Area, AreaChart, ResponsiveContainer, YAxis, XAxis, Tooltip } from 'recharts'
import type { ProbabilityPoint } from '../types'

export default function ProbabilityTrend({
  data,
  now,
}: {
  data: ProbabilityPoint[]
  now: number
}) {
  return (
    <div className="panel flex flex-col p-3">
      <div className="flex items-center justify-between">
        <div className="panel-header">
          Probability Trend <span className="text-slate-500">(Top 5%)</span>
        </div>
        <div className="text-right leading-none">
          <div className="text-[10px] text-slate-500">Now</div>
          <div className="text-sm font-bold text-accent-cyan">{now}%</div>
        </div>
      </div>

      <div className="mt-2 h-[120px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
            <defs>
              <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.45} />
                <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="t"
              tick={{ fill: '#64748b', fontSize: 10 }}
              axisLine={{ stroke: '#1a2d4d' }}
              tickLine={false}
            />
            <YAxis
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tickFormatter={(v) => `${v}%`}
              tick={{ fill: '#64748b', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: '#0d182b',
                border: '1px solid #1a2d4d',
                borderRadius: 8,
                fontSize: 11,
              }}
              labelStyle={{ color: '#94a3b8' }}
              formatter={(v: number) => [`${v}%`, 'Mass']}
            />
            <Area
              type="monotone"
              dataKey="mass"
              stroke="#22d3ee"
              strokeWidth={2}
              fill="url(#trendFill)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-1 text-[11px] text-slate-500">
        The probability is concentrating in a smaller area.
      </p>
    </div>
  )
}
