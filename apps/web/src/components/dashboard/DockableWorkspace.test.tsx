import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, expect, test } from 'vitest';
import { DockableWorkspace, type WorkspacePanel } from './DockableWorkspace';

const panels: WorkspacePanel[] = [
  {
    id: 'candles',
    title: 'Market Replay Candles',
    category: 'Market',
    defaultVisible: true,
    defaultSpan: 8,
    defaultRows: 1,
    compactClass: 'compact-candles',
    render: () => (
      <section className="panel">
        <h2>Market Replay Candles</h2>
        <div>Candles body</div>
      </section>
    )
  },
  {
    id: 'agent-live',
    title: 'Agent Society Live',
    category: 'Agents',
    defaultVisible: true,
    defaultSpan: 4,
    defaultRows: 1,
    compactClass: 'compact-agent-live',
    render: () => (
      <section className="panel">
        <h2>Agent Society Live</h2>
        <div>Agent body</div>
      </section>
    )
  },
  {
    id: 'orderbook',
    title: 'Order Book',
    category: 'Market',
    defaultVisible: true,
    defaultSpan: 8,
    defaultRows: 1,
    compactClass: 'compact-orderbook',
    render: () => (
      <section className="panel">
        <h2>Order Book</h2>
        <div>Order book body</div>
      </section>
    )
  },
  {
    id: 'portfolio',
    title: 'Portfolio',
    category: 'Market',
    defaultVisible: true,
    defaultSpan: 4,
    defaultRows: 1,
    compactClass: 'compact-portfolio',
    render: () => (
      <section className="panel">
        <h2>Portfolio</h2>
        <div>Portfolio body</div>
      </section>
    )
  },
  {
    id: 'agent-workbench',
    title: 'Agent Workbench',
    category: 'Agents',
    defaultVisible: false,
    defaultSpan: 6,
    render: () => (
      <section className="panel">
        <h2>Agent Workbench</h2>
        <div>Workbench body</div>
      </section>
    )
  }
];

function renderedHeadings() {
  const workspace = screen.getByLabelText('Dockable dashboard workspace');
  return Array.from(workspace.querySelectorAll('.dock-panel .panel h2')).map(
    (node) => node.textContent
  );
}

beforeEach(() => {
  window.localStorage.clear();
});

test('defaults to market candles, order book, agent live, and portfolio', () => {
  render(<DockableWorkspace panels={panels} storageKey="dock-test-default" />);

  expect(screen.getByRole('heading', { name: 'Market Replay Candles' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Order Book' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Agent Society Live' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Portfolio' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Market Replay Candles' }).closest('.dock-panel')).toHaveClass(
    'span-8',
    'row-span-1',
    'compact-candles'
  );
  expect(screen.getByRole('heading', { name: 'Agent Society Live' }).closest('.dock-panel')).toHaveClass(
    'span-4',
    'row-span-1',
    'compact-agent-live'
  );
  expect(screen.getByRole('heading', { name: 'Order Book' }).closest('.dock-panel')).toHaveClass(
    'span-8',
    'row-span-1',
    'compact-orderbook'
  );
  expect(screen.getByRole('heading', { name: 'Portfolio' }).closest('.dock-panel')).toHaveClass(
    'span-4',
    'row-span-1',
    'compact-portfolio'
  );
});

test('adds removes moves and resets optional panels', () => {
  render(<DockableWorkspace panels={panels} storageKey="dock-test-actions" />);

  fireEvent.click(screen.getByText('Add Panel'));
  fireEvent.click(screen.getByRole('button', { name: 'Agent Workbench' }));
  expect(screen.getByRole('heading', { name: 'Agent Workbench' })).toBeInTheDocument();

  fireEvent.click(screen.getByLabelText('Move Portfolio left'));
  expect(renderedHeadings()).toEqual([
    'Market Replay Candles',
    'Agent Society Live',
    'Portfolio',
    'Order Book',
    'Agent Workbench'
  ]);

  fireEvent.click(screen.getByLabelText('Remove Agent Workbench'));
  expect(screen.queryByRole('heading', { name: 'Agent Workbench' })).not.toBeInTheDocument();

  fireEvent.click(screen.getByText('Add Panel'));
  const menu = screen.getByText('Add Panel').closest('.add-panel-menu');
  expect(menu).not.toBeNull();
  fireEvent.click(within(menu as HTMLElement).getByRole('button', { name: 'Agent Workbench' }));
  expect(screen.getByRole('heading', { name: 'Agent Workbench' })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Reset layout/i }));
  expect(renderedHeadings()).toEqual([
    'Market Replay Candles',
    'Agent Society Live',
    'Order Book',
    'Portfolio'
  ]);
  expect(screen.queryByRole('heading', { name: 'Agent Workbench' })).not.toBeInTheDocument();
});

test('shows a drop preview while dragging over a panel', () => {
  render(<DockableWorkspace panels={panels} storageKey="dock-test-drag" />);

  const candles = screen.getByRole('heading', { name: 'Market Replay Candles' }).closest('.dock-panel');
  const orderbook = screen.getByRole('heading', { name: 'Order Book' }).closest('.dock-panel');
  expect(candles).not.toBeNull();
  expect(orderbook).not.toBeNull();

  fireEvent.dragStart(candles as HTMLElement);
  fireEvent.dragOver(orderbook as HTMLElement, { clientX: 12 });

  expect(orderbook).toHaveClass('drop-target');
});
