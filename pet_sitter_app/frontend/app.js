const API_BASE = "";

const SERVICE_LABELS = {
  dog_walking: "Dog walking",
  boarding: "Boarding",
  drop_in_visit: "Drop-in visit",
  daycare: "Daycare",
  house_sitting: "House sitting",
};

const state = {
  token: localStorage.getItem("pc_token") || null,
  user: JSON.parse(localStorage.getItem("pc_user") || "null"),
  view: "browse",
  pets: [],
  bookingsCache: [],
};

function setAuth(token, user) {
  state.token = token;
  state.user = user;
  if (token) {
    localStorage.setItem("pc_token", token);
    localStorage.setItem("pc_user", JSON.stringify(user));
  } else {
    localStorage.removeItem("pc_token");
    localStorage.removeItem("pc_user");
  }
}

function toast(message, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.remove("hidden");
  el.style.background = isError ? "#c62828" : "#2b2320";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 3200);
}

async function api(path, { method = "GET", body, auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && state.token) headers["Authorization"] = `Bearer ${state.token}`;
  const resp = await fetch(API_BASE + path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  const text = await resp.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (e) {
      data = null;
    }
  }
  if (!resp.ok) {
    const detail = (data && data.detail) || resp.statusText || "Request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

// ---------- Layout / nav ----------

const NAV_ITEMS = [
  { id: "browse", label: "Browse Sitters" },
  { id: "bookings", label: "My Bookings", requiresAuth: true },
  { id: "profile", label: "My Profile", requiresAuth: true },
];

function renderNav() {
  const nav = document.getElementById("nav");
  nav.innerHTML = "";
  for (const item of NAV_ITEMS) {
    if (item.requiresAuth && !state.user) continue;
    const btn = el(
      "button",
      {
        class: state.view === item.id ? "active" : "",
        onclick: () => {
          state.view = item.id;
          render();
        },
      },
      item.label
    );
    nav.appendChild(btn);
  }

  const authStatus = document.getElementById("auth-status");
  authStatus.innerHTML = "";
  if (state.user) {
    authStatus.appendChild(el("span", {}, `${state.user.full_name} (${state.user.role})`));
    authStatus.appendChild(
      el("button", {
        class: "secondary",
        onclick: () => {
          setAuth(null, null);
          state.view = "browse";
          render();
        },
      }, "Log out")
    );
  } else {
    authStatus.appendChild(
      el("button", {
        onclick: () => {
          state.view = "auth";
          render();
        },
      }, "Log in / Sign up")
    );
  }
}

function render() {
  renderNav();
  const app = document.getElementById("app");
  app.innerHTML = "";
  if (state.view === "auth") return renderAuth(app);
  if (state.view === "browse") return renderBrowse(app);
  if (state.view === "bookings") return state.user ? renderBookings(app) : renderAuth(app);
  if (state.view === "profile") return state.user ? renderProfile(app) : renderAuth(app);
  renderBrowse(app);
}

// ---------- Auth ----------

function renderAuth(app) {
  const card = el("div", { class: "card" });
  const tabs = el("div", { class: "tabs" });
  let mode = "login";

  const formHolder = el("div");

  function drawForm() {
    formHolder.innerHTML = "";
    formHolder.appendChild(mode === "login" ? loginForm() : registerForm());
    tabs.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  }

  tabs.appendChild(el("button", { "data-mode": "login", class: "active", onclick: () => { mode = "login"; drawForm(); } }, "Log in"));
  tabs.appendChild(el("button", { "data-mode": "register", onclick: () => { mode = "register"; drawForm(); } }, "Sign up"));

  card.appendChild(el("h2", {}, "Welcome to PawConnect"));
  card.appendChild(tabs);
  card.appendChild(formHolder);
  app.appendChild(card);
  drawForm();
}

function loginForm() {
  const errorEl = el("div", { class: "error" });
  const emailInput = el("input", { type: "email", required: "true", placeholder: "you@example.com" });
  const passInput = el("input", { type: "password", required: "true", placeholder: "Password" });

  const form = el("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      errorEl.textContent = "";
      try {
        const data = await api("/api/auth/login", {
          method: "POST",
          body: { email: emailInput.value, password: passInput.value },
        });
        setAuth(data.access_token, data.user);
        toast(`Welcome back, ${data.user.full_name}!`);
        state.view = "browse";
        render();
      } catch (err) {
        errorEl.textContent = err.message;
      }
    },
  });
  form.appendChild(el("label", {}, ["Email", emailInput]));
  form.appendChild(el("label", {}, ["Password", passInput]));
  form.appendChild(errorEl);
  form.appendChild(el("button", { class: "primary", type: "submit" }, "Log in"));
  return form;
}

