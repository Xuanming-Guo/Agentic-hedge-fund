import { ArrowLeft, ArrowRight, GripVertical, Maximize2, RotateCcw, X } from 'lucide-react';
import { useEffect, useMemo, useState, type DragEvent, type ReactNode } from 'react';

export type WorkspacePanelCategory = 'Market' | 'Agents' | 'Governance' | 'Diagnostics';

export type WorkspacePanel = {
  id: string;
  title: string;
  category: WorkspacePanelCategory;
  defaultVisible: boolean;
  defaultSpan: 4 | 6 | 8 | 12;
  defaultRows?: 1 | 2 | 3;
  minRows?: 1 | 2 | 3;
  compactClass?: string;
  render: () => ReactNode;
};

type LayoutItem = {
  id: string;
  span: 4 | 6 | 8 | 12;
  rows: 1 | 2 | 3;
};

type DropTarget = {
  id: string;
  position: 'before' | 'after';
};

type Props = {
  panels: WorkspacePanel[];
  storageKey: string;
};

const spanCycle: LayoutItem['span'][] = [4, 6, 8, 12];
const rowCycle: LayoutItem['rows'][] = [1, 2, 3];

function rowsFor(panel: WorkspacePanel): LayoutItem['rows'] {
  return panel.defaultRows ?? panel.minRows ?? 1;
}

function defaultLayout(panels: WorkspacePanel[]): LayoutItem[] {
  return panels
    .filter((panel) => panel.defaultVisible)
    .map((panel) => ({ id: panel.id, span: panel.defaultSpan, rows: rowsFor(panel) }));
}

function loadLayout(storageKey: string, panels: WorkspacePanel[]): LayoutItem[] {
  if (typeof window === 'undefined') return defaultLayout(panels);
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return defaultLayout(panels);
    const parsed = JSON.parse(raw) as LayoutItem[];
    if (!Array.isArray(parsed)) return defaultLayout(panels);
    const known = new Map(panels.map((panel) => [panel.id, panel]));
    const cleaned = parsed
      .filter((item) => known.has(item.id))
      .map((item) => ({
        id: item.id,
        span: spanCycle.includes(item.span) ? item.span : known.get(item.id)?.defaultSpan ?? 4,
        rows: rowCycle.includes(item.rows) ? item.rows : rowsFor(known.get(item.id) as WorkspacePanel)
      }));
    return cleaned.length ? cleaned : defaultLayout(panels);
  } catch {
    return defaultLayout(panels);
  }
}

function groupedPanels(panels: WorkspacePanel[]) {
  return panels.reduce<Record<WorkspacePanelCategory, WorkspacePanel[]>>(
    (groups, panel) => {
      groups[panel.category].push(panel);
      return groups;
    },
    { Market: [], Agents: [], Governance: [], Diagnostics: [] }
  );
}

