from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask import Response, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import io
import csv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

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
    name = db.Column(db.String(100), nullable=False)
    matric_no = db.Column(db.String(50), unique=True, nullable=False)
    course = db.Column(db.String(100), nullable=False)
    active = db.Column(db.Boolean, default=True)  # This is the field we're toggling
    
    def __repr__(self):
        return f'<Student {self.matric_no}>'
    
    
# Attendance Model
class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    matric_no = db.Column(db.String(100), nullable=False)
    course = db.Column(db.String(100), nullable=False)

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

# Records Route (Protected)
@app.route('/records')
def records():
    if 'user_id' not in session or session['role'] != 'lecturer':
        flash('Please login as lecturer to access this page', 'danger')
        return redirect(url_for('login'))
    
    all_records = Attendance.query.all()
    return render_template('records.html', records=all_records)


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
    student = Student.query.get_or_404(student_id)  # Assuming you have a Student model
    action = request.form.get('action')
    
    if action == 'activate':
        student.active = True
    elif action == 'deactivate':
        student.active = False
    
    db.session.commit()
    flash(f'Student account has been {action}d successfully!', 'success')
    return redirect(url_for('records'))



if __name__ == '__main__':
    app.run(debug=True)
