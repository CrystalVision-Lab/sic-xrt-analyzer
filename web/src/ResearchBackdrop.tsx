import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Pause, Play } from "lucide-react";

// Fixed decoration: no random render values, canvas loop, external assets or data requests.
const particles = [
  [7, 28, 3, 12], [16, 76, 2, 15], [23, 13, 2, 10], [35, 58, 3, 17],
  [44, 30, 2, 14], [51, 83, 3, 12], [62, 12, 2, 16], [69, 68, 2, 11],
  [77, 39, 3, 18], [84, 78, 2, 14], [91, 18, 3, 13], [96, 54, 2, 16],
];

export function ResearchBackdrop() {
  const root = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState(true);
  const [inView, setInView] = useState(true);
  const [visible, setVisible] = useState(() => !document.hidden);
  const [reduced, setReduced] = useState(() =>
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
  );

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const onMotion = () => setReduced(media?.matches ?? false);
    const onVisibility = () => setVisible(!document.hidden);
    media?.addEventListener("change", onMotion);
    document.addEventListener("visibilitychange", onVisibility);
    const observer = typeof IntersectionObserver === "undefined" ? null :
      new IntersectionObserver(entries => setInView(entries.some(entry => entry.isIntersecting)));
    if (root.current) observer?.observe(root.current);
    return () => {
      media?.removeEventListener("change", onMotion);
      document.removeEventListener("visibilitychange", onVisibility);
      observer?.disconnect();
    };
  }, []);

  const playing = enabled && inView && visible && !reduced;
  return <>
    <div ref={root} className="research-backdrop" aria-hidden="true" data-motion={playing ? "running" : "paused"}>
      <div className="backdrop-glow backdrop-glow-teal" />
      <div className="backdrop-glow backdrop-glow-blue" />
      <div className="backdrop-glow backdrop-glow-amber" />
      <div className="backdrop-grid" />
      <div className="backdrop-contours">
        <svg viewBox="0 0 1200 800" fill="none" focusable="false">
          {Array.from({ length: 8 }, (_, i) => <ellipse key={i} cx="835" cy="340"
            rx={330 + i * 27} ry={155 + i * 21} transform="rotate(-24 835 340)" />)}
        </svg>
      </div>
      {particles.map(([x, y, size, duration], i) => <span key={i} className="backdrop-particle"
        style={{ "--x": `${x}%`, "--y": `${y}%`, "--size": `${size}px`,
          "--duration": `${duration}s`, "--delay": `${-i * 1.7}s` } as CSSProperties} />)}
      <div className="backdrop-veil" />
    </div>
    <button type="button" className="backdrop-motion" disabled={reduced}
      aria-label={reduced ? "OS 동작 줄이기 설정 적용됨" : enabled ? "배경 애니메이션 정지" : "배경 애니메이션 재생"}
      aria-pressed={!enabled || reduced} onClick={() => setEnabled(value => !value)}>
      {enabled && !reduced ? <Pause size={13} /> : <Play size={13} />}
      <span>{reduced ? "정적 배경" : enabled ? "배경 정지" : "배경 재생"}</span>
    </button>
  </>;
}
