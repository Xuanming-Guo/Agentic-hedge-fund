type Props = {
  open: boolean;
  reason?: string;
};

export function HumanApprovalModal({ open, reason }: Props) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/30">
      <section className="panel w-[min(32rem,calc(100vw-2rem))]">
        <h2>Human Approval</h2>
        <div className="panel-body">
          <p>{reason ?? 'Manual approval is required before this simulated order can continue.'}</p>
          <div className="toolbar">
            <button className="btn primary">Approve</button>
            <button className="btn">Approve resized</button>
            <button className="btn warning">Reject</button>
          </div>
        </div>
      </section>
    </div>
  );
}