function registerForm() {
  const errorEl = el("div", { class: "error" });
  const nameInput = el("input", { required: "true", placeholder: "Jane Doe" });
  const emailInput = el("input", { type: "email", required: "true", placeholder: "you@example.com" });
  const passInput = el("input", { type: "password", required: "true", minlength: "8", placeholder: "At least 8 characters" });
  const cityInput = el("input", { placeholder: "Austin, TX" });
  const phoneInput = el("input", { placeholder: "(optional)" });
  const roleSelect = el("select", {}, [
    el("option", { value: "owner" }, "Pet owner - I need a sitter"),
    el("option", { value: "sitter" }, "Pet sitter - I offer sitting services"),
  ]);

  const form = el("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      errorEl.textContent = "";
      try {
        const data = await api("/api/auth/register", {
          method: "POST",
          body: {
            full_name: nameInput.value,
            email: emailInput.value,
            password: passInput.value,
            role: roleSelect.value,
            city: cityInput.value || null,
            phone: phoneInput.value || null,
          },
        });
        setAuth(data.access_token, data.user);
        toast(`Welcome to PawConnect, ${data.user.full_name}!`);
        state.view = data.user.role === "sitter" ? "profile" : "browse";
        render();
      } catch (err) {
        errorEl.textContent = err.message;
      }
    },
  });
  form.appendChild(el("label", {}, ["Full name", nameInput]));
  form.appendChild(el("label", {}, ["Email", emailInput]));
  form.appendChild(el("label", {}, ["Password", passInput]));
  form.appendChild(el("label", {}, ["City", cityInput]));
  form.appendChild(el("label", {}, ["Phone", phoneInput]));
  form.appendChild(el("label", {}, ["I am a...", roleSelect]));
  form.appendChild(errorEl);
  form.appendChild(el("button", { class: "primary", type: "submit" }, "Create account"));
  return form;
}

// ---------- Browse sitters ----------

async function renderBrowse(app) {
  const filterCard = el("div", { class: "card" });
  filterCard.appendChild(el("h2", {}, "Find a pet sitter"));

  const cityInput = el("input", { placeholder: "City" });
  const petTypeInput = el("input", { placeholder: "Pet type (dog, cat, ...)" });
  const maxRateInput = el("input", { type: "number", min: "0", placeholder: "Max hourly rate" });
  const serviceSelect = el("select", {}, [
    el("option", { value: "" }, "Any service"),
    ...Object.entries(SERVICE_LABELS).map(([v, label]) => el("option", { value: v }, label)),
  ]);

  const resultsHolder = el("div", { class: "grid" }, [el("p", { class: "muted" }, "Loading sitters...")]);

  async function search() {
    resultsHolder.innerHTML = "";
    const params = new URLSearchParams();
    if (cityInput.value) params.set("city", cityInput.value);
    if (petTypeInput.value) params.set("pet_type", petTypeInput.value);
    if (maxRateInput.value) params.set("max_rate", maxRateInput.value);
    if (serviceSelect.value) params.set("service", serviceSelect.value);
    try {
      const sitters = await api(`/api/sitters?${params.toString()}`);
      if (!sitters.length) {
        resultsHolder.appendChild(el("p", { class: "muted" }, "No sitters match those filters yet."));
        return;
      }
      sitters.forEach((s) => resultsHolder.appendChild(sitterCard(s)));
    } catch (err) {
      resultsHolder.appendChild(el("p", { class: "error" }, err.message));
    }
  }

  const filterForm = el("form", { onsubmit: (e) => { e.preventDefault(); search(); } });
  filterForm.appendChild(el("div", { class: "row" }, [
    el("label", {}, ["City", cityInput]),
    el("label", {}, ["Pet type", petTypeInput]),
  ]));
  filterForm.appendChild(el("div", { class: "row" }, [
    el("label", {}, ["Service", serviceSelect]),
    el("label", {}, ["Max hourly rate ($)", maxRateInput]),
  ]));
  filterForm.appendChild(el("button", { class: "primary", type: "submit" }, "Search"));
  filterCard.appendChild(filterForm);

  app.appendChild(filterCard);
  app.appendChild(resultsHolder);
  search();
}