export function DockableWorkspace({ panels, storageKey }: Props) {
  const panelById = useMemo(() => new Map(panels.map((panel) => [panel.id, panel])), [panels]);
  const groups = useMemo(() => groupedPanels(panels), [panels]);
  const [layout, setLayout] = useState<LayoutItem[]>(() => loadLayout(storageKey, panels));
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<DropTarget | null>(null);

  useEffect(() => {
    window.localStorage.setItem(storageKey, JSON.stringify(layout));
  }, [layout, storageKey]);

  function addPanel(id: string) {
    const panel = panelById.get(id);
    if (!panel) return;
    setLayout((current) =>
      current.some((item) => item.id === id)
        ? current
        : [...current, { id, span: panel.defaultSpan, rows: rowsFor(panel) }]
    );
  }

  function removePanel(id: string) {
    setLayout((current) => current.filter((item) => item.id !== id));
  }

  function movePanel(id: string, direction: -1 | 1) {
    setLayout((current) => {
      const index = current.findIndex((item) => item.id === id);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function resizePanel(id: string) {
    setLayout((current) =>
      current.map((item) => {
        if (item.id !== id) return item;
        const index = spanCycle.indexOf(item.span);
        const nextSpan = spanCycle[(index + 1) % spanCycle.length];
        if (nextSpan !== spanCycle[0]) return { ...item, span: nextSpan };
        const rowIndex = rowCycle.indexOf(item.rows);
        return { ...item, span: nextSpan, rows: rowCycle[(rowIndex + 1) % rowCycle.length] };
      })
    );
  }

  function resetLayout() {
    setLayout(defaultLayout(panels));
  }

  function updateDropTarget(event: DragEvent<HTMLDivElement>, id: string) {
    event.preventDefault();
    if (!draggingId || draggingId === id) {
      setDropTarget(null);
      return;
    }
    const bounds = event.currentTarget.getBoundingClientRect();
    const position = event.clientX < bounds.left + bounds.width / 2 ? 'before' : 'after';
    setDropTarget({ id, position });
  }

  function dropOn(id: string, position: DropTarget['position'] = 'before') {
    if (!draggingId || draggingId === id) return;
    setLayout((current) => {
      const from = current.findIndex((item) => item.id === draggingId);
      const to = current.findIndex((item) => item.id === id);
      if (from < 0 || to < 0) return current;
      const next = [...current];
      const [moved] = next.splice(from, 1);
      const targetIndex = next.findIndex((item) => item.id === id);
      next.splice(position === 'after' ? targetIndex + 1 : targetIndex, 0, moved);
      return next;
    });
    setDraggingId(null);
    setDropTarget(null);
  }

  const visibleIds = new Set(layout.map((item) => item.id));

  return (
    <section className="workspace">
      <div className="workspace-toolbar">
        <div>
          <span className="muted">Dockable workspace</span>
          <strong>Trading cockpit</strong>
        </div>
        <div className="toolbar">
          <details className="add-panel-menu">
            <summary className="btn">Add Panel</summary>
            <div className="add-panel-popover">
              {(Object.keys(groups) as WorkspacePanelCategory[]).map((category) => (
                <div className="panel-menu-group" key={category}>
                  <span className="muted">{category}</span>
                  {groups[category].map((panel) => (
                    <button
                      className="btn"
                      disabled={visibleIds.has(panel.id)}
                      key={panel.id}
                      onClick={() => addPanel(panel.id)}
                    >
                      {panel.title}
                      {visibleIds.has(panel.id) ? ' active' : ''}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </details>
          <button className="btn" onClick={resetLayout}>
            <RotateCcw size={15} />
            Reset layout
          </button>
        </div>
      </div>

      <div className="workspace-grid" aria-label="Dockable dashboard workspace">
        {layout.map((item, index) => {
          const panel = panelById.get(item.id);
          if (!panel) return null;
          return (
            <div
              className={[
                'dock-panel',
                `span-${item.span}`,
                `row-span-${item.rows}`,
                panel.compactClass ?? '',
                draggingId === item.id ? 'dragging' : '',
                dropTarget?.id === item.id ? `drop-target drop-${dropTarget.position}` : ''
              ]
                .filter(Boolean)
                .join(' ')}
              draggable
              key={item.id}
              onDragEnd={() => {
                setDraggingId(null);
                setDropTarget(null);
              }}
              onDragLeave={() => {
                if (dropTarget?.id === item.id) setDropTarget(null);
              }}
              onDragOver={(event) => updateDropTarget(event, item.id)}
              onDragStart={() => setDraggingId(item.id)}
              onDrop={() => dropOn(item.id, dropTarget?.position)}
            >
              <div className="dock-panel-controls" aria-label={`${panel.title} panel controls`}>
                <span className="dock-handle" title="Drag panel">
                  <GripVertical size={15} />
                </span>
                <button
                  aria-label={`Move ${panel.title} left`}
                  className="icon-btn"
                  disabled={index === 0}
                  onClick={() => movePanel(item.id, -1)}
                  title="Move left"
                >
                  <ArrowLeft size={14} />
                </button>
                <button
                  aria-label={`Move ${panel.title} right`}
                  className="icon-btn"
                  disabled={index === layout.length - 1}
                  onClick={() => movePanel(item.id, 1)}
                  title="Move right"
                >
                  <ArrowRight size={14} />
                </button>
                <button
                  aria-label={`Resize ${panel.title}`}
                  className="icon-btn"
                  onClick={() => resizePanel(item.id)}
                  title="Resize"
                >
                  <Maximize2 size={14} />
                </button>
                <button
                  aria-label={`Remove ${panel.title}`}
                  className="icon-btn"
                  onClick={() => removePanel(item.id)}
                  title="Remove"
                >
                  <X size={14} />
                </button>
              </div>
              {panel.render()}
            </div>
          );
        })}
      </div>
    </section>
  );
}
