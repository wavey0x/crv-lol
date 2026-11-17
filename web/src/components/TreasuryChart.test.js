import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import TreasuryChart, {
  prepareHistory,
  TreasuryTooltip,
} from './TreasuryChart';

jest.mock('recharts', () => {
  const React = require('react');
  return {
    ...jest.requireActual('recharts'),
    ResponsiveContainer: ({ children }) =>
      React.cloneElement(children, { width: 600, height: 160 }),
  };
});

const day = 86400;
const point = (date, values = {}) => ({
  captured_at: date * day + 100,
  captured_block: 1000 + date,
  stablecoins_usd: '100',
  governance_usd: '300',
  other_usd: '0',
  complete: true,
  ...values,
});

test('keeps the latest observation and filters ranges by UTC day', () => {
  const history = [point(1), point(70), point(100)];
  const filtered = prepareHistory(history, '30');
  expect(filtered).toHaveLength(1);
  expect(filtered[0].captured_block).toBe(1100);
  expect(prepareHistory(history, 'All')[0].captured_at).toBe(day + 100);
});

test('missing days and missing prices create gaps instead of zero valuations', () => {
  const history = [point(1), point(3, { complete: false }), point(4)];
  const points = prepareHistory(history, 'All');
  expect(points).toHaveLength(4);
  expect(points[1].stablecoins_usd).toBeNull();
  expect(points[2].stablecoins_usd).toBeNull();
  expect(points[2].governance_usd).toBeNull();
  expect(points[3].stablecoins_usd).toBe(100);
});

test('tooltip shows only the date and the two category values', () => {
  render(
    <TreasuryTooltip
      active
      payload={[{ payload: prepareHistory([point(100)], 'All')[0] }]}
    />
  );
  expect(screen.getByText('$100')).toBeInTheDocument();
  expect(screen.getByText('$300')).toBeInTheDocument();
  expect(screen.getByText('Apr 11, 1970')).toBeInTheDocument();
  expect(screen.queryByText('Combined')).not.toBeInTheDocument();
  expect(screen.queryByText(/%|Block|UTC/)).not.toBeInTheDocument();
});

test('unavailable prices do not show a misleading total in the tooltip', () => {
  render(
    <TreasuryTooltip
      active
      payload={[{ payload: point(1, { complete: false }) }]}
    />
  );
  expect(screen.getByText('Pricing unavailable')).toBeInTheDocument();
  expect(screen.queryByText('Combined')).not.toBeInTheDocument();
});

test('period controls are accessible and change the displayed range', () => {
  render(<TreasuryChart history={[point(1), point(80), point(100)]} />);
  expect(screen.getByRole('button', { name: '90D' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  fireEvent.click(screen.getByRole('button', { name: 'All' }));
  expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  expect(screen.getByText('Jan 2')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '30D' }));
  expect(screen.queryByText('Jan 2')).not.toBeInTheDocument();
});

test('the chart remains optional for older API responses', () => {
  const { container } = render(<TreasuryChart />);
  expect(container).toBeEmptyDOMElement();
});
