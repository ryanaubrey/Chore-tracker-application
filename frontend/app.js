import { api } from "./api.js";

const root = document.querySelector("#app");
const message = document.querySelector("#message");
const logout = document.querySelector("#logout");
let invite = new URLSearchParams(location.hash.slice(1)).get("invite") ||
  new URLSearchParams(location.search).get("invite");
const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
let board, anchor, editing, mine = false;

function element(tag, value, className) {
  const node = document.createElement(tag);
  if (value != null) node.textContent = value;
  if (className) node.className = className;
  return node;
}

function button(label, action, className) {
  const node = element("button", label, className);
  node.type = "button";
  node.addEventListener("click", () => run(action));
  return node;
}

function field(form, label, name, type, value = "", options = []) {
  const wrapper = element("label", label);
  const control = element(type === "select" || type === "textarea" ? type : "input");
  control.name = name;
  if (type === "select") {
    for (const [optionValue, title] of options) {
      const option = element("option", title);
      option.value = optionValue;
      control.append(option);
    }
  } else if (type !== "textarea") control.type = type;
  control.value = value;
  wrapper.append(control);
  form.append(wrapper);
  return control;
}

function submit(form, label, action) {
  const node = element("button", label, "primary");
  node.type = "submit";
  form.append(node);
  form.addEventListener("submit", event => {
    event.preventDefault();
    node.disabled = true;
    run(() => action(Object.fromEntries(new FormData(form))))
      .finally(() => { node.disabled = false; });
  });
}

async function run(action) {
  message.textContent = "";
  try { await action(); }
  catch (error) { message.textContent = error.message; }
}

async function load() {
  board = await api("board" + (anchor ? "?day=" + encodeURIComponent(anchor) : ""));
  logout.hidden = !board.user;
  root.replaceChildren();
  if (board.user) showBoard();
  else auth();
}

async function update(action, data, notice) {
  await api(action, data);
  await load();
  message.textContent = notice;
}

function auth(signup = !!invite) {
  root.replaceChildren();
  const panel = element("div", null, "panel auth");
  const setup = board.setup;
  const path = setup ? "setup" : signup ? "signup" : "login";
  panel.append(element("h1", setup ? "Set up your household" : signup ? "Join the household" : "Sign in"));
  const form = element("form");
  if (path !== "login") field(form, "Display name", "name", "text").required = true;
  const username = field(form, "Username", "username", "text");
  username.required = true;
  username.autocomplete = "username";
  const password = field(form, "Password", "password", "password");
  password.required = true;
  password.minLength = 8;
  password.autocomplete = path === "login" ? "current-password" : "new-password";
  if (setup) field(form, "Owner setup key", "key", "password").required = true;
  submit(form, path === "login" ? "Sign in" : "Create account", async data => {
    if (path === "signup") data.key = invite;
    await api(path, data);
    invite = null;
    history.replaceState(null, "", "/");
    await load();
  });
  panel.append(form);
  if (!setup && invite) panel.append(button(signup ? "I already have an account" : "Join with this invite", () => auth(!signup)));
  root.append(panel);
}

function dateLabel(day, options) {
  return new Intl.DateTimeFormat(undefined, {...options, timeZone: "UTC"})
    .format(new Date(day + "T00:00:00Z"));
}

function offset(day, amount) {
  const value = new Date(day + "T00:00:00Z");
  value.setUTCDate(value.getUTCDate() + amount);
  return value.toISOString().slice(0, 10);
}

function personOptions() {
  return [["", "Available to claim"], ...board.members.map(member => [member.id, member.name])];
}

function showBoard() {
  const admin = !!board.chores;
  const start = board.days[0], end = board.days[6];
  root.append(element("h1", "Chore board"),
    element("p", "Signed in as " + board.user.name, "muted"));
  const toolbar = element("div", null, "row toolbar");
  const shift = async date => { anchor = date; await load(); };
  toolbar.append(button("Previous week", () => shift(offset(start, -7))),
    button("Today", () => shift(board.today)),
    button("Next week", () => shift(offset(start, 7))),
    button(mine ? "Show all chores" : "Show my chores", () => { mine = !mine; redraw(); }));
  const dateInput = field(toolbar, "Jump to date", "date", "date", anchor || board.today);
  dateInput.addEventListener("change", () => { if (dateInput.value) run(() => shift(dateInput.value)); });
  root.append(toolbar, element("h2", dateLabel(start, {month:"short",day:"numeric"}) +
    " – " + dateLabel(end, {month:"short",day:"numeric",year:"numeric"})));
  const layout = element("div", null, admin ? "layout" : "layout solo");
  const schedule = element("div");
  for (const day of board.days) {
    const section = element("section", null, day === board.today ? "day current" : "day");
    section.append(element("h2", dateLabel(day, {weekday:"long",month:"short",day:"numeric"})));
    const entries = board.items.filter(item => item.day === day &&
      (!mine || item.assignee === board.user.id));
    if (!entries.length) section.append(element("p", "No chores scheduled.", "muted"));
    for (const item of entries) section.append(choreCard(item, admin));
    schedule.append(section);
  }
  layout.append(schedule);
  if (admin) layout.append(adminPanel());
  root.append(layout);
}

