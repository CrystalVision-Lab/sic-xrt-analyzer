import {
  LoaderCircle,
  AlertCircle,
  Inbox,
  Layers3,
  ArrowUpRight,
} from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "./api";
export function Brand({ inverse = false }: { inverse?: boolean }) {
  return (
    <Link
      to="/"
      className={`brand ${inverse ? "inverse" : ""}`}
      aria-label="SiC XRT Analyzer 홈"
    >
      <span className="brand-symbol">
        <Layers3 size={23} />
      </span>
      <span>
        SiC XRT<span className="brand-sub">ANALYZER</span>
      </span>
    </Link>
  );
}
export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`pill ${tone}`}>{children}</span>;
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <Inbox size={32} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function Loading() {
  return (
    <div role="status" className="loading">
      <LoaderCircle className="spin" size={19} /> 서버에서 불러오는 중
    </div>
  );
}
export function ErrorBox({ error }: { error: Error }) {
  const message =
    error instanceof ApiError && error.status === 401
      ? "관리자 세션이 없거나 만료됐습니다. 다시 로그인해 주세요."
      : error instanceof ApiError && error.status === 429
        ? "요청이 많습니다. 잠시 후 다시 시도해 주세요."
        : "서버에 연결하지 못했습니다. 연결 상태를 확인하고 다시 시도해 주세요.";
  return (
    <div role="alert" className="error">
      <AlertCircle size={19} />
      {message}
    </div>
  );
}
export function Heading({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow?: string;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {children && <p className="lead">{children}</p>}
      </div>
      {action}
    </div>
  );
}
export function External({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-link"
    >
      {children}
      <ArrowUpRight size={15} />
    </a>
  );
}
export function JsonDetails({
  value,
  label = "상세 기록",
}: {
  value: unknown;
  label?: string;
}) {
  return (
    <details className="json-details">
      <summary>{label}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

export function Modal({
  children,
  labelId,
  onClose,
  disabled = false,
}: {
  children: ReactNode;
  labelId: string;
  onClose: () => void;
  disabled?: boolean;
}) {
  const dialog = useRef<HTMLElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : undefined;
    const node = dialog.current;
    const focusable = () =>
      Array.from(
        node?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),input,select,textarea,a[href],[tabindex="0"]',
        ) ?? [],
      );
    focusable()[0]?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !disabled) {
        e.preventDefault();
        close.current();
      }
      if (e.key === "Tab") {
        const items = focusable();
        const first = items[0];
        const last = items.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [disabled]);
  return (
    <div className="modal-backdrop">
      <section
        ref={dialog}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelId}
      >
        {children}
      </section>
    </div>
  );
}