function sitterCard(sitter) {
  const card = el("div", { class: "card sitter-card" });
  card.appendChild(el("h3", {}, sitter.user.full_name));
  card.appendChild(el("div", { class: "muted" }, sitter.city || "Location not set"));
  if (sitter.review_count > 0) {
    card.appendChild(el("div", { class: "rating" }, `★ ${sitter.average_rating} (${sitter.review_count} review${sitter.review_count === 1 ? "" : "s"})`));
  } else {
    card.appendChild(el("div", { class: "muted" }, "No reviews yet"));
  }
  card.appendChild(el("p", {}, sitter.bio || "No bio provided."));
  card.appendChild(el("p", {}, [
    el("strong", {}, `$${sitter.hourly_rate}/hr`),
    ` · ${sitter.years_experience} yr experience`,
  ]));
  if (sitter.services.length) {
    card.appendChild(el("p", { class: "muted" }, "Services: " + sitter.services.map((s) => SERVICE_LABELS[s] || s).join(", ")));
  }
  if (sitter.accepted_pet_types.length) {
    card.appendChild(el("p", { class: "muted" }, "Pets: " + sitter.accepted_pet_types.join(", ")));
  }

  if (state.user && state.user.role === "owner") {
    card.appendChild(bookingRequestForm(sitter));
  } else if (!state.user) {
    card.appendChild(el("p", { class: "muted" }, "Log in as a pet owner to request a booking."));
  }
  return card;
}

function bookingRequestForm(sitter) {
  const errorEl = el("div", { class: "error" });
  const serviceSelect = el("select", {}, Object.entries(SERVICE_LABELS).map(([v, label]) => el("option", { value: v }, label)));
  const petSelect = el("select", {}, [el("option", { value: "" }, "No specific pet")]);
  const startInput = el("input", { type: "date", required: "true" });
  const endInput = el("input", { type: "date", required: "true" });
  const notesInput = el("textarea", { placeholder: "Anything the sitter should know?" });

  api("/api/pets", { auth: true }).then((pets) => {
    pets.forEach((p) => petSelect.appendChild(el("option", { value: p.id }, `${p.name} (${p.species})`)));
  }).catch(() => {});

  const form = el("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      errorEl.textContent = "";
      try {
        await api("/api/bookings", {
          method: "POST",
          auth: true,
          body: {
            sitter_id: sitter.user.id,
            pet_id: petSelect.value || null,
            service_type: serviceSelect.value,
            start_date: startInput.value,
            end_date: endInput.value,
            notes: notesInput.value,
          },
        });
        toast(`Booking request sent to ${sitter.user.full_name}!`);
        form.reset();
      } catch (err) {
        errorEl.textContent = err.message;
      }
    },
  });
  form.appendChild(el("div", { class: "row" }, [
    el("label", {}, ["Service", serviceSelect]),
    el("label", {}, ["Pet", petSelect]),
  ]));
  form.appendChild(el("div", { class: "row" }, [
    el("label", {}, ["Start date", startInput]),
    el("label", {}, ["End date", endInput]),
  ]));
  form.appendChild(el("label", {}, ["Notes", notesInput]));
  form.appendChild(errorEl);
  form.appendChild(el("button", { class: "primary", type: "submit" }, "Request booking"));
  return form;
}

