import { RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { MouseEvent } from 'react';
import type { MarketBar } from '../../lib/types';

type Props = {
  bars: MarketBar[];
  symbol: string;
};

const width = 860;
const height = 320;
const padding = { top: 20, right: 58, bottom: 32, left: 52 };
const defaultVisibleCandles = 96;
const minVisibleCandles = 12;

type DragState = {
  x: number;
  endIndex: number;
};

function yFor(price: number, min: number, max: number) {
  const plotHeight = height - padding.top - padding.bottom;
  if (max === min) return padding.top + plotHeight / 2;
  return padding.top + ((max - price) / (max - min)) * plotHeight;
}

function formatTime(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function CandlestickChart({ bars, symbol }: Props) {
  const frameRef = useRef<HTMLDivElement | null>(null);
  const defaultWindow = Math.max(1, Math.min(defaultVisibleCandles, bars.length));
  const [visibleCount, setVisibleCount] = useState(defaultWindow);
  const [endIndex, setEndIndex] = useState(bars.length);
  const [drag, setDrag] = useState<DragState | null>(null);

  useEffect(() => {
    const nextWindow = Math.max(1, Math.min(defaultVisibleCandles, bars.length));
    setVisibleCount(nextWindow);
    setEndIndex(bars.length);
    setDrag(null);
  }, [bars.length, symbol]);

  const clampedVisibleCount = Math.max(1, Math.min(visibleCount, bars.length || 1));
  const clampedEndIndex = Math.max(clampedVisibleCount, Math.min(endIndex, bars.length));
  const startIndex = Math.max(0, clampedEndIndex - clampedVisibleCount);
  const candles = useMemo(
    () => bars.slice(startIndex, clampedEndIndex),
    [bars, clampedEndIndex, startIndex],
  );

  function clampEnd(nextEnd: number, windowSize = clampedVisibleCount) {
    return Math.max(windowSize, Math.min(bars.length, nextEnd));
  }

  function clampWindow(nextWindow: number) {
    const minimum = Math.min(minVisibleCandles, Math.max(1, bars.length));
    return Math.max(minimum, Math.min(bars.length, nextWindow));
  }

  function zoom(direction: 'in' | 'out') {
    if (bars.length <= 1) return;
    const factor = direction === 'in' ? 0.75 : 1.35;
    const nextWindow = clampWindow(Math.round(clampedVisibleCount * factor));
    setVisibleCount(nextWindow);
    setEndIndex((current) => clampEnd(current, nextWindow));
  }

  function resetView() {
    const nextWindow = Math.max(1, Math.min(defaultVisibleCandles, bars.length));
    setVisibleCount(nextWindow);
    setEndIndex(bars.length);
    setDrag(null);
  }

  function panTo(clientX: number, base: DragState) {
    const plotWidth = width - padding.left - padding.right;
    const pixelsPerCandle = plotWidth / Math.max(1, clampedVisibleCount);
    const deltaCandles = Math.round((base.x - clientX) / Math.max(1, pixelsPerCandle));
    setEndIndex(clampEnd(base.endIndex + deltaCandles));
  }

  function handleMouseMove(event: MouseEvent<SVGSVGElement>) {
    if (!drag) return;
    event.preventDefault();
    event.stopPropagation();
    panTo(event.clientX, drag);
  }

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return undefined;

    function handleWheel(event: WheelEvent) {
      event.preventDefault();
      event.stopPropagation();
      zoom(event.deltaY < 0 ? 'in' : 'out');
    }

    frame.addEventListener('wheel', handleWheel, { passive: false });
    return () => frame.removeEventListener('wheel', handleWheel);
  });

  if (candles.length === 0) {
    return (
      <div className="empty-chart">
        <strong>{symbol}</strong>
        <span className="muted">No visible candles yet. Step into market hours.</span>
      </div>
    );
  }

  const minPrice = Math.min(...candles.map((bar) => bar.low));
  const maxPrice = Math.max(...candles.map((bar) => bar.high));
  const xStep = (width - padding.left - padding.right) / Math.max(1, candles.length);
  const candleWidth = Math.max(3, Math.min(11, xStep * 0.58));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => maxPrice - (maxPrice - minPrice) * ratio);
  const rangeLabel = `Candles ${startIndex + 1}-${clampedEndIndex} / ${bars.length}`;

  return (
    <div className="candle-stack">
      <div className="candle-toolbar">
        <span className="badge mono">{rangeLabel}</span>
        <div className="toolbar">
          <button className="btn" onClick={() => zoom('in')} type="button" aria-label="Zoom in candles">
            <ZoomIn size={15} />
            Zoom in
          </button>
          <button className="btn" onClick={() => zoom('out')} type="button" aria-label="Zoom out candles">
            <ZoomOut size={15} />
            Zoom out
          </button>
          <button className="btn" onClick={resetView} type="button" aria-label="Reset candle view">
            <RotateCcw size={15} />
            Reset
          </button>
        </div>
      </div>
      <div className="candle-frame" ref={frameRef}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${symbol} candlestick chart`}
        className={drag ? 'dragging' : undefined}
        onDragStart={(event) => event.preventDefault()}
        onMouseDown={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setDrag({ x: event.clientX, endIndex: clampedEndIndex });
        }}
        onMouseMove={handleMouseMove}
        onMouseUp={(event) => {
          if (drag) {
            event.preventDefault();
            event.stopPropagation();
          }
          setDrag(null);
        }}
        onMouseLeave={(event) => {
          if (drag) {
            event.preventDefault();
            event.stopPropagation();
          }
          setDrag(null);
        }}
      >
        <rect x="0" y="0" width={width} height={height} fill="#071023" />
        {ticks.map((tick) => {
          const y = yFor(tick, minPrice, maxPrice);
          return (
            <g key={tick}>
              <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} stroke="#223456" />
              <text x={width - padding.right + 8} y={y + 4} className="chart-label">
                {tick.toFixed(2)}
              </text>
            </g>
          );
        })}
        {candles.map((bar, index) => {
          const x = padding.left + index * xStep + xStep / 2;
          const openY = yFor(bar.open, minPrice, maxPrice);
          const closeY = yFor(bar.close, minPrice, maxPrice);
          const highY = yFor(bar.high, minPrice, maxPrice);
          const lowY = yFor(bar.low, minPrice, maxPrice);
          const up = bar.close >= bar.open;
          const bodyY = Math.min(openY, closeY);
          const bodyHeight = Math.max(2, Math.abs(closeY - openY));
          return (
            <g key={`${bar.symbol}-${bar.timestamp}`}>
              <line
                x1={x}
                x2={x}
                y1={highY}
                y2={lowY}
                stroke={up ? '#35d391' : '#ff5c7a'}
                strokeWidth="1.5"
              />
              <rect
                x={x - candleWidth / 2}
                y={bodyY}
                width={candleWidth}
                height={bodyHeight}
                rx="1"
                fill={up ? '#2fd597' : '#ff5c7a'}
              />
            </g>
          );
        })}
        <line
          x1={padding.left}
          x2={width - padding.right}
          y1={height - padding.bottom}
          y2={height - padding.bottom}
          stroke="#31466f"
        />
        <text x={padding.left} y={height - 10} className="chart-label">
          {formatTime(candles[0].timestamp)}
        </text>
        <text x={width / 2 - 24} y={height - 10} className="chart-label">
          {formatTime(candles[Math.floor(candles.length / 2)].timestamp)}
        </text>
        <text x={width - padding.right - 42} y={height - 10} className="chart-label">
          {formatTime(candles[candles.length - 1].timestamp)}
        </text>
      </svg>
      </div>
    </div>
  );
}
