# Local-Messaging-App
It uses python flask to create a server which san be used to communicate multiple devices connected to the same serevr.
It provides three group ans indivisual messsage service
- `admin`
- `staff`
- `client`
## Required modules
- Flask module
`pip install Flask`
- Flask-socket.io module
`pip install flask-socketio`
Make sure you have installed the following modules before executing the `app.py` file
## `app.py` File
```python
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__, static_url_path='/static')
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

users = {}

admin_list = []
staff_list = []
client_list = []

@app.route('/admin/<username>')
def admin_page(username):
    return render_template('admin.html', username=username, user_type='admin')

@app.route('/staff/<username>')
def staff_page(username):
    return render_template('staff.html', username=username, user_type='staff')

@app.route('/client/<username>')
def client_page(username):
    return render_template('client.html', username=username, user_type='client')

@socketio.on('connect')
def connect():
    # scrap the basic details
    user_ip = request.remote_addr
    user_sid = request.sid

    # save user information
    users[user_sid] = {'IP':user_ip, 'Connected_at':datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'Varification':'NOT VERIFIED', 'user_type':'NULL'}

    # display connection successful message
    print(f'User connected [NOT VERIFIED] {user_ip}\t{user_sid}')

    for admin in admin_list + staff_list + client_list:
        emit('update_web_app', {'message':'USER CONNECTED', 'users':users}, room=admin)

@socketio.on('verify_user')
def verify_user(data):
    # scrap the basic details 
    user_ip = request.remote_addr
    user_sid = request.sid
    user_type = data['user_type']
    user_name = data['user_name']

    users[user_sid]['user_type'] = user_type
    users[user_sid]['user_name'] = user_name

    # filter the user_type
    if user_type == 'admin':
        # add user into into group
        admin_list.append(user_sid)
        # display user connection verification successful
        print(f'Connected user [VERIFIED] {user_ip}\t{user_sid}')
        users[user_sid]['Varification'] = 'VERIFIED'
    elif user_type == 'staff':
        staff_list.append(user_sid)
        print(f'Connected user [VERIFIED] {user_ip}\t{user_sid}')
        users[user_sid]['Varification'] = 'VERIFIED'
    elif user_type == 'client':
        client_list.append(user_sid)
        print(f'Connected user [VERIFIED] {user_ip}\t{user_sid}')
        users[user_sid]['Varification'] = 'VERIFIED'
    else:
        print(f'Connected user [NOT AUTHORISED] {user_ip}\t{user_sid}')
        users[user_sid]['Varification'] = 'NOT AUTHORISED'

    emit('update_web_app', {'message':'USER CONNECTED', 'users':users}, broadcast=True)
'''
    for admin in admin_list:
        emit('update_web_app', {'message':'USER CONNECTED', 'users':users}, room=admin)
'''
@socketio.on('disconnect')
def disconnect():
    # scrap the basic details
    user_ip = request.remote_addr
    user_sid = request.sid

    user_type = users[user_sid]['user_type']
    verification_status = users[user_sid]['Varification']

    # save user information
    users.pop(user_sid)

    # display connection successful message
    print(f'User disconnected {user_ip}\t{user_sid}\t{user_type}\t{verification_status}')

    emit('update_web_app', {'message':'USER CONNECTED', 'users':users}, broadcast=True)
'''
    for admin in admin_list + staff_list + client_list:
        emit('update_web_app', {'message':'USER CONNECTED', 'users':users}, room=admin)
'''    
@socketio.on('send_message')
def send_message(data):
    # scrap basic details
    sender_sid = request.sid
    recipients = data['recipients']
    message = data['message']

    # filter the recipient group
    if recipients == 'admin':
        for admin in admin_list:
            # send message to all the group members
            emit('message_from_user', {'message':message, 'sender':sender_sid, 'sender_name':users[sender_sid]['user_name']}, room=admin)
    elif recipients == 'client':
        for client in client_list:
            emit('message_from_user', {'message':message, 'sender':sender_sid, 'sender_name':users[sender_sid]['user_name']}, room=client)
    elif recipients == 'staff':
        for staff in staff_list:
            emit('message_from_user', {'message':message, 'sender':sender_sid, 'sender_name':users[sender_sid]['user_name']}, room=staff)
    else:
        # if recipient group is neither admin, staff not client
        emit('message_from_user', {'message':message, 'sender':sender_sid, 'sender_name':users[sender_sid]['user_name']}, room=recipients)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8080)
```
## Javascript Codes
- Add these codes in your `<head>` tag
```javascript
// Connect the user to the server
var socket = io.connect(`server_url`);

// 1. Connect event
socket.on('connect', function () {
    console.log('Connected to server');
});

// 2. Verify user event
socket.on('verify_user', function (data) {
      console.log('User verified:', data);
});

// 4. message_individual event
socket.on('message_from_user', function (data) {
      console.log('Received individual message:', data);
});

// send message  
function send_message(message, recipients) {
    socket.emit('send_message', { message: message, recipients: recipients });
}

// Function to emit verify_user event
function verifyUser(userType) {
    socket.emit('verify_user', { user_type: `user_type`, user_name: `user_name` });
}

// call the function when App loads
window.addEventListener('load', function () {
    verifyUser();
});

// handle the received update_web_app message 
socket.on('update_web_app', function (data) {
    console.log('Received message:', data); // log the message received
});
```
- remember to replace and handle the valiables `user_type`, `user_name` and `server_url`.

## Important
- executing the main `app.py` file directly don't need any modification in the webpages.
- For your own use you can modify the file as per your need.
- For users their app will be serving at the url like `localhost:8080/user_type/user_name` where usertype may be `admin`, `staff` or `client`.
## Screenshots
- ![Example Image](https://i.ibb.co/CQ6YVLs/Screenshot-2024-04-16-181417.png)
- ![Example Image](https://i.ibb.co/p27qWqH/Screenshot-2024-04-16-181457.png)

## Install

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run (Flask / SocketIO)

Run the existing Flask app:

```bash
python app.py
```

Default URL patterns:

- `http://localhost:8080/admin/<username>`
- `http://localhost:8080/staff/<username>`
- `http://localhost:8080/client/<username>`

## FastAPI Rooms (Shareable URL chat)

This repository also includes a separate FastAPI + WebSocket based room chat app under `fastapi_chat/`.

### Features

- Create a room and get a shareable URL
- Anyone opening the URL can send/receive messages
- Messages are broadcast to all connected users in the room

### Run

```bash
python -m uvicorn fastapi_chat.main:app --host 0.0.0.0 --port 8090 --reload
```

Open:

- `http://localhost:8090/`

Create a room and share the generated room link.
