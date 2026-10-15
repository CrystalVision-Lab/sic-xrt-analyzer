// Apply the saved theme before first paint; contains no credentials.
(() => {
  let theme;
  try { theme = localStorage.getItem("xrt-theme:v1"); } catch { /* optional */ }
  if (theme !== "light" && theme !== "dark") theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  document.documentElement.style.backgroundColor = theme === "dark" ? "#151c21" : "#f8faf9";
})();
