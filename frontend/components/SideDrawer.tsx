/**
 * SideDrawer — slide-in panel from the right edge.
 *
 * Used for "view resume original", "view project detail", etc.
 * - Fixed right edge, full height
 * - Backdrop (semi-transparent black) closes on click
 * - ESC closes
 * - Lock body scroll while open
 */

import { useEffect } from "react";

interface SideDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  width?: string;            // tailwind width class, default "w-[480px]"
  children: React.ReactNode;
}

export default function SideDrawer({
  open,
  onClose,
  title,
  width = "w-[480px]",
  children,
}: SideDrawerProps) {
  // ESC to close + lock body scroll
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        className={`fixed inset-0 bg-black/50 backdrop-blur-sm z-40 transition-opacity duration-300 ${
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`fixed right-0 top-0 h-full ${width} max-w-[95vw] bg-[#0c1024] border-l border-indigo-500/20 z-50
                    shadow-2xl shadow-indigo-500/10 flex flex-col
                    transform transition-transform duration-300 ease-out
                    ${open ? "translate-x-0" : "translate-x-full"}`}
      >
        {/* Header */}
        <header className="flex items-center justify-between px-5 py-4 border-b border-indigo-500/10 shrink-0">
          <h3 className="text-sm font-semibold text-gray-100 truncate pr-4">{title}</h3>
          <button
            onClick={onClose}
            aria-label="关闭"
            className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-100 hover:bg-white/[0.05] transition-all"
          >
            ✕
          </button>
        </header>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </aside>
    </>
  );
}