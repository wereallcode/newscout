const KEY = "newscout-saved";

function remember(value) {
  try {
    if (value) sessionStorage.setItem(KEY, value);
    else sessionStorage.removeItem(KEY);
  } catch {}
}

function recall() {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

document.addEventListener("submit", (event) => {
  const button = event.submitter;
  if (button && button.dataset.busy && !event.defaultPrevented) {
    button.classList.add("busy");
    button.textContent = button.dataset.busy;
    return;
  }
  if (!button || !button.classList.contains("save")) return;
  button.classList.add("saved");
  remember(event.target.action);
});

const pressed = recall();
remember(null);
if (pressed && document.querySelector(".flash.ok")) {
  for (const form of document.forms) {
    const button = form.querySelector(".save");
    if (form.action !== pressed || !button) continue;
    const label = button.innerHTML;
    button.classList.add("saved", "pop");
    button.innerHTML =
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l4 4 10-10"/></svg>Saved';
    setTimeout(() => {
      button.classList.remove("saved", "pop");
      button.innerHTML = label;
    }, 1600);
    break;
  }
}

window.addEventListener("pageshow", (event) => {
  if (event.persisted && document.querySelector(".busy")) location.reload();
});
