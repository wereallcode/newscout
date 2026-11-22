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
