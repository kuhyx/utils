// ?theme=light|dark forces both the page tokens and the credit's theme.
const theme = new URLSearchParams(location.search).get("theme");
if (theme === "light" || theme === "dark") {
  document.documentElement.style.colorScheme = theme;
  document.querySelector("kuhy-credit").setAttribute("theme", theme);
  const surface = { dark: "#211d1b", light: "#f6f4f3" }[theme];
  document.body.style.background = surface;
}
