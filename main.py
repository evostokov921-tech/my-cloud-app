import os
import sqlite3
import hashlib
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_session'

# Получаем ссылку на базу данных из переменных окружения
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    if DATABASE_URL:
        # Если есть PostgreSQL - используем его
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        # Иначе используем SQLite (для тестов)
        conn = sqlite3.connect('habits.db')
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    # Таблица пользователей
    cur.execute('''CREATE TABLE IF NOT EXISTS users
                    (id SERIAL PRIMARY KEY, 
                     username TEXT UNIQUE NOT NULL, 
                     password TEXT NOT NULL)''')
                     
    # Таблица привычек
    cur.execute('''CREATE TABLE IF NOT EXISTS habits
                    (id SERIAL PRIMARY KEY, 
                     name TEXT NOT NULL, 
                     user_id INTEGER)''')

    # Таблица выполнений
    cur.execute('''CREATE TABLE IF NOT EXISTS completions
                    (id SERIAL PRIMARY KEY, 
                     habit_id INTEGER, 
                     date TEXT, 
                     FOREIGN KEY(habit_id) REFERENCES habits(id),
                     UNIQUE(habit_id, date))''')
    
    conn.commit()
    cur.close()
    conn.close()

# Инициализируем БД при старте
try:
    init_db()
except:
    pass 

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
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO users (username, password) VALUES (%s, %s)', 
                     (username, hash_password(password)))
        conn.commit()
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        session['user_id'] = user['id']
        session['username'] = user['username']
        cur.close()
        conn.close()
        return jsonify({"message": "Успех!"}), 200
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({"error": "Такой пользователь уже существует"}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM users WHERE username = %s AND password = %s', 
                (username, hash_password(password)))
    user = cur.fetchone()
    cur.close()
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
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM habits WHERE user_id = %s', (session['user_id'],))
    habits = cur.fetchall()
    
    result = []
    for habit in habits:
        habit_dict = dict(habit)
        cur.execute('SELECT date FROM completions WHERE habit_id = %s', (habit['id'],))
        completions = cur.fetchall()
        habit_dict['dates'] = [row['date'] for row in completions]
        result.append(habit_dict)
    
    cur.close()
    conn.close()
    return jsonify(result)

@app.route('/api/habits', methods=['POST'])
def add_habit():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.get_json()
    if not data or 'name' not in data:  # <-- ИСПРАВЛЕНО ЗДЕСЬ
        return jsonify({"error": "No name provided"}), 400
        
    new_habit_name = data['name']
    conn = get_db()
    cur = conn.cursor()
    cur.execute('INSERT INTO habits (name, user_id) VALUES (%s, %s)', 
                 (new_habit_name, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "Success!", "habit": new_habit_name}), 201

@app.route('/api/habits/<int:habit_id>/complete/<date>', methods=['POST'])
def complete_habit(habit_id, date):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('SELECT id FROM completions WHERE habit_id = %s AND date = %s', (habit_id, date))
        existing = cur.fetchone()
        
        if existing:
            cur.execute('DELETE FROM completions WHERE habit_id = %s AND date = %s', (habit_id, date))
        else:
            cur.execute('INSERT INTO completions (habit_id, date) VALUES (%s, %s)', (habit_id, date))
        
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Updated", "date": date}), 200
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({"error": str(e)}), 500

@app.route('/api/habits/<int:habit_id>', methods=['DELETE'])
def delete_habit(habit_id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM habits WHERE id = %s AND user_id = %s', (habit_id, session['user_id']))
    cur.execute('DELETE FROM completions WHERE habit_id = %s', (habit_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "Привычка удалена!"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)