// ---------- My Bookings ----------

async function renderBookings(app) {
  app.appendChild(el("h2", {}, "My bookings"));
  const holder = el("div");
  app.appendChild(holder);
  try {
    const bookings = await api("/api/bookings", { auth: true });
    state.bookingsCache = bookings;
    if (!bookings.length) {
      holder.appendChild(el("p", { class: "muted" }, "No bookings yet."));
      return;
    }
    bookings.forEach((b) => holder.appendChild(bookingCard(b)));
  } catch (err) {
    holder.appendChild(el("p", { class: "error" }, err.message));
  }
}

function bookingCard(booking) {
  const iAmSitter = state.user.id === booking.sitter.id;
  const counterparty = iAmSitter ? booking.owner : booking.sitter;
  const card = el("div", { class: "card" });
  card.appendChild(el("h3", {}, [
    `${SERVICE_LABELS[booking.service_type] || booking.service_type} with ${counterparty.full_name} `,
    el("span", { class: `badge ${booking.status}` }, booking.status),
  ]));
  card.appendChild(el("p", { class: "muted" }, `${booking.start_date} → ${booking.end_date}`));
  if (booking.pet) card.appendChild(el("p", {}, `Pet: ${booking.pet.name} (${booking.pet.species})`));
  if (booking.notes) card.appendChild(el("p", {}, booking.notes));

  const actions = el("div");
  const errorEl = el("div", { class: "error" });

  async function transition(newStatus) {
    errorEl.textContent = "";
    try {
      await api(`/api/bookings/${booking.id}`, { method: "PATCH", auth: true, body: { status: newStatus } });
      toast("Booking updated.");
      render();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  }

  if (booking.status === "pending" && iAmSitter) {
    actions.appendChild(el("button", { class: "small accept", onclick: () => transition("accepted") }, "Accept"));
    actions.appendChild(el("button", { class: "small decline", onclick: () => transition("declined") }, "Decline"));
  }
  if (booking.status === "pending" && !iAmSitter) {
    actions.appendChild(el("button", { class: "small cancel", onclick: () => transition("cancelled") }, "Cancel request"));
  }
  if (booking.status === "accepted") {
    actions.appendChild(el("button", { class: "small cancel", onclick: () => transition("cancelled") }, "Cancel"));
    if (iAmSitter) {
      actions.appendChild(el("button", { class: "small accept", onclick: () => transition("completed") }, "Mark completed"));
    }
  }
  card.appendChild(actions);
  card.appendChild(errorEl);

  if (booking.status === "completed" && !iAmSitter) {
    card.appendChild(reviewSection(booking));
  }

  card.appendChild(messagesSection(booking));
  return card;
}

function reviewSection(booking) {
  const holder = el("div", { class: "card", style: "background:#faf7f2" });
  const errorEl = el("div", { class: "error" });
  const ratingSelect = el("select", {}, [1, 2, 3, 4, 5].map((n) => el("option", { value: n, selected: n === 5 ? "true" : null }, `${n} star${n === 1 ? "" : "s"}`)));
  const commentInput = el("textarea", { placeholder: "How did it go?" });
  const form = el("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      errorEl.textContent = "";
      try {
        await api(`/api/bookings/${booking.id}/review`, {
          method: "POST",
          auth: true,
          body: { rating: Number(ratingSelect.value), comment: commentInput.value },
        });
        toast("Thanks for the review!");
        holder.innerHTML = "";
        holder.appendChild(el("p", { class: "muted" }, "Review submitted."));
      } catch (err) {
        errorEl.textContent = err.message;
      }
    },
  });
  form.appendChild(el("label", {}, ["Rate your sitter", ratingSelect]));
  form.appendChild(el("label", {}, ["Comment", commentInput]));
  form.appendChild(errorEl);
  form.appendChild(el("button", { class: "primary", type: "submit" }, "Leave a review"));
  holder.appendChild(el("h4", {}, "Leave a review"));
  holder.appendChild(form);
  return holder;
}

