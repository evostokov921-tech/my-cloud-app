import os
import sqlite3
import hashlib
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from datetime import date

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_session'
DATABASE = 'habits.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    
    conn.execute('''CREATE TABLE IF NOT EXISTS users
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     username TEXT UNIQUE NOT NULL, 
                     password TEXT NOT NULL)''')
                     
    conn.execute('''CREATE TABLE IF NOT EXISTS habits
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     name TEXT NOT NULL, 
                     user_id INTEGER)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS completions
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     habit_id INTEGER, 
                     date TEXT, 
                     FOREIGN KEY(habit_id) REFERENCES habits(id),
                     UNIQUE(habit_id, date))''')
    
    try:
        conn.execute('ALTER TABLE habits ADD COLUMN user_id INTEGER')
    except:
        pass
        
    conn.commit()
    conn.close()

init_db()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@app.route('/')
def index():
    if 'user_id' not in session:
        return render_template('index.html', user=None)
    return render_template('index.html', user=session['username'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Заполните все поля"}), 400
        
    conn = get_db()
    try:
        conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
                     (username, hash_password(password)))
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        session['user_id'] = user['id']
        session['username'] = user['username']
        conn.close()
        return jsonify({"message": "Успех!"}), 200
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Такой пользователь уже существует"}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', 
                        (username, hash_password(password))).fetchone()
    conn.close()
    
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        return jsonify({"message": "Вход выполнен!"}), 200
    else:
        return jsonify({"error": "Неверный логин или пароль"}), 401

@app.route('/api/habits', methods=['GET'])
def get_habits():
    if 'user_id' not in session:
        return jsonify([]), 401
        
    conn = get_db()
    habits = conn.execute('SELECT * FROM habits WHERE user_id = ?', (session['user_id'],)).fetchall()
    result = []
    for habit in habits:
        habit_dict = dict(habit)
        completions = conn.execute('SELECT date FROM completions WHERE habit_id = ?', (habit['id'],)).fetchall()
        habit_dict['dates'] = [row['date'] for row in completions]
        result.append(habit_dict)
    conn.close()
    return jsonify(result)

@app.route('/api/habits', methods=['POST'])
def add_habit():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "No name provided"}), 400
        
    new_habit_name = data['name']
    conn = get_db()
    conn.execute('INSERT INTO habits (name, user_id) VALUES (?, ?)', 
                 (new_habit_name, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({"message": "Success!", "habit": new_habit_name}), 201

@app.route('/api/habits/<int:habit_id>/complete/<date>', methods=['POST'])
def complete_habit(habit_id, date):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db()
    try:
        existing = conn.execute('SELECT id FROM completions WHERE habit_id = ? AND date = ?', (habit_id, date)).fetchone()
        if existing:
            conn.execute('DELETE FROM completions WHERE habit_id = ? AND date = ?', (habit_id, date))
        else:
            conn.execute('INSERT INTO completions (habit_id, date) VALUES (?, ?)', (habit_id, date))
        conn.commit()
        conn.close()
        return jsonify({"message": "Updated", "date": date}), 200
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500

@app.route('/api/habits/<int:habit_id>', methods=['DELETE'])
def delete_habit(habit_id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db()
    conn.execute('DELETE FROM habits WHERE id = ? AND user_id = ?', (habit_id, session['user_id']))
    conn.execute('DELETE FROM completions WHERE habit_id = ?', (habit_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Привычка удалена!"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)