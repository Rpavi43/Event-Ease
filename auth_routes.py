from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import MySQLdb.cursors
from extensions import mysql

auth = Blueprint('auth', __name__)

# User class to work with flask_login
class User(UserMixin):
    def __init__(self, id, username, email, is_admin=False):
        self.id = id
        self.username = username
        self.email = email
        self.is_admin = is_admin

    def get_id(self):
        return str(self.id)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()

        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'], user['email'], user['is_admin'])
            login_user(user_obj)

            flash('Logged in successfully!', 'success')

            if user['is_admin']:
                return redirect('/admin/dashboard')
            else:
                return redirect('/')
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('login.html')


@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cur.fetchone()

        if existing_user:
            flash('Email already registered.', 'warning')
        else:
            hashed_password = generate_password_hash(password)

            is_admin = email == 'admin1@example.com'  # You can modify the admin logic here
            cur.execute(
                "INSERT INTO users (username, email, password, is_admin) VALUES (%s, %s, %s, %s)",
                (username, email, hashed_password, is_admin)
            )
            mysql.connection.commit()
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('signup.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('auth.login'))
