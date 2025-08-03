from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response, send_file, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timezone
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
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import DataRequired
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

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
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Should be a long, random string
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///attendance.db'  # or your DB URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = True

# Initialize database and migration
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User Model
class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    active = db.Column(db.Boolean, default=True)  # THIS MUST EXIST

    @property
    def is_active(self):
        return self.active

# User loader function required by Flask-Login
@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    if user and user.active:  # Use your existing active attribute
        return user
    return None

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
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    accuracy = db.Column(db.Float)
    location_name = db.Column(db.String(200))

    def __repr__(self):
        return f'<StudentRecord {self.matric_no}>'
    
# Attendance Model
class Attendance(db.Model):
    __tablename__ = 'attendance'  # Explicit table name
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    matric_no = db.Column(db.String(50), nullable=False)
    course = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(DateTime, default=datetime.utcnow)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    accuracy = db.Column(db.Float)
    location_name = db.Column(db.String(200))

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

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    role = SelectField('Role', choices=[('student', 'Student'), ('lecturer', 'Lecturer')], validators=[DataRequired()])

# Home Route
@app.route('/')
def index():
    return render_template('index.html')

# Register Route
@app.route('/register', methods=['GET', 'POST'])
def register():
    lecturer_exists = User.query.filter_by(role='lecturer').first() is not None
    form = RegistrationForm()
    if form.validate_on_submit():
        role = request.form.get('role')
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not role:
            flash('Role is required', 'danger')
            return redirect(url_for('register'))
        
        if not username or not password:
            flash('Username and password are required', 'danger')
            return redirect(url_for('register'))
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists!', 'danger')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password, role=role)
        
        db.session.add(new_user)
        try:
            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except IntegrityError:
            db.session.rollback()
            flash('Registration failed. Please try again.', 'danger')
    
    return render_template('register.html', form=form, lecturer_exists=lecturer_exists)
    
# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login successful!', 'success')
            
            if user.role == 'lecturer':
                return redirect(url_for('records'))
            else:
                return redirect(url_for('attendance'))
        else:
            flash('Invalid username or password!', 'danger')
    
    return render_template('login.html', form=form)

# Logout Route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))


# Attendance Route (Protected)
@app.route('/attendance', methods=['GET', 'POST'])
@login_required
def attendance():
    if current_user.role != 'student':
        flash('Please login as student to access this page', 'danger')
        return redirect(url_for('login'))
    
    form = AttendanceForm()
    
    if form.validate_on_submit():
        name = form.name.data
        matric_no = form.matric_no.data
        course = form.course.data
        
        new_record = Attendance(name=name, matric_no=matric_no, course=course)
        db.session.add(new_record)
        db.session.commit()
        
        return render_template('success.html', record=new_record)
    
    return render_template('attendance.html', form=form)

@app.route('/submit_attendance', methods=['POST'])
@login_required
def submit_attendance():
    try:
        # Required fields
        name = request.form.get('name')
        matric_no = request.form.get('matric_no')
        course = request.form.get('course')
        
        # Location data
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        accuracy = request.form.get('accuracy')
        location_name = request.form.get('location_name')
        
        if not all([name, matric_no, course]):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'Name, Matric Number and Course are required!'
                }), 400
            flash('Name, Matric Number and Course are required!', 'danger')
            return redirect(url_for('attendance'))
        
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
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            accuracy=float(accuracy) if accuracy else None,
            location_name=location_name,
            active=True
        )

        db.session.add(new_record)
        db.session.commit()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': 'Attendance submitted successfully!',
                'record': {
                    'id': new_record.id,
                    'name': name,
                    'matric_no': matric_no,
                    'course': course,
                    'latitude': latitude,
                    'longitude': longitude,
                    'accuracy': accuracy,
                    'location_name': location_name
                }
            })

        flash('Attendance submitted successfully!', 'success')
        return redirect(url_for('attendance'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error submitting attendance: {str(e)}", exc_info=True)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': f'Error submitting attendance: {str(e)}'
            }), 500
        
        flash(f'Error submitting attendance: {str(e)}', 'danger')
        return redirect(url_for('attendance'))


# Records Route (Protected)
@app.route('/records')
@login_required
def records():
    if current_user.role != 'lecturer':
        flash('You need lecturer privileges to access this page', 'danger')
        return redirect(url_for('index'))
    
    all_records = StudentRecord.query.order_by(StudentRecord.timestamp.desc()).all()
    active_count = StudentRecord.query.filter_by(active=True).count()
    inactive_count = StudentRecord.query.filter_by(active=False).count()
    
    # Prepare location data for each record
    records_with_location = []
    for record in all_records:
        location_data = {
            'latitude': record.latitude,
            'longitude': record.longitude,
            'accuracy': record.accuracy,
            'location_name': record.location_name
        }
        records_with_location.append((record, location_data))
    
    return render_template('records.html', 
                         records=all_records,
                         records_with_location=records_with_location,
                         active_count=active_count,
                         inactive_count=inactive_count)

