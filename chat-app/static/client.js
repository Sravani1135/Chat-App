const socket = io();
const form = document.getElementById('chat-form');
const input = document.getElementById('msg');
let SELECTED_USER_ID = null;

let currentChatUserId = null;

const messages = document.getElementById('messages');
form.addEventListener('submit', function(e) {
  e.preventDefault();
  if (input.value.trim() && SELECTED_USER_ID) {
    const msg = {
      name: USER_NAME,
      sender_id: USER_ID,
      receiver_id: SELECTED_USER_ID,
      text: input.value,
      time: new Date().toLocaleTimeString()
    };

    socket.emit('chat message', msg);
    socket.emit('join', USER_ID);

    // Show message immediately
    const li = document.createElement('li');
    li.className = 'message sent';
    li.innerHTML = `<strong>${USER_NAME}</strong>: ${msg.text} <span class="time">${msg.time}</span>`;
    messages.appendChild(li);
    messages.scrollTop = messages.scrollHeight;

    input.value = '';
  }
});

function openChat(receiverId, receiverName) {
  SELECTED_USER_ID = receiverId;
  currentChatUserId = receiverId;

  // highlight selected user
  document.querySelectorAll('.user-item').forEach(el => el.classList.remove('active-user'));
  const activeLi = document.getElementById(`user-${receiverId}`);
  if (activeLi) activeLi.classList.add('active-user');

  messages.innerHTML = ''; // clear chat

  fetch(`/messages/${receiverId}`)
    .then(res => res.json())
    .then(data => {
      data.forEach(msg => {
        const li = document.createElement('li');
        li.className = msg.name === USER_NAME ? 'message sent' : 'message received';
        li.innerHTML = `<strong>${msg.name}:</strong> ${msg.text} <span class="time">${msg.time}</span>`;
        messages.appendChild(li);
      });
      messages.scrollTop = messages.scrollHeight;
    });
}

socket.on('refresh contacts', () => {
  console.log("Refreshing contacts...");
  window.location.reload(); // or call a function to re-render the contact list
});



socket.on('chat message', function(data) {
    console.log("Received on client:", data);
    console.log("Current chat user:", currentChatUserId);
    console.log("Logged in user:", USER_ID);

const isRelevant = 
  (data.sender_id === USER_ID && data.receiver_id === currentChatUserId) || 
  (data.sender_id === currentChatUserId && data.receiver_id === USER_ID);

    if (isRelevant) {
        const li = document.createElement('li');
        li.className = data.name === USER_NAME ? 'message sent' : 'message received';
        li.innerHTML = `<strong>${data.name}</strong>: ${data.text} <span class="time">${data.time}</span>`;
        messages.appendChild(li);

        messages.scrollTop = messages.scrollHeight;
    } else {
        console.log("Message ignored: not for this chat window.");
    }
});



const chatBox = document.getElementById('messages');
chatBox.scrollTop = chatBox.scrollHeight;

console.log("currentChatUserId:", currentChatUserId);

