# app.py

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_login import LoginManager, login_required, current_user
import MySQLdb.cursors
from config import config
from extensions import mysql, login_manager
from auth_routes import auth, User
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from flask_paginate import Pagination, get_page_parameter
from flask import Response
import csv
from io import StringIO
from user import User
import os
from werkzeug.utils import secure_filename
from flask_mysqldb import MySQL


from flask_mail import Mail, Message



app = Flask(__name__)
app.config.from_object(config)

# Initialize extensions
mysql.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# Register Blueprint
app.register_blueprint(auth, url_prefix='/auth')

@login_manager.user_loader
def load_user(user_id):
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()

    if row:
        # ✅ Instantiate with role for admin detection
        return User(id=row['id'], username=row['username'], email=row['email'], role=row['role'])
    return None

@app.route('/', methods=['GET', 'POST'])
def home():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)  # ← make cursor return dictionaries
    cur.execute("SELECT * FROM events")
    events = cur.fetchall()

    if request.method == 'POST' and current_user.is_authenticated and not current_user.is_admin:
        event_id = request.form['event_id']
        user_id = current_user.id

        cur.execute("INSERT INTO registrations (user_id, event_id) VALUES (%s, %s)", (user_id, event_id))
        mysql.connection.commit()
        flash('You have successfully registered for the event!')

        return redirect(url_for('home'))

    return render_template('home.html', events=events)


@app.route('/test-db')
def test_db():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM events")
    data = cur.fetchall()
    return str(data)


