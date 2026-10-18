"use client";

import { useState } from "react";

// Раскрывающийся раздел. Содержимое создаётся только при первом открытии,
// поэтому тяжёлые панели (прогнозы) не делают запросов, пока их не открыли.
export default function Collapsible({
  title,
  hint,
  children,
  defaultOpen = false,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [everOpened, setEverOpened] = useState(defaultOpen);

  return (
    <div className={`collapsible ${open ? "open" : ""}`}>
      <button
        type="button"
        className="collapsible-head"
        aria-expanded={open}
        onClick={() => {
          setOpen((v) => !v);
          setEverOpened(true);
        }}
      >
        <span className="collapsible-title">
          {title}
          {hint && <span className="collapsible-hint">{hint}</span>}
        </span>
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" className="collapsible-chevron">
          <path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <div className="collapsible-body" hidden={!open}>
        {everOpened && children}
      </div>
    </div>
  );
}
