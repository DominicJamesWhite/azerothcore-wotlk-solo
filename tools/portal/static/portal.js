/* Alonecraft account portal.
 *
 * Client-side checks here are UX only -- accounts.py re-validates everything.
 */

const FORMS = {
  "form-register": { url: "/api/register", success: "Account created. Log in with it in the game client." },
  "form-password": { url: "/api/change-password", success: "Password changed." },
  "form-email": { url: "/api/change-email", success: "Email changed." },
};

for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => {
    for (const other of document.querySelectorAll(".tab")) {
      other.classList.toggle("is-active", other === tab);
    }
    for (const panel of document.querySelectorAll("main .card")) {
      panel.hidden = panel.id !== `panel-${tab.dataset.panel}`;
    }
  });
}

for (const [id, config] of Object.entries(FORMS)) {
  const form = document.getElementById(id);
  const status = form.querySelector(".status");
  const submit = form.querySelector("button[type=submit]");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.textContent = "Working…";
    status.className = "status";
    submit.disabled = true;

    const payload = Object.fromEntries(new FormData(form).entries());

    try {
      const response = await fetch(config.url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json();

      if (body.ok) {
        status.textContent = config.success;
        status.className = "status is-ok";
        form.reset();
        showRealmHint(body.realm_address);
      } else {
        status.textContent = body.error || "Something went wrong.";
        status.className = "status is-error";
      }
    } catch (err) {
      status.textContent = "Could not reach the portal. Is it still running?";
      status.className = "status is-error";
    } finally {
      submit.disabled = false;
    }
  });
}

/* After a successful registration, tell the player what to put in
 * realmlist.wtf -- it is the very next thing they need and the most common
 * reason a working new account still cannot connect. */
function showRealmHint(address) {
  if (!address) return;
  const hint = document.getElementById("realm-hint");
  // Built from nodes rather than innerHTML: `address` comes from the realmlist
  // table, and a template string here would be an injection point the day
  // anything else can write to it.
  const file = document.createElement("code");
  file.textContent = "realmlist.wtf";
  const line = document.createElement("code");
  line.textContent = `set realmlist ${address}`;

  hint.replaceChildren(
    "Before you can log in, open ", file,
    " in your WoW folder and make it read ", line, ".",
  );
  hint.hidden = false;
  hint.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
