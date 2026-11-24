const KEY = "newscout-open-groups";

function opened() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || [];
  } catch {
    return [];
  }
}

for (const group of document.querySelectorAll("details[data-group]")) {
  group.open = opened().includes(group.dataset.group);
  group.addEventListener("toggle", () => {
    const rest = opened().filter((id) => id !== group.dataset.group);
    try {
      localStorage.setItem(KEY, JSON.stringify(group.open ? [...rest, group.dataset.group] : rest));
    } catch {}
  });
}

for (const pencil of document.querySelectorAll("label.group-edit-toggle")) {
  pencil.addEventListener("click", (event) => {
    event.preventDefault();
    const group = pencil.closest("details");
    const box = document.getElementById(pencil.htmlFor);
    box.checked = !box.checked || !group.open;
    group.open = true;
    if (box.checked) group.querySelector(".group-edit input").focus();
  });
}

document.getElementById("new-group")?.addEventListener("change", (event) => {
  if (event.target.checked) document.querySelector(".new-group input").focus();
});
