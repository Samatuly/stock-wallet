"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const PRIMARY = [
  { href: "/", label: "Портфель" },
  { href: "/dashboard", label: "Дашборд" },
  { href: "/whatif", label: "Что-если" },
  { href: "/journal", label: "Журнал" },
  { href: "/alerts", label: "Алерты" },
];
const MORE = [
  { href: "/accuracy", label: "Точность прогнозов" },
  { href: "/import", label: "Импорт CSV" },
];

// Верхняя панель (одна на всё приложение, подключена в layout.tsx): на широком экране вкладки (редкие разделы в меню «Ещё»),
// на планшете и телефоне всё прячется за одну кнопку-меню.
export default function AppBar() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);

  // Закрываем меню при переходе на другую страницу
  useEffect(() => {
    setMenuOpen(false);
    setMoreOpen(false);
  }, [pathname]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setMenuOpen(false);
        setMoreOpen(false);
      }
    }
    function onClick(e: MouseEvent) {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) setMoreOpen(false);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, []);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const moreActive = MORE.some((l) => isActive(l.href));

  return (
    <>
      <div className="appbar">
        <div className="appbar-inner">
          <Link href="/" className="brand" aria-label="Stock Wallet, на главную">
            <span className="brand-mark" aria-hidden="true" />
            Stock Wallet
          </Link>

          <nav className="nav-desktop" aria-label="Разделы">
            {PRIMARY.map((l) => (
              <Link key={l.href} href={l.href} className={isActive(l.href) ? "active" : ""} aria-current={isActive(l.href) ? "page" : undefined}>
                {l.label}
              </Link>
            ))}
            <div className="nav-more" ref={moreRef}>
              <button
                type="button"
                className={`nav-more-btn ${moreActive ? "active" : ""}`}
                aria-expanded={moreOpen}
                aria-haspopup="true"
                onClick={() => setMoreOpen((v) => !v)}
              >
                Ещё
                <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
                  <path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              {moreOpen && (
                <div className="nav-popover" role="menu">
                  {MORE.map((l) => (
                    <Link key={l.href} href={l.href} role="menuitem" className={isActive(l.href) ? "active" : ""}>
                      {l.label}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </nav>

          <button
            type="button"
            className="menu-btn"
            aria-label={menuOpen ? "Закрыть меню" : "Открыть меню"}
            aria-expanded={menuOpen}
            aria-controls="mobile-menu"
            onClick={() => setMenuOpen((v) => !v)}
          >
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
              {menuOpen ? (
                <path d="M4 4l12 12M16 4 4 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              ) : (
                <path d="M3 5.5h14M3 10h14M3 14.5h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              )}
            </svg>
          </button>
        </div>

        {menuOpen && (
          <nav id="mobile-menu" className="nav-mobile" aria-label="Разделы">
            {[...PRIMARY, ...MORE].map((l) => (
              <Link key={l.href} href={l.href} className={isActive(l.href) ? "active" : ""} aria-current={isActive(l.href) ? "page" : undefined}>
                {l.label}
              </Link>
            ))}
          </nav>
        )}
      </div>

      {menuOpen && <div className="menu-backdrop" onClick={() => setMenuOpen(false)} aria-hidden="true" />}
    </>
  );
}
