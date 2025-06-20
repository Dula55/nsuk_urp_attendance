from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from flask import Response, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import io
import csv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


Base = declarative_base()

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///attendance.db'
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
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
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
    
    return render_template('login.html')

# Logout Route
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

# Attendance Route (Protected)
@app.route('/attendance', methods=['GET', 'POST'])
def attendance():
    if 'user_id' not in session or session['role'] != 'student':
        flash('Please login as student to access this page', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form['name']
        matric_no = request.form['matric_no']
        course = request.form['course']
        
        if not name or not matric_no or not course:
            flash('All fields are required!', 'danger')
            return redirect(url_for('attendance'))
            
        new_record = Attendance(name=name, matric_no=matric_no, course=course)
        db.session.add(new_record)
        db.session.commit()
        
        return render_template('success.html', record=new_record)
    
    return render_template('attendance.html')


@app.route('/submit_attendance', methods=['POST'])
def submit_attendance():
    name = request.form.get('name')
    matric_no = request.form.get('matric_no')
    course = request.form.get('course')
    
    # Check if student exists and is active
    student = Student.query.filter_by(matric_no=matric_no).first()
    
    if student and not student.active:
        flash('Your account is currently deactivated. Please contact administrator.', 'danger')
        return redirect(url_for('attendance'))
    
    if student:
        # Update existing record
        student.name = name
        student.course = course
        student.timestamp = datetime.utcnow()
    else:
        # Create new record
        student = Student(
            name=name,
            matric_no=matric_no,
            course=course,
            active=True  # Default to active when creating new
        )
        db.session.add(student)
    
    db.session.commit()
    flash('Attendance submitted successfully!', 'success')
    return redirect(url_for('attendance'))


# Records Route (Protected)
@app.route('/records')
def records():
    records = Student.query.order_by(Student.timestamp.desc()).all()
    active_count = Student.query.filter_by(active=True).count()
    inactive_count = Student.query.filter_by(active=False).count()
    return render_template('records.html', 
                         records=records,
                         active_count=active_count,
                         inactive_count=inactive_count,
                         now=datetime.utcnow())


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
@app.route('/delete/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    record = Attendance.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()
    flash('Record deleted successfully!', 'success')
    return redirect(url_for('records'))



@app.route('/toggle_status/<int:student_id>', methods=['POST'])
def toggle_status(student_id):
    student = Student.query.get_or_404(student_id)
    action = request.form.get('action')
    
    if action == 'activate':
        student.active = True
        flash(f'{student.name}\'s account has been activated successfully!', 'success')
    elif action == 'deactivate':
        student.active = False
        flash(f'{student.name}\'s account has been deactivated successfully!', 'warning')
    
    db.session.commit()
    return redirect(url_for('records'))



if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run()

