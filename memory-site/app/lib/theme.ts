// Shared by the layout, which runs THEME_SCRIPT before the first paint, and ThemeSwitch.
export const THEME_KEY = "lighthouse.theme";
export const DARK = "(prefers-color-scheme: dark)";
export const THEME_SCRIPT = `(function(){try{var c=localStorage.getItem("${THEME_KEY}");var d=c==="dark"||(c!=="light"&&matchMedia("${DARK}").matches);document.documentElement.dataset.theme=d?"dark":"light"}catch(e){}})()`;
