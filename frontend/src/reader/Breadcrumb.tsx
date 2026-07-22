import type { TrailEntry } from "./useDepthTrail";

interface Props {
  title: string;
  trail: TrailEntry[];
  onPopBack: () => void;
}

export default function Breadcrumb({ title, trail, onPopBack }: Props) {
  return (
    <div className="breadcrumb">
      <span className="breadcrumb-title" title={title}>
        {title}
      </span>
      {trail.length > 0 && (
        <>
          <span className="breadcrumb-trail">
            {trail.map((entry, i) => (
              <span key={`${entry.anchor}-${i}`} className="breadcrumb-step">
                <span className="breadcrumb-sep">›</span>
                {entry.label}
              </span>
            ))}
          </span>
          <button type="button" className="back-to-spot" onClick={onPopBack}>
            ↩ Back to your spot
          </button>
        </>
      )}
    </div>
  );
}
