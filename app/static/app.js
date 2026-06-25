const chat = document.getElementById("chat");
const form = document.getElementById("form");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");

// Historique de conversation envoyé au backend (rôles user/assistant).
const history = [];

function addMessage(role, text, opts = {}) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}` + (opts.error ? " error" : "");
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (opts.typing) bubble.classList.add("typing");
  
  if (role === "assistant" && !opts.typing) {
    bubble.innerHTML = marked.parse(text);
  } else {
    bubble.textContent = text;
  }
  
  wrap.appendChild(bubble);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return bubble;
}

async function sendMessage(text) {
  addMessage("user", text);
  history.push({ role: "user", content: text });

  const typing = addMessage("assistant", "Analyse des modèles en cours…", {
    typing: true,
  });
  sendBtn.disabled = true;
  input.disabled = true;

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history }),
    });

    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || `Erreur ${resp.status}`);
    }

    typing.parentElement.remove();
    addMessage("assistant", data.answer);
    history.push({ role: "assistant", content: data.answer });
  } catch (err) {
    typing.parentElement.remove();
    addMessage("assistant", `⚠️ ${err.message}`, { error: true });
  } finally {
    sendBtn.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendMessage(text);
});
