function setTheme(mode) {
    localStorage.setItem("theme-storage", mode);
    var toggleBtn = document.getElementById("dark-mode-toggle");
    var darkModeStyle = document.getElementById("darkModeStyle");
    
    if (mode === "dark") {
        if (darkModeStyle) darkModeStyle.disabled = false;
        
        if (toggleBtn) {
            toggleBtn.innerHTML = `<svg class="feather" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
            </svg>`;
            toggleBtn.setAttribute('data-theme', 'dark');
        }
    } else if (mode === "light") {
        if (darkModeStyle) darkModeStyle.disabled = true;
        
        if (toggleBtn) {
            toggleBtn.innerHTML = `<svg class="feather" viewBox="0 0 24 24" fill="none" stroke="#232333" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="5"></circle>
              <line x1="12" y1="1" x2="12" y2="3"></line>
              <line x1="12" y1="21" x2="12" y2="23"></line>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
              <line x1="1" y1="12" x2="3" y2="12"></line>
              <line x1="21" y1="12" x2="23" y2="12"></line>
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
            </svg>`;
            toggleBtn.setAttribute('data-theme', 'light');
        }
    }
}

function toggleTheme() {
    var currentTheme = localStorage.getItem("theme-storage");
    if (currentTheme === "light") {
        setTheme("dark");
    } else if (currentTheme === "dark") {
        setTheme("light");
    } else if (currentTheme === "auto") {
        var isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        setTheme(isDark ? "light" : "dark");
    }
}

// Get initial theme
var savedTheme = localStorage.getItem("theme-storage");
var prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

// Apply theme based on priority: saved preference > system preference > default light
if (savedTheme) {
    setTheme(savedTheme);
} else {
    // No saved preference - use system preference
    setTheme(prefersDark ? "dark" : "light");
}

// Listen for system theme changes
var mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
mediaQuery.addEventListener("change", function(e) {
    if (localStorage.getItem("theme-storage") === "auto") {
        setTheme(e.matches ? "dark" : "light");
    }
});