@app.route('/admin/dashboard', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("Access denied.")
        return redirect(url_for('home'))

    cur = mysql.connection.cursor()

    if request.method == 'POST':
        title = request.form['title']
        date = request.form['date']
        location = request.form['location']
        description = request.form['description']
        cur.execute("INSERT INTO events (title, date, location, description) VALUES (%s, %s, %s, %s)",
                    (title, date, location, description))
        mysql.connection.commit()
        flash('Event added successfully!')
        return redirect(url_for('admin_dashboard'))

    cur.execute("SELECT * FROM events ORDER BY date ASC")
    raw_events = cur.fetchall()

    # Convert each tuple to a dictionary
    events = [
        {
            'id': e[0],
            'title': e[1],
            'date': e[2],
            'location': e[3],
            'description': e[4]
        }
        for e in raw_events
    ]

    return render_template('admin_dashboard.html', events=events)


@app.route('/register_event/<int:event_id>', methods=['GET', 'POST'])
@login_required
def register_event(event_id):
    user_id = current_user.id

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']

        # 🔒 Server-side validation
        if not name or not email or not phone:
            flash("All fields are required!", "danger")
            return redirect(url_for('register_event', event_id=event_id))

        if not phone.isdigit() or len(phone) != 10:
            flash("Invalid phone number. Please enter a 10-digit number.", "danger")
            return redirect(url_for('register_event', event_id=event_id))

        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        # 🔄 Prevent duplicate registration
        cur.execute("SELECT * FROM registrations WHERE user_id = %s AND event_id = %s", (user_id, event_id))
        if cur.fetchone():
            flash("You are already registered for this event!", "warning")
            return redirect(url_for('dashboard'))

        # 🎟️ Check event capacity
        cur.execute("""
            SELECT capacity, 
                   (SELECT COUNT(*) FROM registrations WHERE event_id = %s) AS registered_count 
            FROM events WHERE id = %s
        """, (event_id, event_id))
        event_data = cur.fetchone()

        if event_data['registered_count'] >= event_data['capacity']:
            flash("Event is full! You cannot register.", "danger")
            return redirect(url_for('home'))

        # ✅ Proceed with registration
        cur.execute("""
            INSERT INTO registrations (user_id, event_id, name, email, phone)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, event_id, name, email, phone))
        mysql.connection.commit()

        # 📧 Send confirmation email
        msg = Message('Event Registration Confirmation', recipients=[email])
        msg.body = f"""
            Hello {name},

            You have successfully registered for the event!
            Event ID: {event_id}

            Thank you for your registration!

            Best regards,
            EventEase Team
        """
        try:
            mail.send(msg)
            flash("Registration successful! A confirmation email has been sent.", "success")
        except Exception as e:
            flash("Registration successful, but email sending failed.", "warning")
            print(e)

        return redirect(url_for('dashboard'))

    # GET request – show the registration form
    return render_template('register_event.html', event_id=event_id)

from MySQLdb.cursors import DictCursor

@app.route('/admin/edit/<int:event_id>', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    if not current_user.is_admin:
        flash("Access denied.")
        return redirect(url_for('home'))

    # Use a single cursor object for both fetching and updating
    cur = mysql.connection.cursor(DictCursor)
    
    # Fetch event details
    cur.execute("SELECT * FROM events WHERE id = %s", (event_id,))
    event = cur.fetchone()

    if event is None:
        flash("Event not found.")
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        # Fetch the form data (excluding the image)
        title = request.form['title']
        date = request.form['date']
        location = request.form['location']
        description = request.form['description']

        # Keep the existing image (no changes to image)
        image_filename = event['image_path']

        # Update event details in the database (excluding image update)
        cur.execute("""
            UPDATE events 
            SET title=%s, date=%s, location=%s, description=%s 
            WHERE id=%s
        """, (title, date, location, description, event_id))
        mysql.connection.commit()
        
        flash('Event updated successfully!')
        return redirect(url_for('admin_dashboard'))

    # If GET request, just show the event data in the form
    return render_template('edit_event.html', event=event)



@app.route('/admin/delete/<int:event_id>', methods=['POST'])
@login_required
def delete_event(event_id):
    if not current_user.is_admin:
        flash("Access denied.")
        return redirect(url_for('home'))

    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM events WHERE id = %s", (event_id,))
    mysql.connection.commit()
    flash('Event deleted successfully!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add', methods=['GET', 'POST'])
@login_required
def add_event():
    if not current_user.is_admin:
        flash("Access denied", "danger")
        return redirect(url_for('home'))

    if request.method == 'POST':
        title = request.form['title']
        date = request.form['date']
        location = request.form['location']
        description = request.form['description']

        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO events (title, date, location, description) VALUES (%s, %s, %s, %s)",
                    (title, date, location, description))
        mysql.connection.commit()
        flash("Event added successfully!", "success")
        return redirect(url_for('admin_dashboard'))

    return render_template('add_event.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    cur = mysql.connection.cursor()

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        # Update the user info in the database
        if password:
            # Hash the new password
            hashed_password = generate_password_hash(password, method='sha256')
            cur.execute("""
                UPDATE users SET name = %s, email = %s, password = %s WHERE id = %s
            """, (name, email, hashed_password, current_user.id))
        else:
            cur.execute("""
                UPDATE users SET name = %s, email = %s WHERE id = %s
            """, (name, email, current_user.id))
        
        mysql.connection.commit()
        flash('Profile updated successfully!')
        return redirect(url_for('profile'))

    # Retrieve current user data
    cur.execute("SELECT * FROM users WHERE id = %s", (current_user.id,))
    user = cur.fetchone()
    return render_template('profile.html', user=user)

@app.route('/registrations', methods=['GET'])
@login_required
def registrations():
    event_id = request.args.get('event_id', type=int)
    status = request.args.get('status', type=str)
    search = request.args.get('search', type=str)
    export = request.args.get('export', type=str)

    page = request.args.get(get_page_parameter(), type=int, default=1)
    per_page = 5
    offset = (page - 1) * per_page

    search_param = f"%{search}%" if search else None
    query_params = (event_id, event_id, status, status, search, search_param, per_page, offset)

    query = """
        SELECT 
            registrations.id,
            users.username AS user_name,
            users.email AS user_email,
            registrations.phone AS user_phone,
            events.title AS event_title,
            registrations.status
        FROM registrations
        JOIN users ON registrations.user_id = users.id
        JOIN events ON registrations.event_id = events.id
        WHERE (%s IS NULL OR registrations.event_id = %s)
        AND (%s IS NULL OR registrations.status = %s)
        AND (%s IS NULL OR users.username LIKE %s)
        ORDER BY registrations.id DESC
        LIMIT %s OFFSET %s
    """

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute(query, query_params)
    registrations = cur.fetchall()

    # Total count for pagination
    count_query = """
        SELECT COUNT(*) as total
        FROM registrations
        JOIN users ON registrations.user_id = users.id
        JOIN events ON registrations.event_id = events.id
        WHERE (%s IS NULL OR registrations.event_id = %s)
        AND (%s IS NULL OR registrations.status = %s)
        AND (%s IS NULL OR users.username LIKE %s)
    """
    count_params = (event_id, event_id, status, status, search, search_param)
    cur.execute(count_query, count_params)
    total = cur.fetchone()['total']

    # Event list for filter dropdown
    cur.execute("SELECT id, title FROM events")
    events = cur.fetchall()
    cur.close()

    # CSV Export logic
    if export == 'csv':
        si = StringIO()
        csv_writer = csv.writer(si)
        csv_writer.writerow(['ID', 'User', 'Email', 'Phone', 'Event', 'Status'])
        for reg in registrations:
            csv_writer.writerow([reg['id'], reg['user_name'], reg['user_email'], reg['user_phone'], reg['event_title'], reg['status']])
        output = si.getvalue()
        return Response(output, mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=registrations.csv"})

    pagination = Pagination(page=page, total=total, per_page=per_page, css_framework='bootstrap4')

    return render_template('registrations.html', registrations=registrations, events=events,
                           pagination=pagination, event_id=event_id, status=status, search=search)


@app.route('/admin/delete_registration/<int:reg_id>', methods=['POST'])
@login_required
def delete_registration(reg_id):
    if not current_user.is_admin:
        flash("Access denied.")
        return redirect(url_for('home'))

    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM registrations WHERE id = %s", (reg_id,))
    mysql.connection.commit()
    flash('Registration deleted successfully!')
    return redirect(url_for('registrations'))

@app.route('/admin/approve_registration/<int:reg_id>', methods=['GET'])
@login_required
def approve_registration(reg_id):
    if not current_user.is_admin:
        flash("Access denied.")
        return redirect(url_for('home'))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cur.execute("UPDATE registrations SET status = 'Approved' WHERE id = %s", (reg_id,))
    mysql.connection.commit()
    flash('Registration approved!')

    # Get user email for the approved registration
    cur.execute("SELECT users.email, users.username, events.title FROM registrations JOIN users ON registrations.user_id = users.id JOIN events ON registrations.event_id = events.id WHERE registrations.id = %s", (reg_id,))
    reg_data = cur.fetchone()

    if reg_data:
        # Send Approval Email
        msg = Message('Event Registration Approved',
                      recipients=[reg_data['email']])  # Send to user's email
        msg.body = f"Hello {reg_data['username']},\n\nYour registration for the event '{reg_data['title']}' has been approved.\n\nThank you!"
        try:
            mail.send(msg)
            flash("Approval email sent successfully.", "success")
        except Exception as e:
            flash("Error sending approval email.", "danger")
            print(e)

    return redirect(url_for('registrations'))


@app.route('/export_registrations')
@login_required
def export_registrations():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT 
            users.username, users.email, users.phone,
            events.title, registrations.status 
        FROM registrations 
        JOIN users ON registrations.user_id = users.id 
        JOIN events ON registrations.event_id = events.id 
        ORDER BY registrations.id DESC
    """)
    rows = cur.fetchall()
    cur.close()

    def generate():
        yield 'Username,Email,Phone,Event Title,Status\n'
        for row in rows:
            yield ','.join([str(field) for field in row]) + '\n'

    return Response(generate(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=registrations.csv'})

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        # Admin Dashboard
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        # Fetch all events for admin to manage
        cur.execute("SELECT * FROM events ORDER BY date ASC")
        events = cur.fetchall()

        # Fetch all pending registrations to approve/reject
        cur.execute("""
            SELECT r.id AS reg_id, u.username, u.email, e.title, e.date, r.status
            FROM registrations r
            JOIN users u ON r.user_id = u.id
            JOIN events e ON r.event_id = e.id
            WHERE r.status = 'Pending'
            ORDER BY e.date ASC
        """)
        pending_regs = cur.fetchall()

        cur.close()
        return render_template("admin_dashboard.html", events=events, pending_regs=pending_regs)

    else:
        # Regular User Dashboard
        user_id = current_user.id

        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        # Get user profile info
        cur.execute("SELECT username, email FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()

        # Get upcoming registrations for the user
        cur.execute("""
            SELECT r.id AS reg_id, e.title, e.date, r.status
            FROM registrations r
            JOIN events e ON r.event_id = e.id
            WHERE r.user_id = %s AND e.date >= CURDATE()
            ORDER BY e.date ASC
        """, (user_id,))
        upcoming = cur.fetchall()
        
        cur.close()

        return render_template("dashboard.html", user=user, upcoming=upcoming)


# Add email configuration to app config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # Use your email provider's SMTP server
app.config['MAIL_PORT'] = 587  # Use port 587 for secure TLS
app.config['MAIL_USE_TLS'] = True  # Use TLS (Transport Layer Security)
app.config['MAIL_USERNAME'] = 'pavithrareddy043@gmail.com'  # Replace with your email
app.config['MAIL_PASSWORD'] = 'rlqz claz ttab lwef'  # Replace with your email password or app password
app.config['MAIL_DEFAULT_SENDER'] = 'your-email@gmail.com'  # Default sender email address

# Initialize Flask-Mail
mail = Mail(app)



if __name__ == '__main__':
    app.run(debug=True)
