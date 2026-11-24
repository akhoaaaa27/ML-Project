import {normalizeTeam} from "./fixtures.js";

export function teamPicker(input, label, changed) {
  input.type = "text";
  input.autocomplete = "off";
  input.placeholder = "All teams";
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  const list = document.createElement("div");
  list.id = input.id + "-options";
  list.className = "team-options";
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-label", label);
  input.setAttribute("aria-controls", list.id);
  input.parentElement.classList.add("team-picker");
  input.after(list);
  let options, selected, visible, active;

  function close() {
    input.value = selected?.id ? selected.name : "";
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function highlight(index) {
    active = index;
    for (const [i, item] of [...list.children].entries()) item.classList.toggle("active", index === i);
    const option = list.children[index];
    if (option) {
      input.setAttribute("aria-activedescendant", option.id);
      option.scrollIntoView({block: "nearest"});
    } else input.removeAttribute("aria-activedescendant");
  }

  function open(query = "") {
    visible = options.filter(team => normalizeTeam(team.name).includes(normalizeTeam(query)));
    list.replaceChildren(...visible.map((team, index) => {
      const option = document.createElement("div");
      option.id = list.id + "-" + index;
      option.dataset.index = index;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", String(team === selected));
      option.textContent = team.name;
      return option;
    }));
    if (!visible.length) {
      const empty = document.createElement("div");
      empty.setAttribute("role", "status");
      empty.textContent = "No matching teams";
      list.append(empty);
    }
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    highlight(-1);
  }

  function choose(index) {
    const team = visible[index];
    if (!team) return;
    const different = selected !== team;
    selected = team;
    close();
    if (different) changed();
  }

  input.addEventListener("focus", () => { open(); input.select(); });
  input.addEventListener("click", () => { if (list.hidden) open(); });
  input.addEventListener("input", event => { event.stopPropagation(); open(input.value); });
  input.addEventListener("blur", close);
  list.addEventListener("mousedown", event => event.preventDefault());
  list.addEventListener("click", event => {
    const option = event.target.closest("[data-index]");
    if (option) choose(Number(option.dataset.index));
  });
  input.addEventListener("keydown", event => {
    if (["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      if (list.hidden) open();
      if (!visible.length) return;
      const index = event.key === "ArrowDown" ? (active + 1) % visible.length :
        (active < 0 ? visible.length - 1 : (active - 1 + visible.length) % visible.length);
      highlight(index);
    } else if (event.key === "Enter" && !list.hidden) {
      event.preventDefault();
      choose(Math.max(0, active));
    } else if (event.key === "Escape" && !list.hidden) {
      event.stopPropagation();
      close();
    }
  });
  const setTeams = teams => {
    options = [{id: "", name: "All teams"}, ...teams];
    selected = options.find(team => team.id === selected?.id) ?? options[0];
    close();
  };
  setTeams([]);
  return {setTeams, value: () => selected.id, clear: () => { selected = options[0]; close(); }};
}
