// script.js

var interval;
let threadId = Date.now().toString(); // Generates a new threadId each time the page loads

// Variables to store user's location
let userLatitude = null;
let userLongitude = null;



var linkTargetBlankExtension = function () {
  return [
    {
      type: "html",
      regex: /<a href="(.+?)">/g,
      replace: '<a href="$1" target="_blank">',
    },
  ];
};

// Function to get user's location
function getUserLocation() {
  const locationStatus = document.getElementById('locationStatus');
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      position => {
        userLatitude = position.coords.latitude;
        userLongitude = position.coords.longitude;
        console.log(`User's location: Latitude ${userLatitude}, Longitude ${userLongitude}`);
        if (locationStatus) {
          locationStatus.textContent = '📍 Location acquired.';
        }
      },
      error => {
        console.error('Error getting location:', error);
        if (locationStatus) {
          locationStatus.textContent = '⚠️ Unable to get location.';
        }
      }
    );
  } else {
    console.error('Geolocation is not supported by this browser.');
    if (locationStatus) {
      locationStatus.textContent = '⚠️ Geolocation is not supported by your browser.';
    }
  }
}

// Function to display messages in the chat
function displayMessage(sender, message) {
  const chat = document.getElementById("chat");
  const messageDiv = document.createElement("div");
  messageDiv.className = `bubble ${sender}`;
  var converter = new showdown.Converter();
  converter.addExtension(linkTargetBlankExtension);
  const messageHtml = converter.makeHtml(message);
  messageDiv.innerHTML = messageHtml;
  chat.appendChild(messageDiv);
  chat.scrollTop = chat.scrollHeight; // Scroll to bottom
}

// Function to fetch and display the welcome message
function fetchWelcomeMessage() {
  fetch('/welcome')
    .then(response => response.json())
    .then(data => {
      displayMessage('left', data.bot_reply);
    })
    .catch(error => {
      console.error('Error fetching welcome message:', error);
    });
}

// Call getUserLocation and fetchWelcomeMessage when the page loads
window.onload = function() {
  getUserLocation();
  fetchWelcomeMessage();
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
    displayMessage('right', message);
    messageInput.value = "";
    document.getElementById("sendMessage").disabled = true;

    // Prepare request body with location data
    const requestBody = {
      threadId: threadId || "initial_thread",
      message: message,
      latitude: userLatitude,
      longitude: userLongitude
    };

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
  chat.scrollTop = chat.scrollHeight; // Scroll to bottom
  sendMessageButton.disabled = true;

  // Prepare request body with location data
  const requestBody = {
    threadId: threadId,
    message: message,
    latitude: userLatitude,
    longitude: userLongitude
  };

  // Make sure the fetch is using "/chat_with_file"
  fetch("/chat_with_file", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  })
    .then((response) => response.json())
    .then((data) => {
      console.log(data);
      // Replace loader with the bot's response
      var converter = new showdown.Converter();
      converter.addExtension(linkTargetBlankExtension);
      const botReplyHtml = converter.makeHtml(data.bot_reply);
      loaderDiv.innerHTML = botReplyHtml;
      sendMessageButton.disabled = false;
      chat.scrollTop = chat.scrollHeight; // Scroll to bottom
    })
    .catch((error) => {
      console.error("There has been a problem with your fetch operation:", error);
      loaderDiv.remove();
      sendMessageButton.disabled = false;
    });
}

function continueChat(message) {
  displayMessage('right', message);

  // Prepare request body with location data
  const requestBody = {
    threadId: threadId,
    message: message,
    latitude: userLatitude,
    longitude: userLongitude
  };

  fetch("/chat_with_file", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  })
    .then((response) => response.json())
    .then((data) => {
      runAssistant(threadId, message);  // Use the current message for the assistant response
    });

  document.getElementById("messageInput").value = "";
  document.getElementById("sendMessage").disabled = true;
}
