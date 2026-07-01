import { Database, ShieldCheck, Waypoints } from 'lucide-react';
import type { SkillCallView } from '../../lib/types';

type Props = {
  calls: SkillCallView[];
};

export function ToolCallGraph({ calls }: Props) {
  const latest = calls.slice(-8).reverse();
  return (
    <section className="panel span-12">
      <h2>AI Tool Calls & MCP</h2>
      <div className="panel-body">
        {latest.length === 0 ? (
          <p className="muted">Tool calls will appear after the first agent cycle.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Tool</th>
                <th>Mode</th>
                <th>Permission</th>
                <th>Latency</th>
                <th>Effect</th>
              </tr>
            </thead>
            <tbody>
              {latest.map((call) => (
                <tr key={call.id}>
                  <td>{call.agent_id ?? 'system'}</td>
                  <td>
                    <span className="toolbar">
                      <Waypoints size={15} />
                      {call.skill_name}
                    </span>
                  </td>
                  <td>{call.mode}</td>
                  <td>
                    <span className={call.permission_decision === 'allowed' ? 'badge green' : 'badge red'}>
                      <ShieldCheck size={13} />
                      {call.permission_decision}
                    </span>
                  </td>
                  <td className="mono">{call.latency_ms} ms</td>
                  <td>
                    <span className="badge">
                      <Database size={13} />
                      {call.side_effecting ? 'side-effecting' : 'read-only'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
