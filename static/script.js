var interval;
let threadId = null;

var linkTargetBlankExtension = function () {
  return [
    {
      type: "html",
      regex: /<a href="(.+?)">/g,
      replace: '<a href="$1" target="_blank">',
    },
  ];
};

function updateButtonState() {
  document.getElementById("sendMessage").disabled =
    document.getElementById("messageInput").value.trim() === "";
}

document.addEventListener("DOMContentLoaded", function () {
  const messageInput = document.getElementById("messageInput");
  messageInput.addEventListener("input", updateButtonState);
  updateButtonState();

  messageInput.addEventListener("keypress", function (e) {
    if (e.key === "Enter") {
      document.getElementById("sendMessage").click();
    }
  });

  document.getElementById("sendMessage").addEventListener("click", function () {
    const message = messageInput.value;
    if (message.trim() === "") {
      return;
    }

    // Add the user message to the chat
    var chat = document.getElementById("chat");
    chat.innerHTML += `<div class="bubble right">${message}</div>`;
    messageInput.value = "";
    document.getElementById("sendMessage").disabled = true;

    // Prepare request body
    const requestBody = { threadId: threadId || "initial_thread", message: message };

    console.log("Sending request with:", requestBody);  // Log the request body

    // Make sure the fetch is using "/chat_with_file"
    fetch("/chat_with_file", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(requestBody),
    })
      .then((response) => {
        console.log("Response status:", response.status);  // Log the response status
        return response.json();
      })
      .then((data) => {
        console.log("Received response:", data);  // Log the response data
        threadId = data.threadId;  // Assign the threadId returned from the server
        runAssistant(threadId, message);  // Pass the message to runAssistant
      })
      .catch((error) => {
        console.error("There has been a problem with your fetch operation:", error);
      });
  });
});

function runAssistant(threadId, message) {
  const chat = document.getElementById("chat");
  const sendMessageButton = document.getElementById("sendMessage");
  const loaderDiv = document.createElement("div");
  loaderDiv.className = "bubble left";
  loaderDiv.innerHTML = `<div class="loader"></div>`;
  chat.appendChild(loaderDiv);
  sendMessageButton.disabled = true;

  // Make sure the fetch is using "/chat_with_file"
  fetch("/chat_with_file", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ threadId: threadId, message: message }),
  })
    .then((response) => response.json())
    .then((data) => {
      console.log(data);
      var converter = new showdown.Converter();
      converter.addExtension(linkTargetBlankExtension);
      
      // Use Markdown format for a more appealing reply
      const botReplyHtml = converter.makeHtml(data.bot_reply);

      // Display formatted HTML
      loaderDiv.innerHTML = botReplyHtml;
    })
    .catch((error) => {
      console.error("There has been a problem with your fetch operation:", error);
      loaderDiv.remove();
    });
}

function continueChat(message) {
  var chat = document.getElementById("chat");
  chat.innerHTML += `<div class="bubble right">${message}</div>`;

  fetch("/chat_with_file", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ threadId: threadId, message: message }),
  })
    .then((response) => response.json())
    .then((data) => {
      runAssistant(threadId, message);  // Use the current message for the assistant response
    });

  document.getElementById("messageInput").value = "";
  document.getElementById("sendMessage").disabled = true;
}