function messagesSection(booking) {
  const holder = el("div");
  const toggleBtn = el("button", { class: "small" }, "Show messages");
  const messagesBox = el("div", { class: "messages hidden" });
  const inputForm = el("form", { class: "row hidden" });
  const bodyInput = el("input", { placeholder: "Write a message..." });
  const sendBtn = el("button", { class: "primary", type: "submit" }, "Send");
  inputForm.appendChild(bodyInput);
  inputForm.appendChild(sendBtn);

  let open = false;

  async function loadMessages() {
    messagesBox.innerHTML = "";
    try {
      const messages = await api(`/api/bookings/${booking.id}/messages`, { auth: true });
      if (!messages.length) {
        messagesBox.appendChild(el("p", { class: "muted" }, "No messages yet."));
      }
      messages.forEach((m) => {
        messagesBox.appendChild(
          el("div", { class: `message ${m.sender_id === state.user.id ? "mine" : ""}` }, m.body)
        );
      });
      messagesBox.scrollTop = messagesBox.scrollHeight;
    } catch (err) {
      messagesBox.appendChild(el("p", { class: "error" }, err.message));
    }
  }

  toggleBtn.addEventListener("click", () => {
    open = !open;
    toggleBtn.textContent = open ? "Hide messages" : "Show messages";
    messagesBox.classList.toggle("hidden", !open);
    inputForm.classList.toggle("hidden", !open);
    if (open) loadMessages();
  });

  inputForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!bodyInput.value.trim()) return;
    try {
      await api(`/api/bookings/${booking.id}/messages`, { method: "POST", auth: true, body: { body: bodyInput.value } });
      bodyInput.value = "";
      loadMessages();
    } catch (err) {
      toast(err.message, true);
    }
  });

  holder.appendChild(toggleBtn);
  holder.appendChild(messagesBox);
  holder.appendChild(inputForm);
  return holder;
}

// ---------- Profile ----------

async function renderProfile(app) {
  if (state.user.role === "sitter") return renderSitterProfile(app);
  return renderOwnerProfile(app);
}

async function renderSitterProfile(app) {
  app.appendChild(el("h2", {}, "My sitter profile"));
  const card = el("div", { class: "card" });
  const errorEl = el("div", { class: "error" });

  let profile;
  try {
    profile = await api(`/api/sitters/${state.user.id}`);
  } catch (err) {
    profile = { bio: "", hourly_rate: 0, years_experience: 0, services: [], accepted_pet_types: [], city: state.user.city };
  }

  const bioInput = el("textarea", { placeholder: "Tell owners about yourself" }, []);
  bioInput.value = profile.bio || "";
  const rateInput = el("input", { type: "number", min: "0", step: "0.5" });
  rateInput.value = profile.hourly_rate || 0;
  const experienceInput = el("input", { type: "number", min: "0" });
  experienceInput.value = profile.years_experience || 0;
  const cityInput = el("input", {});
  cityInput.value = profile.city || "";
  const petTypesInput = el("input", { placeholder: "dog, cat, bird" });
  petTypesInput.value = (profile.accepted_pet_types || []).join(", ");

  const serviceChecks = {};
  const serviceGroup = el("div", { class: "checkbox-group" });
  Object.entries(SERVICE_LABELS).forEach(([value, label]) => {
    const checkbox = el("input", { type: "checkbox", value });
    checkbox.checked = (profile.services || []).includes(value);
    serviceChecks[value] = checkbox;
    serviceGroup.appendChild(el("label", {}, [checkbox, label]));
  });

  const form = el("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      errorEl.textContent = "";
      try {
        await api("/api/sitters/me", {
          method: "PUT",
          auth: true,
          body: {
            bio: bioInput.value,
            hourly_rate: Number(rateInput.value),
            years_experience: Number(experienceInput.value),
            city: cityInput.value,
            services: Object.entries(serviceChecks).filter(([, cb]) => cb.checked).map(([v]) => v),
            accepted_pet_types: petTypesInput.value.split(",").map((s) => s.trim()).filter(Boolean),
          },
        });
        toast("Profile saved.");
      } catch (err) {
        errorEl.textContent = err.message;
      }
    },
  });

  form.appendChild(el("label", {}, ["Bio", bioInput]));
  form.appendChild(el("div", { class: "row" }, [
    el("label", {}, ["Hourly rate ($)", rateInput]),
    el("label", {}, ["Years of experience", experienceInput]),
  ]));
  form.appendChild(el("label", {}, ["City", cityInput]));
  form.appendChild(el("label", {}, ["Pet types you accept (comma-separated)", petTypesInput]));
  form.appendChild(el("label", {}, ["Services offered"]));
  form.appendChild(serviceGroup);
  form.appendChild(errorEl);
  form.appendChild(el("button", { class: "primary", type: "submit" }, "Save profile"));

  card.appendChild(form);
  app.appendChild(card);
}

