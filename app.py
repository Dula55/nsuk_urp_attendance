from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response, send_file
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
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from flask_wtf.csrf import CSRFProtect, generate_csrf


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
    csrf_token = generate_csrf()
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
    
    return render_template('register.html', csrf_token=csrf_token)

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
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'All fields are required!'
                }), 400
            flash('All fields are required!', 'danger')
            return redirect(url_for('attendance'))
        
        # Check for existing record
        existing = StudentRecord.query.filter_by(matric_no=matric_no).first()
        if existing:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'This matric number already exists!'
                }), 400
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
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': 'Attendance submitted successfully!',
                'record': {
                    'name': name,
                    'matric_no': matric_no,
                    'course': course
                }
            })
        
        flash('Attendance submitted successfully!', 'success')
        return redirect(url_for('attendance'))
        
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': f'Error submitting attendance: {str(e)}'
            }), 500
        
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
    try:
        # Get all attendance records with proper ordering
        all_records = Attendance.query.order_by(Attendance.timestamp.desc()).all()
        
        # Create CSV output in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write comprehensive header row
        writer.writerow([
            'No.', 'Name', 'Matric Number', 'Course',
            'Date', 'Time', 'Status', 'Record ID'
        ])
        
        # Write data rows with proper formatting
        for idx, record in enumerate(all_records, 1):
            writer.writerow([
                idx,
                record.name,
                record.matric_no,
                record.course,
                record.timestamp.strftime('%Y-%m-%d'),
                record.timestamp.strftime('%H:%M'),
                'Active' if record.active else 'Inactive',
                record.id
            ])
        
        output.seek(0)
        
        # Generate filename with current date
        filename = f"attendance_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return Response(
            output.getvalue().encode('utf-8'),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        app.logger.error(f"CSV export error: {str(e)}")
        return "Error generating CSV file", 500

@app.route('/download/all/pdf')
def download_all_pdf():
    try:
        # Get all attendance records
        all_records = Attendance.query.order_by(Attendance.timestamp.desc()).all()
        
        # Create PDF buffer
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        
        # Create data for table
        data = [
            ['#', 'Name', 'Matric No.', 'Course', 'Date', 'Time', 'Status', 'Record ID']
        ]
        
        for idx, record in enumerate(all_records, 1):
            data.append([
                str(idx),
                record.name,
                record.matric_no,
                record.course,
                record.timestamp.strftime('%Y-%m-%d'),
                record.timestamp.strftime('%H:%M'),
                'Active' if record.active else 'Inactive',
                str(record.id)
            ])
        
        # Create table with automatic column widths
        table = Table(data, repeatRows=1)
        
        # Add style
        style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#ecf0f1')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bdc3c7')),
            ('FONTSIZE', (0,1), (-1,-1), 9),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ])
        table.setStyle(style)
        
        # Build PDF elements
        elements = []
        styles = getSampleStyleSheet()
        
        # Add title
        title = Paragraph("STUDENT ATTENDANCE RECORDS", styles['Title'])
        elements.append(title)
        
        # Add generation info
        gen_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        info_text = f"Generated on: {gen_date} | Total Records: {len(all_records)}"
        info_para = Paragraph(info_text, styles['Normal'])
        elements.append(info_para)
        
        elements.append(Spacer(1, 24))
        
        # Add table
        elements.append(table)
        
        # Generate PDF
        doc.build(elements)
        buffer.seek(0)
        
        # Generate filename
        filename = f"attendance_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
    except Exception as e:
        app.logger.error(f"PDF export error: {str(e)}")
        return "Error generating PDF file", 500

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

