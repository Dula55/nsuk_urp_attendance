from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timezone  # Updated for UTC timezone
from sqlalchemy import Column, Integer, String, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from flask import Response, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import NotFound, Forbidden
from sqlalchemy.exc import IntegrityError
import io
import csv
from flask_wtf import FlaskForm
from flask_wtf.csrf import validate_csrf
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from flask_wtf.csrf import CSRFProtect


import logging
from logging.handlers import RotatingFileHandler

Base = declarative_base()

app = Flask(__name__)
app.debug = True
app.secret_key = 'your_secret_key'
csrf = CSRFProtect(app)

# Configure logging AFTER app is created
if not app.debug:
    handler = RotatingFileHandler('error.log', maxBytes=10000, backupCount=1)
    handler.setLevel(logging.ERROR)
    app.logger.addHandler(handler)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///attendance.db'  # or your DB URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database and migration
db = SQLAlchemy(app)
migrate = Migrate(app, db)


# Create tables
with app.app_context():
    db.create_all()


# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # 'lecturer' or 'student'


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    matric_no = db.Column(db.String(50), unique=True)
    course = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=True)  # New field
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Student {self.matric_no}>'
    

class StudentRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    matric_no = db.Column(db.String(20), nullable=False, unique=True)
    course = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now)
    active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<StudentRecord {self.matric_no}>'
    
# Attendance Model
class Attendance(db.Model):
    __tablename__ = 'attendance'  # Explicit table name
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    matric_no = db.Column(db.String(50), nullable=False)
    course = db.Column(db.String(100), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Attendance {self.matric_no}>"

class AttendanceForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired()])
    matric_no = StringField('Matric Number', validators=[DataRequired()])
    course = StringField('Course', validators=[DataRequired()])
    submit = SubmitField('Submit Attendance')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

# Home Route
@app.route('/')
def index():
    return render_template('index.html')

# Register Route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists!', 'danger')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password, role=role)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = user.role
            
            if user.role == 'lecturer':
                return redirect(url_for('records'))
            else:
                return redirect(url_for('attendance'))
        else:
            flash('Invalid username or password!', 'danger')
    
    return render_template('login.html', form=form)



# Logout Route
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

# Attendance Route (Protected)
@app.route('/attendance', methods=['GET', 'POST'])
def attendance():
    # Authentication check
    if 'user_id' not in session or session['role'] != 'student':
        flash('Please login as student to access this page', 'danger')
        return redirect(url_for('login'))
    
    form = AttendanceForm()
    
    # Form submission handling
    if form.validate_on_submit():
        name = form.name.data
        matric_no = form.matric_no.data
        course = form.course.data
        
        new_record = Attendance(name=name, matric_no=matric_no, course=course)
        db.session.add(new_record)
        db.session.commit()
        
        return render_template('success.html', record=new_record)
    
    # Render template with form (for both GET and failed POST)
    return render_template('attendance.html', form=form)



@app.route('/submit_attendance', methods=['POST'])
def submit_attendance():
    try:
        # Get form data
        name = request.form.get('name')
        matric_no = request.form.get('matric_no')
        course = request.form.get('course')
        
        # Validate required fields
        if not all([name, matric_no, course]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('attendance'))
        
        # Check for existing record
        existing = StudentRecord.query.filter_by(matric_no=matric_no).first()
        if existing:
            flash('This matric number already exists!', 'warning')
            return redirect(url_for('attendance'))
        
        # Create new record
        new_record = StudentRecord(
            name=name,
            matric_no=matric_no,
            course=course,
            timestamp=datetime.now(),
            active=True
        )
        
        db.session.add(new_record)
        db.session.commit()
        flash('Attendance submitted successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting attendance: {str(e)}', 'danger')
    
    return redirect(url_for('attendance'))


# Records Route (Protected)
@app.route('/records')
def records():
    # Get all records sorted by timestamp (newest first)
    all_records = StudentRecord.query.order_by(StudentRecord.timestamp.desc()).all()
    
    # Count active and inactive records
    active_count = StudentRecord.query.filter_by(active=True).count()
    inactive_count = StudentRecord.query.filter_by(active=False).count()
    
    return render_template('records.html', 
                         records=all_records,
                         active_count=active_count,
                         inactive_count=inactive_count)


# Download PDF route
@app.route('/download/all/csv')
def download_all_csv():
    all_records = Attendance.query.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Matric Number', 'Course'])
    for record in all_records:
        writer.writerow([record.name, record.matric_no, record.course])
    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=all_attendance_records.csv'}
    )

@app.route('/download/all/pdf')
def download_all_pdf():
    all_records = Attendance.query.all()
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    y_position = 750
    p.drawString(100, y_position, "Attendance Records")
    y_position -= 30
    
    for record in all_records:
        p.drawString(100, y_position, f'Name: {record.name}')
        p.drawString(100, y_position-20, f'Matric Number: {record.matric_no}')
        p.drawString(100, y_position-40, f'Course: {record.course}')
        y_position -= 60
        if y_position < 100:  # Add new page if running out of space
            p.showPage()
            y_position = 750
    
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name='all_attendance_records.pdf',
        mimetype='application/pdf'
    )

# Delete record route
@app.route('/delete_record/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    record = StudentRecord.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Record deleted successfully'})
        


@app.route('/toggle_status/<student_id>', methods=['POST'])
def toggle_status(student_id):
    if request.is_json:
        data = request.get_json()
        new_status = data.get('new_status') == 'active'
        
        # Update the student status in your database
        student = Student.query.get(student_id)
        if student:
            student.active = new_status
            db.session.commit()
            
            # Get updated counts
            total = Student.query.count()
            active = Student.query.filter_by(active=True).count()
            inactive = total - active
            
            return jsonify({
                'success': True,
                'message': 'Status updated successfully',
                'new_status': new_status,
                'new_counts': {
                    'total': total,
                    'active': active,
                    'inactive': inactive
                }
            })
    
    return jsonify({'success': False, 'message': 'Invalid request'}), 400



if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run()

