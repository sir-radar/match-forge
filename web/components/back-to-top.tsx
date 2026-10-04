"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/icon";

const SHOW_AFTER_PIXELS = 300;

export function BackToTop() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const updateVisibility = () => setVisible(window.scrollY >= SHOW_AFTER_PIXELS);
    updateVisibility();
    window.addEventListener("scroll", updateVisibility, { passive: true });
    return () => window.removeEventListener("scroll", updateVisibility);
  }, []);

  if (!visible) return null;

  const returnToTop = () => {
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    window.scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" });
    document.getElementById("main")?.focus({ preventScroll: true });
  };

  return <button className="back-to-top" type="button" aria-label="Back to top" onClick={returnToTop}><Icon name="chevron-up" /></button>;
}
