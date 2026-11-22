const fresh = document.getElementById("fresh");
let seen = null;

async function check() {
  try {
    const tab = fresh.dataset.tab === "raw" ? "raw" : "news";
    const url = `/api/latest?tab=${tab}` + (seen === null ? "" : `&since=${seen}`);
    const data = await (await fetch(url)).json();
    if (seen === null) seen = data.latest;
    else if (data.new > 0) {
      document.getElementById("fresh-text").textContent =
        data.new === 1 ? "1 new item arrived." : `${data.new} new items arrived.`;
      fresh.hidden = false;
    }
  } catch {
    // The page keeps working while the server is unreachable.
  }
}

if (fresh) {
  check();
  setInterval(check, 15000);
}
