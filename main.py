from flask import *
import ollama
from flask_login import *


from flask_cors import CORS


import sqlite3
import secrets
import re


conn = sqlite3.connect("database.db", check_same_thread=False)


# Create a table if it doesn't exist
with conn:
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS USERS(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, password TEXT, email TEXT)"
    )
    conn.commit()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS MEMORY(id INTEGER, user_id INTEGER, message TEXT, reply TEXT, FOREIGN KEY(user_id) REFERENCES USERS(id))"
    )
    conn.commit()

app = Flask(__name__)
lm = LoginManager()
lm.init_app(app)
lm.login_view = "login"
lm.login_message_category = "info"
app.secret_key = "132123213213"  # Change this to a random secret key
CORS(app, supports_credentials=True)


class User(UserMixin):
    def __init__(self, id, username, password, email):
        self.id = id
        self.username = username
        self.password = password
        self.email = email

    @staticmethod
    def get(user_id):
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        cur.execute("SELECT * FROM USERS WHERE id=?", (user_id,))
        user = cur.fetchone()
        return User(user[0], user[1], user[2], user[3]) if user else None


pre_context = """You are a helpful assistant named Kindeye. made by Aman Sharma. Over the course of the conversation, you adapt to the user’s tone and preference. Try to match the user's vibe, tone, and generally how they are speaking. You want the conversation to feel natural. You engage in authentic conversation by responding to the information provided and showing genuine curiosity. Ask a very simple, single-sentence follow-up question when natural. Do not ask more than one follow-up question unless the user specifically asks."""

@lm.user_loader
def load_user(user_id):
    return User.get(user_id)


@app.route("/test")
def test():
    return render_template("test.html")
@app.route("/process_message", methods=["POST"])
@login_required
def process_message():
    data = request.get_json()
    message = data.get("message", "")
    chat_id = data.get("chat_id", None)  # if there is no chat_id,
    if not chat_id:
        # generate a new chat_id if not provided
        chat_id = secrets.token_urlsafe(16)
        contenxt = f"{pre_context}\nThis is a new chat, please answer accordingly\n" + message + "\n"
    else:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM MEMORY WHERE id=? AND user_id=?",
                (chat_id, current_user.id),
            )
            chats = cur.fetchall()

            contenxt = f"{pre_context}\nHere is your previous chat history answer accordingly\n"
            for chat in chats:
                contenxt += f"User: {chat[2]}\n"
                contenxt += f"You: {chat[3]}\n"
            contenxt += f"User: {message}\n"
    # Process the message here (e.g., save to a database, send to another service, etc.)
    print(chat_id)
    print(contenxt)
    response = ollama.chat(
        model="llama3", messages=[{"role": "user", "content": contenxt}]
    )
    with conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO MEMORY (id, user_id, message, reply) VALUES (?, ?, ?, ?)",
            (chat_id, current_user.id, message, response["message"]["content"]),
        )
        conn.commit()
    return jsonify(
        {
            "status": "success",
            "message": response["message"]["content"],
            "chat_id": chat_id,  # return the chat_id in the response
        }
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat/<chat_id>")
@app.route("/chat")
@app.route("/chat/")
@login_required
def chat(chat_id=None):
    previous_chats = []
    with conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT id FROM MEMORY WHERE user_id=?", (current_user.id,)
        )
        previous_chats = cur.fetchall()
        previous_chats = [
            chat[0] for chat in previous_chats
        ]  # Extract chat IDs from tuples

    if chat_id is None:
        return render_template("chat.html", previous_chats=previous_chats, chat=None)
    else:
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM MEMORY WHERE id=?", (chat_id,))
            chat = cur.fetchall()
            if chat:
                return render_template(
                    "chat.html", chat=chat, previous_chats=previous_chats
                )
            else:
                flash("Chat not found", "warning")
                return redirect(url_for("chat"))


@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        match_against = "username"
        if "@" in username:
            match_against = "email"
        with conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM USERS WHERE {match_against}=? AND password=?",
                (username, password),
            )
            user = cur.fetchone()
            if user:
                user_obj = User(user[0], user[1], user[2], user[3])
                login_user(user_obj, remember=True)
                next = request.args.get("next")
                print(next)
                return redirect(next or url_for("index"))
            else:
                flash("Invalid username or password", "danger")
                return render_template(
                    "login.html",
                )

    next = request.args.get("next", "")
    if next:
        next = f"?next={next}"
    return render_template(
        "login.html",
        next=next,
    )


@app.route("/breath")
def breathe():
    return render_template("breathe.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

@app.route("/del/<chat_id>")
@login_required
def delete_chat(chat_id):
    with conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM MEMORY WHERE id=? AND user_id=?", (chat_id, current_user.id)
        )
        conn.commit()
    flash("Chat deleted successfully", "success")
    return redirect(url_for("chat"))



@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = request.form["password"]
    email = request.form["email"]
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        flash("Invalid email address", "danger")
        return render_template("login.html")
    with conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM USERS WHERE username=? OR email=?",
            (
                username,
                email,
            ),
        )
        user = cur.fetchone()
        if user:
            flash("Username or email already exists", "danger")
            return render_template("login.html")
        cur.execute(
            "INSERT INTO USERS (username, password, email) VALUES (?, ?, ?)",
            (username, password, email),
        )
        login_user(User(cur.lastrowid, username, password, email))
        conn.commit()
    return redirect(url_for("index"))

    # About page route
@app.route("/about")
def about():
    return render_template("about.html")  # This is where your About page content will be rendered

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=80)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=80)
