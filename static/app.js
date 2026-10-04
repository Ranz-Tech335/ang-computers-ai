const form = document.getElementById("form");
const input = document.getElementById("input");
const chat = document.getElementById("chat");

function addMessage(text, type) {
    const div = document.createElement("div");
    div.className = "message " + type;
    div.textContent = text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

async function sendMessage(message) {
    addMessage(message, "user");

    const response = await fetch("/chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message})
    });

    const data = await response.json();
    addMessage(data.reply, "bot");
}

form.addEventListener("submit", function(e) {
    e.preventDefault();

    const message = input.value.trim();

    if (!message) return;

    input.value = "";
    sendMessage(message);
});

function quick(message) {
    sendMessage(message);
}
