import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify
from flask_socketio import SocketIO, emit, join_room
from pymongo import MongoClient
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
import base64
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Flask & SocketIO setup
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# MongoDB setup
client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("DB_NAME", "chat_app")]
users_col = db["users"]
messages_col = db["messages"]

# -------------------- ROUTES --------------------

@app.route('/', methods=['GET'])
def login_page():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form['pemail'].strip().lower()
    password = request.form['ppwd']

    user = users_col.find_one({'email': email})
    if user and check_password_hash(user['password'], password):
        session['user_id'] = str(user['_id'])
        flash('Logged in successfully!', 'success')
        return redirect('/chat')
    else:
        flash('Invalid email or password', 'danger')
        return redirect(url_for('login_page'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['uname']
        email = request.form['uemail'].strip().lower()
        password = request.form['upwd']
        hashed_pw = generate_password_hash(password)  # ✅ Hash password here

        desc = request.form['udesc']
        pic = request.files['upic']


        if users_col.find_one({'email': email}):
            flash('Email already registered!', 'danger')
            return redirect(url_for('register'))

        profile_pic = base64.b64encode(pic.read()).decode('utf-8') if pic else ''

        user = {
    'name': name,
    'email': email,
    'password': hashed_pw,
    'description': desc,
    'profile_pic': profile_pic,
    "contacts": []
  # NEW: holds ObjectId references to added users
}

        user_id = users_col.insert_one(user).inserted_id
        session['user_id'] = str(user_id)
        flash('Registration successful!', 'success')
        return redirect('/chat')

    return render_template('register.html')


@app.route('/chat')
def chat():
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/')
    
    user = users_col.find_one({'_id': ObjectId(user_id)})
    contact_ids = user.get('contacts', [])
    contacts = list(users_col.find({'_id': {'$in': contact_ids}}))

    return render_template('chat.html', user=user, users=contacts)

@app.route('/add-contact/<email>')
def add_contact(email):
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/')
    
    current_user = users_col.find_one({'_id': ObjectId(user_id)})
    other_user = users_col.find_one({'email': email})

    if not other_user:
        flash("User not found", "danger")
        return redirect('/chat')

    # Avoid duplicates
    if ObjectId(other_user['_id']) not in current_user.get('contacts', []):
        users_col.update_one(
            {'_id': ObjectId(user_id)},
            {'$push': {'contacts': ObjectId(other_user['_id'])}}
        )
    
    return redirect('/chat')
   
@app.route('/private-chat/<email>')
def private_chat(email):
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/')

    current_user = users_col.find_one({'_id': ObjectId(user_id)})
    other_user = users_col.find_one({'email': email})

    if not other_user:
        flash("User not found", "danger")
        return redirect('/chat')

    # Check if other_user is in current_user's contacts
    if 'contacts' not in current_user or other_user['_id'] not in current_user['contacts']:
        flash("User not in your contacts!", "warning")
        return redirect('/chat')

    # Proceed to show chat
    messages = list(messages_col.find({
        '$or': [
            {'sender_id': str(current_user['_id']), 'receiver_id': str(other_user['_id'])},
            {'sender_id': str(other_user['_id']), 'receiver_id': str(current_user['_id'])}
        ]
    }))

    contacts = list(users_col.find({'_id': {'$in': current_user['contacts']}}))

    return render_template('chat.html', user=current_user, other_user=other_user, users=contacts, messages=messages)



@app.route('/messages/<receiver_id>')
def get_messages(receiver_id):
    user_id = session.get('user_id')
    chats = messages_col.find({
        '$or': [
            {'sender_id': user_id, 'receiver_id': receiver_id},
            {'sender_id': receiver_id, 'receiver_id': user_id}
        ]
    })
    return jsonify([{
        'name': chat['name'],
        'text': chat['text'],
        'time': chat['time'],
        'sender_id': chat['sender_id'],
        'receiver_id': chat['receiver_id']
    } for chat in chats])


# -------------------- SOCKET.IO --------------------

@socketio.on('chat message')
def handle_message(data):
    print("Received message:", data)

    data['sender_id'] = str(data['sender_id'])
    data['receiver_id'] = str(data['receiver_id'])
    room = data.get('room') or data['receiver_id']

    # Store the message
    messages_col.insert_one({
        'sender_id': data['sender_id'],
        'receiver_id': data['receiver_id'],
        'name': data['name'],
        'text': data['text'],
        'time': data['time'],
        'room': room
    })

    # Auto-add sender to receiver's contacts
    sender_id = ObjectId(data['sender_id'])
    receiver_id = ObjectId(data['receiver_id'])

# 🔥 Auto-add sender to receiver's contacts if not already
    receiver = users_col.find_one({'_id': receiver_id})
    sender = users_col.find_one({'_id': sender_id})

    if sender_id not in receiver.get('contacts', []):
        users_col.update_one(
            {'_id': receiver_id},
            {'$push': {'contacts': sender_id}}
        )

    if receiver_id not in sender.get('contacts', []):
        users_col.update_one(
            {'_id': sender_id},
            {'$push': {'contacts': receiver_id}}
        )


    # Notify the receiver to update contact list if needed
    emit('chat message', data, room=room, include_self=True)
    # Let the receiver refresh UI (optional event)
    socketio.emit('refresh contacts', room=data['receiver_id'])


# -------------------- UTILITY --------------------

def get_private_room(user1, user2):
    ids = sorted([str(user1['_id']), str(user2['_id'])])
    return f"private_{ids[0]}_{ids[1]}"


# -------------------- MAIN --------------------

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

