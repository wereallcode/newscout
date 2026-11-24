// A Save button turns green when pressed, and again after the page reloads
// if the server confirmed the save, so the feedback survives the redirect.
const KEY = "newscout-saved";

function remember(value) {
  try {
    if (value) sessionStorage.setItem(KEY, value);
    else sessionStorage.removeItem(KEY);
  } catch {
    // Without storage the button still turns green while the form submits.
  }
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
  // Buttons that wait on the network say what they are doing until the page reloads.
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

// Coming back with the browser's Back button must not leave a button spinning.
window.addEventListener("pageshow", (event) => {
  if (event.persisted && document.querySelector(".busy")) location.reload();
});
