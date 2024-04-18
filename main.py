from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory,make_response, send_file
import sqlite3
import hashlib
import os
import io
from datetime import datetime
import base64
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = '1111'
app.config['UPLOAD_FOLDER'] = 'uploads'



conn = sqlite3.connect('документооборот.db')
cursor = conn.cursor()


cursor.execute('''
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        content TEXT,
        author TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        file_data BLOB,
        file_extension TEXT,  -- Поле для хранения расширения файла
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        approval_status TEXT DEFAULT 'pending' -- Поле для статуса согласования
    )
''')
conn.commit()


cursor.execute('''
   CREATE TABLE IF NOT EXISTS document_approvals (
      id INTEGER PRIMARY KEY,
      document_id INTEGER NOT NULL,  
      approver_id INTEGER NOT NULL,
      status TEXT DEFAULT 'pending',
      approved_at TIMESTAMP
   )
''')


cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL,
        password_hash TEXT NOT NULL
    )
''')
conn.commit()

cursor.execute('''
CREATE TABLE IF NOT EXISTS sent_documents (
    id INTEGER PRIMARY KEY,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approval_status TEXT DEFAULT 'pending',
    FOREIGN KEY (sender_id) REFERENCES users(id),
    FOREIGN KEY (receiver_id) REFERENCES users(id),
    FOREIGN KEY (document_id) REFERENCES documents(id),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE -- Удалять сообщение, если документ удаляется
)
''')
conn.commit()



@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('документооборот.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        if user and user[2] == hashlib.sha256(password.encode('utf-8')).hexdigest():  # Проверяем хешированный пароль
            session['username'] = username  # Сохраняем имя пользователя в сессии
            session['user_id'] = user[0]
            return redirect(url_for('document_interaction'))

    return render_template('login.html')


@app.route('/admin')
def admin():
    conn = sqlite3.connect('документооборот.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT * FROM documents")
    documents = cursor.fetchall()

    return render_template('admin.html', users=users, documents=documents)


@app.route('/delete_user/<user_id>', methods=['GET'])
def delete_user(user_id):
    conn = sqlite3.connect('документооборот.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    return redirect('/admin')


@app.route('/delete_doc/<document_id>', methods=['GET'])
def delete_doc(document_id):
    conn = sqlite3.connect('документооборот.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM documents WHERE id=?", (document_id,))
    cursor.execute("DELETE FROM sent_documents WHERE document_id=?", (document_id,))
    conn.commit()
    return redirect('/admin')

@app.route('/create_user', methods=['POST'])
def create_user():
    if request.method == 'POST':
        username = request.form['username']
        conn = sqlite3.connect('документооборот.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username) VALUES (?)", (username,))
        conn.commit()
        return redirect('/admin')



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('документооборот.db')
        cursor = conn.cursor()
        password_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()  # Хешируем пароль перед сохранением
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))



@app.route('/document_interaction', methods=['GET'])
def document_interaction():
    conn = sqlite3.connect('документооборот.db')
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_user = session['username']


    cursor.execute('SELECT * FROM documents WHERE author = ? AND approval_status = "pending"', (current_user,))
    pending_documents = cursor.fetchall()

    cursor.execute('SELECT * FROM documents WHERE approval_status = "approved"')
    approved_documents = cursor.fetchall()

    conn.close()

    return render_template('document_interaction.html', approved_documents=approved_documents,
                           pending_documents=pending_documents, current_time=current_time)


@app.route('/search', methods=['GET'])
def search():
    search_term = request.args.get('query').lower()
    conn = sqlite3.connect('документооборот.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM documents WHERE lower(title) LIKE ? OR lower(content) LIKE ? OR lower(author) LIKE ?', ('%' + search_term + '%', '%' + search_term + '%', '%' + search_term + '%'))
    search_results = cursor.fetchall()
    conn.close()
    return jsonify(search_results)




@app.route('/add_document', methods=['GET', 'POST'])
def add_document():
    if request.method == 'POST':
        title = request.form['title']
        author = session['username']

        file = request.files['file']

        if file:

            secure_file_name = secure_filename(file.filename)
            file_extension = os.path.splitext(secure_file_name)[1]
            file_data = file.read()

            conn = sqlite3.connect('документооборот.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO documents (title, author, file_data, file_extension, uploaded_at) VALUES (?, ?, ?, ?, ?)',
                           (title, author, file_data, file_extension, datetime.now()))
            conn.commit()
            conn.close()
            return redirect(url_for('document_interaction'))
        else:
            return "File was not uploaded"
    return render_template('add_document.html')


@app.route('/send_document', methods=['GET', 'POST'])
def send_document():
    if request.method == 'POST':
        receiver_username = request.form['receiver']
        document_id = request.form['document_id']
        approval_needed = 'pending_approval' if request.form.get(
            'approval_needed') else None  # Проверяем, требуется ли согласование

        conn = sqlite3.connect('документооборот.db')
        cursor = conn.cursor()

        sender_id = cursor.execute('SELECT id FROM users WHERE username = ?', (session['username'],)).fetchone()[0]
        receiver_id = cursor.execute('SELECT id FROM users WHERE username = ?', (receiver_username,)).fetchone()[0]

        cursor.execute(
            'INSERT INTO sent_documents (sender_id, receiver_id, document_id, approval_status) VALUES (?, ?, ?, ?)',
            (sender_id, receiver_id, document_id, approval_needed))
        conn.commit()
        conn.close()

        return redirect(url_for('send_document'))

    conn = sqlite3.connect('документооборот.db')
    cursor = conn.cursor()

    all_users = cursor.execute('SELECT username FROM users').fetchall()
    all_documents = cursor.execute('SELECT id, title FROM documents').fetchall()
    current_user_id = cursor.execute('SELECT id FROM users WHERE username = ?', (session['username'],)).fetchone()[0]

    cursor.execute('''
        SELECT d.id, d.title, u.username AS sender, d.uploaded_at AS sent_at, d.author, s.approval_status
        FROM sent_documents s
        JOIN users u ON s.sender_id = u.id
        JOIN documents d ON s.document_id = d.id
        WHERE s.receiver_id = ?
        ORDER BY d.uploaded_at DESC
    ''', (current_user_id,))
    incoming_documents = cursor.fetchall()

    conn.close()

    return render_template('send_document.html', all_users=all_users, incoming_documents=incoming_documents,
                           all_documents=all_documents)


@app.route('/approve_document/<document_id>')
def approve_document(document_id):

   approver_id = session['user_id']

   conn = sqlite3.connect('документооборот.db')
   cursor = conn.cursor()


   cursor.execute('''
      INSERT INTO document_approvals 
         (document_id, approver_id, status)
      VALUES (?, ?, 'approved')
   ''', (document_id, approver_id))


   cursor.execute('UPDATE sent_documents SET approval_status="approved" WHERE document_id=?', (document_id,))
   cursor.execute('UPDATE documents SET approval_status="approved" WHERE id=?', (document_id,))

   conn.commit()
   conn.close()

   return redirect(url_for('send_document'))



@app.route('/download/<int:file_id>', methods=['GET'])
def download(file_id):
    conn = sqlite3.connect('документооборот.db')
    cursor = conn.cursor()
    cursor.execute('SELECT title, file_data, file_extension FROM documents WHERE id = ?', (file_id,))
    result = cursor.fetchone()
    title = result[0]
    file_data = result[1]
    file_extension = result[2]
    conn.close()

    tempdir = 'temp_files'
    if not os.path.exists(tempdir):
        os.mkdir(tempdir)

    file_path = os.path.join(tempdir, f"{title}{file_extension}")
    with open(file_path, 'wb') as file:
        file.write(file_data)

    return send_file(file_path, as_attachment=True)



@app.route('/delete_message/<message_id>')
def delete_message(message_id):

  conn = sqlite3.connect('документооборот.db')
  cursor = conn.cursor()

  cursor.execute('DELETE FROM sent_documents WHERE id = ?', (message_id,))

  conn.commit()
  conn.close()

  return redirect(url_for('send_document'))


# Запуск приложения
if __name__ == '__main__':
    app.run(debug=True)