async function renderOwnerProfile(app) {
  app.appendChild(el("h2", {}, "My pets"));
  const listCard = el("div", { class: "card" });
  const petsHolder = el("div", { class: "grid" });
  listCard.appendChild(petsHolder);
  app.appendChild(listCard);

  async function loadPets() {
    petsHolder.innerHTML = "";
    try {
      const pets = await api("/api/pets", { auth: true });
      if (!pets.length) petsHolder.appendChild(el("p", { class: "muted" }, "No pets added yet."));
      pets.forEach((pet) => {
        const petCard = el("div", { class: "card" });
        petCard.appendChild(el("h4", {}, `${pet.name} (${pet.species})`));
        if (pet.breed) petCard.appendChild(el("p", { class: "muted" }, pet.breed));
        if (pet.notes) petCard.appendChild(el("p", {}, pet.notes));
        petCard.appendChild(
          el("button", {
            class: "small cancel",
            onclick: async () => {
              await api(`/api/pets/${pet.id}`, { method: "DELETE", auth: true });
              loadPets();
            },
          }, "Remove")
        );
        petsHolder.appendChild(petCard);
      });
    } catch (err) {
      petsHolder.appendChild(el("p", { class: "error" }, err.message));
    }
  }

  const addCard = el("div", { class: "card" });
  addCard.appendChild(el("h3", {}, "Add a pet"));
  const errorEl = el("div", { class: "error" });
  const nameInput = el("input", { required: "true", placeholder: "Pet name" });
  const speciesInput = el("input", { required: "true", placeholder: "dog, cat, ..." });
  const breedInput = el("input", { placeholder: "Breed (optional)" });
  const notesInput = el("textarea", { placeholder: "Feeding schedule, medications, quirks..." });
  const addForm = el("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      errorEl.textContent = "";
      try {
        await api("/api/pets", {
          method: "POST",
          auth: true,
          body: { name: nameInput.value, species: speciesInput.value, breed: breedInput.value || null, notes: notesInput.value },
        });
        addForm.reset();
        toast("Pet added.");
        loadPets();
      } catch (err) {
        errorEl.textContent = err.message;
      }
    },
  });
  addForm.appendChild(el("div", { class: "row" }, [
    el("label", {}, ["Name", nameInput]),
    el("label", {}, ["Species", speciesInput]),
  ]));
  addForm.appendChild(el("label", {}, ["Breed", breedInput]));
  addForm.appendChild(el("label", {}, ["Notes", notesInput]));
  addForm.appendChild(errorEl);
  addForm.appendChild(el("button", { class: "primary", type: "submit" }, "Add pet"));
  addCard.appendChild(addForm);
  app.appendChild(addCard);

  loadPets();
}

render();