function redraw() { root.replaceChildren(); showBoard(); }

function choreCard(item, admin) {
  const card = element("article", null, "card");
  const name = board.members.find(member => member.id === item.assignee)?.name;
  card.append(element("strong", item.title));
  if (item.details) card.append(element("p", item.details));
  const status = item.completed ? "Complete · " + name :
    name ? "Assigned to " + name : "Available";
  card.append(element("p", status, "status"));
  const details = {id:item.id, day:item.day};
  if (item.completed) return card;
  if (item.assignee === null)
    card.append(button("Claim", () => update("claim", details, "Chore claimed."), "primary"));
  if (item.assignee === board.user.id)
    card.append(button("Mark complete", () => update("complete", details, "Chore completed."), "primary"));
  if (admin) {
    const disclosure = element("details", null, "manage");
    disclosure.append(element("summary", "Manage assignment"));
    const form = element("form");
    field(form, "Assigned to", "assignee", "select", item.assignee ?? "", personOptions());
    submit(form, "Save assignment", data => update("assign",
      {...details, assignee:Number(data.assignee) || null}, "Assignment updated."));
    disclosure.append(form);
    card.append(disclosure);
  }
  return card;
}

function adminPanel() {
  const sidebar = element("aside");
  const invitePanel = element("section", null, "panel");
  const url = new URL("/", location.origin);
  url.hash = new URLSearchParams({invite: board.invite});
  invitePanel.append(element("h2", "Invite family"));
  const link = field(invitePanel, "Signup link", "invite", "url", url.href);
  link.readOnly = true;
  invitePanel.append(button("Copy link", async () => {
    if (navigator.clipboard) await navigator.clipboard.writeText(url.href);
    else { link.select(); document.execCommand("copy"); }
    message.textContent = "Signup link copied.";
  }));
  invitePanel.append(button("Replace signup link", () => {
      if (confirm("Replace the signup link and disable the old one?"))
        return update("renew-invite", {}, "Signup link replaced.");
    }));
  if (board.invite_expired) {
    link.value = "";
    invitePanel.querySelector("button").disabled = true;
    invitePanel.append(element("p", "Invite expired. Replace the signup link to invite someone."));
  }
  sidebar.append(invitePanel);
  const panel = element("section", null, "panel");
  panel.append(element("h2", editing ? "Edit chore" : "Create a chore"));
  const form = element("form");
  field(form, "Chore name", "title", "text", editing?.title).required = true;
  field(form, "Instructions", "details", "textarea", editing?.details);
  const repeat = field(form, "Repeat", "frequency", "select", editing?.frequency || "once",
    [["once","Once"],["daily","Daily"],["weekly","Weekly"]]);
  field(form, "Start date", "start", "date", editing?.start || anchor || board.today).required = true;
  const weekday = field(form, "Repeat on", "weekday", "select", editing?.weekday ?? 0,
    weekdays.map((name, index) => [index, name]));
  const toggle = () => { weekday.parentElement.hidden = repeat.value !== "weekly"; };
  repeat.addEventListener("change", toggle);
  toggle();
  field(form, "Default assignee", "assignee", "select", editing?.assignee ?? "", personOptions());
  submit(form, editing ? "Save changes" : "Create chore", async data => {
    await api("save", {...data, id:editing?.id ?? null, weekday:Number(data.weekday),
      assignee:Number(data.assignee) || null});
    if (!editing) anchor = data.start;
    editing = null;
    await load();
    message.textContent = "Chore saved.";
  });
  if (editing) form.append(button("Cancel edit", () => { editing = null; redraw(); }));
  panel.append(form);
  sidebar.append(panel);
  const manage = element("section", null, "panel");
  manage.append(element("h2", "Manage chores"));
  if (!board.chores.length) manage.append(element("p", "No chores created yet.", "muted"));
  for (const chore of board.chores) {
    const row = element("div", null, "card");
    row.append(element("strong", chore.title), element("p", chore.frequency, "muted"));
    const controls = element("div", null, "row");
    controls.append(button("Edit", () => {
      editing = chore; redraw(); root.querySelector('[name="title"]').focus();
    }), button("Delete", () => {
      if (confirm("Delete " + chore.title + " from the schedule?")) {
        if (editing?.id === chore.id) editing = null;
        return update("delete", {id:chore.id}, "Chore deleted.");
      }
    }, "danger"));
    row.append(controls);
    manage.append(row);
  }
  sidebar.append(manage);
  if (board.user.role === "owner") {
    const people = element("section", null, "panel");
    people.append(element("h2", "Household members"));
    for (const member of board.members) {
      const row = element("div", null, "card");
      row.append(element("p", member.name + " · " + member.role));
      if (member.role !== "owner") row.append(button(member.role === "admin" ? "Remove admin" : "Make admin",
        () => update("role", {id:member.id, role:member.role === "admin" ? "member" : "admin"},
          "Member role updated.")));
      people.append(row);
    }
    sidebar.append(people);
  }
  return sidebar;
}

logout.addEventListener("click", () => run(async () => {
  await api("logout", {}); editing = null; anchor = null; mine = false; await load();
}));

run(load);

