import { useEffect, useRef } from "react";

import type { DemoEmployee } from "../../auth/demo-employees";
import type { AuthStatus } from "../../auth/session";
import "../../styles/login.css";
import { FreightRoadScene } from "./freight-road-scene";
import { LoginCard } from "./login-card";
import { LoginHero } from "./login-hero";

const BACKGROUND_IMAGE = "/assets/login/county-valley-logistics-sunrise.png";

export function LoginPage(props: {
  employees: readonly DemoEmployee[];
  loading: boolean;
  status: AuthStatus;
  error: string | null;
  onLogin: (employeeId: string) => Promise<void> | void;
}) {
  const rootRef = useRef<HTMLElement>(null);
  const frameRef = useRef<number | null>(null);
  const targetRef = useRef({ x: 0, y: 0 });
  const currentRef = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const coarsePointer = window.matchMedia?.("(pointer: coarse)").matches ?? false;
    if (reducedMotion || coarsePointer) return undefined;

    const renderFrame = () => {
      const current = currentRef.current;
      const target = targetRef.current;
      current.x += (target.x - current.x) * .085;
      current.y += (target.y - current.y) * .085;
      root.style.setProperty("--login-parallax-x", current.x.toFixed(3));
      root.style.setProperty("--login-parallax-y", current.y.toFixed(3));
      if (Math.abs(target.x - current.x) + Math.abs(target.y - current.y) > .002) {
        frameRef.current = requestAnimationFrame(renderFrame);
      } else {
        frameRef.current = null;
      }
    };
    const schedule = () => {
      if (frameRef.current === null) frameRef.current = requestAnimationFrame(renderFrame);
    };
    const onPointerMove = (event: PointerEvent) => {
      targetRef.current = {
        x: Math.max(-1, Math.min(1, (event.clientX / window.innerWidth - .5) * 2)),
        y: Math.max(-1, Math.min(1, (event.clientY / window.innerHeight - .5) * 2)),
      };
      schedule();
    };
    const onPointerLeave = () => {
      targetRef.current = { x: 0, y: 0 };
      schedule();
    };
    root.addEventListener("pointermove", onPointerMove, { passive: true });
    root.addEventListener("pointerleave", onPointerLeave, { passive: true });
    return () => {
      root.removeEventListener("pointermove", onPointerMove);
      root.removeEventListener("pointerleave", onPointerLeave);
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    };
  }, []);

  return <main className="county-login" data-county-login ref={rootRef}>
    <div className="county-login__scene" aria-hidden="true">
      <img src={BACKGROUND_IMAGE} alt="" decoding="async" fetchPriority="high" />
      <div className="county-login__scene-shade" />
      <div className="county-login__sun" />
      <FreightRoadScene />
      <div className="county-login__foreground" />
    </div>
    <div className="county-login__layout">
      <LoginHero />
      <div className="county-login__access county-login__reveal county-login__reveal--card"><LoginCard {...props} /></div>
    </div>
    <span className="county-login__version">CountyFlow · 智慧县域物流调度系统</span>
  </main>;
}