# Download CSV route
@app.route('/download/all/csv')
@login_required
def download_all_csv():
    try:
        all_records = StudentRecord.query.order_by(StudentRecord.timestamp.desc()).all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow([
            'No.', 'Name', 'Matric Number', 'Course',
            'Date', 'Time', 'Status', 'Latitude', 
            'Longitude', 'Accuracy', 'Location Name', 'Record ID'
        ])
        
        if not all_records:
            writer.writerow(['No attendance records found', '', '', '', '', '', '', '', '', '', ''])
        else:
            for idx, record in enumerate(all_records, 1):
                writer.writerow([
                    idx,
                    record.name,
                    record.matric_no,
                    record.course,
                    record.timestamp.strftime('%Y-%m-%d'),
                    record.timestamp.strftime('%H:%M:%S'),
                    'Active' if record.active else 'Inactive',
                    record.latitude if record.latitude else 'N/A',
                    record.longitude if record.longitude else 'N/A',
                    record.accuracy if record.accuracy else 'N/A',
                    record.location_name if record.location_name else 'N/A',
                    record.id
                ])
        
        output.seek(0)
        
        filename = f"attendance_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'text/csv; charset=utf-8'
            }
        )
    except Exception as e:
        app.logger.error(f"CSV export error: {str(e)}")
        flash('Error generating CSV file', 'danger')
        return redirect(url_for('records'))

@app.route('/download/all/pdf')
@login_required
def download_all_pdf():
    try:
        all_records = StudentRecord.query.order_by(StudentRecord.timestamp.desc()).all()
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=30,
            title="Student Attendance Records"
        )
        
        # Updated header with location columns
        data = [['#', 'Name', 'Matric No.', 'Course', 'Date', 'Time', 'Status', 
                'Latitude', 'Longitude', 'Accuracy', 'Location', 'Record ID']]
        
        if not all_records:
            data.append(['No attendance records found', '', '', '', '', '', '', '', '', '', ''])
        else:
            for idx, record in enumerate(all_records, 1):
                data.append([
                    str(idx),
                    record.name,
                    record.matric_no,
                    record.course,
                    record.timestamp.strftime('%Y-%m-%d'),
                    record.timestamp.strftime('%H:%M:%S'),
                    'Active' if record.active else 'Inactive',
                    str(record.latitude) if record.latitude else 'N/A',
                    str(record.longitude) if record.longitude else 'N/A',
                    str(record.accuracy) if record.accuracy else 'N/A',
                    record.location_name if record.location_name else 'N/A',
                    str(record.id)
                ])
        
        # Adjusted column widths to accommodate new columns
        col_widths = ['4%', '15%', '10%', '12%', '10%', '8%', '8%', '8%', '8%', '8%', '9%']
        table = Table(data, colWidths=col_widths, repeatRows=1)
        
        style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 8),  # Smaller font size to fit more columns
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#ecf0f1')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bdc3c7')),
            ('FONTSIZE', (0,1), (-1,-1), 7),  # Smaller font size for data rows
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('WORDWRAP', (0,0), (-1,-1)),  # Enable word wrap for long text
        ])
        table.setStyle(style)
        
        elements = []
        styles = getSampleStyleSheet()
        
        title = Paragraph("<b>STUDENT ATTENDANCE RECORDS WITH LOCATION DATA</b>", styles['Title'])
        elements.append(title)
        
        gen_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        info_text = f"<b>Generated on:</b> {gen_date} | <b>Total Records:</b> {len(all_records)}"
        info_para = Paragraph(info_text, styles['Normal'])
        elements.append(info_para)
        
        elements.append(Spacer(1, 12))  # Smaller spacer
        
        # Add a note about location data
        note = Paragraph("<i>Note: Location data is captured when available during attendance submission</i>", 
                         styles['Italic'])
        elements.append(note)
        elements.append(Spacer(1, 12))
        
        elements.append(table)
        
        doc.build(elements)
        buffer.seek(0)
        
        filename = f"attendance_records_with_location_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        return Response(
            buffer.getvalue(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'application/pdf'
            }
        )
    except Exception as e:
        app.logger.error(f"PDF export error: {str(e)}")
        flash('Error generating PDF file', 'danger')
        return redirect(url_for('records'))
    

# Delete record route
@app.route('/delete_record/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    if current_user.role != 'lecturer':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
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
    app.run(host='0.0.0.0', port=5000)
