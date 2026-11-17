import React, { useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import './TreasuryChart.css';

const DAY = 86400;
const SERIES = [
  { key: 'stablecoins_usd', label: 'Stablecoins', color: '#999999' },
  { key: 'governance_usd', label: 'Gov tokens', color: '#555555' },
];
const LEGEND_SERIES = [...SERIES].reverse();
const currency = (value) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
const compactCurrency = (value) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
const shortDate = (timestamp) =>
  new Date(timestamp * 1000).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });

export const prepareHistory = (history, range) => {
  const ordered = [...history].sort((a, b) => a.captured_at - b.captured_at);
  if (!ordered.length) return [];
  const lastDay = Math.floor(ordered[ordered.length - 1].captured_at / DAY);
  const cutoff = range === 'All' ? 0 : (lastDay - Number(range) + 1) * DAY;
  const points = [];
  ordered
    .filter((point) => point.captured_at >= cutoff)
    .forEach((point) => {
      const previous = points[points.length - 1];
      if (previous) {
        // An absent observation is a gap, not an interpolated valuation.
        for (
          let day = Math.floor(previous.captured_at / DAY) + 1;
          day < Math.floor(point.captured_at / DAY);
          day += 1
        ) {
          points.push({
            captured_at: day * DAY + DAY - 1,
            stablecoins_usd: null,
            governance_usd: null,
            complete: false,
          });
        }
      }
      const complete =
        point.complete &&
        SERIES.every(
          ({ key }) =>
            point[key] != null &&
            Number.isFinite(Number(point[key])) &&
            Number(point[key]) >= 0
        );
      points.push({
        ...point,
        complete,
        stablecoins_usd: complete ? Number(point.stablecoins_usd) : null,
        governance_usd: complete ? Number(point.governance_usd) : null,
      });
    });
  return points;
};

export const TreasuryTooltip = ({ active, payload }) => {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="treasury-chart-tooltip">
      <div className="treasury-chart-tooltip-date">
        {new Date(point.captured_at * 1000).toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
          year: 'numeric',
          timeZone: 'UTC',
        })}
      </div>
      {point.complete ? (
        LEGEND_SERIES.map(({ key, label, color }) => (
          <div className="treasury-chart-tooltip-row" key={key}>
            <span>
              <i style={{ backgroundColor: color }} />
              {label}
            </span>
            <span>{currency(point[key])}</span>
          </div>
        ))
      ) : (
        <div className="treasury-chart-tooltip-note">Pricing unavailable</div>
      )}
    </div>
  );
};

const TreasuryChart = ({ history = [] }) => {
  const [range, setRange] = useState('90');
  const points = useMemo(
    () => prepareHistory(history, range),
    [history, range]
  );
  if (!history.length) return null;

  const completePoints = points.filter((point) => point.complete);
  const maximum = Math.max(
    1,
    ...completePoints.map(
      (point) => point.stablecoins_usd + point.governance_usd
    )
  );
  const unit = 10 ** Math.floor(Math.log10(maximum));
  const ceiling = Math.ceil(maximum / unit) * unit;
  const lastPoint = points[points.length - 1];
  const hasOtherAssets = points.some((point) => Number(point.other_usd) > 0);

  return (
    <section className="treasury-chart" aria-label="Treasury value over time">
      <div className="treasury-chart-legend">
        {LEGEND_SERIES.map(({ key, label, color }) => (
          <span key={key}>
            <i style={{ backgroundColor: color }} />
            {label}
          </span>
        ))}
      </div>
      {completePoints.length >= 2 ? (
        <div className="treasury-chart-plot">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={points}
              margin={{ top: 8, right: 0, bottom: 0, left: 0 }}
              accessibilityLayer
              aria-label="Stablecoin and governance token values in USD"
            >
              <XAxis
                dataKey="captured_at"
                type="number"
                domain={['dataMin', 'dataMax']}
                ticks={[points[0].captured_at, lastPoint.captured_at]}
                interval="preserveStartEnd"
                tickFormatter={shortDate}
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#999999', fontSize: 9 }}
                tickMargin={8}
                height={24}
                padding={{ left: 1, right: 1 }}
              />
              <YAxis
                orientation="right"
                domain={[0, ceiling]}
                ticks={[0, ceiling]}
                tickFormatter={compactCurrency}
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#999999', fontSize: 9 }}
                width={40}
                tickMargin={8}
              />
              <Tooltip
                content={<TreasuryTooltip />}
                filterNull={false}
                cursor={{ stroke: '#cccccc', strokeWidth: 1 }}
                isAnimationActive={false}
              />
              {SERIES.map(({ key, label, color }) => (
                <Area
                  key={key}
                  name={label}
                  type="linear"
                  dataKey={key}
                  stackId="treasury"
                  stroke={color}
                  strokeWidth={1.25}
                  fill={color}
                  fillOpacity={0.17}
                  dot={false}
                  activeDot={{ r: 2.5, strokeWidth: 0 }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="treasury-chart-empty">Daily history is collecting.</div>
      )}
      <div className="treasury-chart-ranges" aria-label="Chart period">
        {['30', '90', 'All'].map((period) => (
          <button
            key={period}
            type="button"
            aria-pressed={range === period}
            onClick={() => setRange(period)}
          >
            {period === 'All' ? period : `${period}D`}
          </button>
        ))}
      </div>
      {hasOtherAssets && (
        <div className="treasury-chart-note">Other assets excluded.</div>
      )}
      {points.some((point) => !point.complete) && (
        <div className="treasury-chart-note">
          Gaps indicate unavailable prices.
        </div>
      )}
    </section>
  );
};

export default TreasuryChart;
