// Swaps every [data-live] region with a fresh copy so the dashboard follows the fetcher.
async function refresh() {
  try {
    const response = await fetch(location.href);
    if (!response.ok) return;
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    for (const region of document.querySelectorAll("[data-live]")) {
      const fresh = page.getElementById(region.id);
      if (region.contains(document.activeElement)) continue;
      if (fresh && fresh.innerHTML !== region.innerHTML) {
        region.replaceWith(fresh);
        fresh.classList.add("updated");
      }
    }
  } catch {
    // Keep the current view while the server is unreachable.
  }
}

setInterval(refresh, 10000);
