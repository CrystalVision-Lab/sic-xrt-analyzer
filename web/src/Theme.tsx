import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
type Theme = "light" | "dark";
function initialTheme(): Theme {
  try { const saved = localStorage.getItem("xrt-theme:v1"); if(saved === "light" || saved === "dark") return saved; } catch { /* theme is optional */ }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => { document.documentElement.dataset.theme = theme; document.documentElement.style.colorScheme = theme; document.documentElement.style.backgroundColor = theme === "dark" ? "#151c21" : "#f8faf9"; try { localStorage.setItem("xrt-theme:v1", theme); } catch { /* no credentials are stored */ } }, [theme]);
  return <button className="theme-toggle" aria-label={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"} aria-pressed={theme === "dark"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={18}/> : <Moon size={18}/>}<span>{theme === "dark" ? "라이트" : "다크"}</span></button>;
}
