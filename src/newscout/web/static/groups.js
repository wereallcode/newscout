// Remembers which groups you opened, so they stay open after adding or deleting a source.
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
    } catch {
      // Without storage the groups simply start closed.
    }
  });
}

// The pencil sits in the group's header: it opens the group and its edit form
// without folding the group shut, which a click inside the header would do.
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

// Opening Add group puts the cursor straight in the name field.
document.getElementById("new-group")?.addEventListener("change", (event) => {
  if (event.target.checked) document.querySelector(".new-group input").focus();
});
