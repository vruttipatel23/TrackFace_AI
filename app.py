from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ARRAY, Float
import numpy as np
import cv2
import os
from datetime import datetime
from insightface.app import FaceAnalysis
from scipy.spatial.distance import cosine
import csv
from io import StringIO

app = Flask(__name__)
app.secret_key = "facetrack_secret_key_123" 

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# DATABASE CONFIG 
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Vrutti%402309@localhost:5432/facetrack_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# MODELS
class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    enrollment_no = db.Column(db.String(50), unique=True, nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    year = db.Column(db.String(10), nullable=False)
    semester = db.Column(db.String(10), nullable=False)
    password = db.Column(db.Text, nullable=False) 
    face_embedding = db.Column(ARRAY(Float)) 

class Faculty(db.Model):
    __tablename__ = 'faculty'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    year = db.Column(db.String(10), nullable=True)      
    semester = db.Column(db.String(10), nullable=True)  

class AttendanceSession(db.Model):
    __tablename__ = 'attendance_sessions'
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    year = db.Column(db.String(10), nullable=False)
    semester = db.Column(db.String(10), nullable=False)
    faculty_email = db.Column(db.String(100))
    records = db.relationship('AttendanceRecord', backref='session_ref', lazy=True)

class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_records'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_sessions.id'))
    enrollment_no = db.Column(db.String(50), nullable=False)
    student_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False) 
    error_reports = db.relationship('AttendanceError', backref='record_ref', lazy=True)

class AttendanceError(db.Model):
    __tablename__ = 'attendance_errors'
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('attendance_records.id'))
    student_enrollment = db.Column(db.String(50))
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending')

# AI SETUP 
face_app = FaceAnalysis(name="buffalo_l", providers=['CPUExecutionProvider'])
face_app.prepare(ctx_id=-1, det_size=(1280, 1280)) 
def _l2norm(v): return v / (np.linalg.norm(v) + 1e-12)

# NAVIGATION AND LOGIN ROUTES 
@app.route('/')
def home(): return render_template('Home.html')

@app.route('/register')
def register(): return render_template('Register.html')

@app.route('/register-form')
def register_form(): return render_template('Register_Form.html')

@app.route('/login')
def login(): return render_template('Login.html')

@app.route('/login-form')
def login_form(): return render_template('Login_Form.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# REGISTRATION LOGIC 
@app.route('/register-faculty', methods=['POST'])
def handle_faculty_registration():
    try:
        new_fac = Faculty(
            full_name=request.form.get('full_name'),
            email=request.form.get('email'),
            subject=request.form.get('subject'),
            year=request.form.get('year') or "N/A",
            semester=request.form.get('semester') or "N/A"
        )
        db.session.add(new_fac)
        db.session.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/register-student', methods=['POST'])
def handle_student_registration():
    try:
        emb_list = []
        files = request.files.getlist('photos')
        for file in files:
            img = cv2.imdecode(np.frombuffer(file.read(), np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                faces = face_app.get(img)
                if faces:
                    f = max(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
                    emb = f.normed_embedding if hasattr(f, "normed_embedding") else _l2norm(f.embedding)
                    emb_list.append(emb)
        
        if len(emb_list) < 3:
            return jsonify({"status": "error", "message": "At least 3 clear face photos required"}), 400
        
        avg_emb = _l2norm(np.mean(np.vstack(emb_list), axis=0)).tolist()
        new_std = Student(
            full_name=request.form.get('full_name'),
            enrollment_no=request.form.get('enroll'),
            gender=request.form.get('gender'),
            year=request.form.get('year'),
            semester=request.form.get('semester'),
            password=request.form.get('password'),
            face_embedding=avg_emb
        )
        db.session.add(new_std)
        db.session.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

# LOGIN & DASHBOARDS 
@app.route('/login-process', methods=['POST'])
def handle_login():
    try:
        role = request.args.get('role')
        identifier = request.form.get('identifier')
        secret = request.form.get('secret')
        
        if role == 'faculty':
            if secret == "123":
                user = Faculty.query.filter_by(email=identifier).first()
                if user:
                    session['faculty_email'] = user.email
                    session['faculty_name'] = user.full_name
                    return jsonify({"status": "success", "redirect": url_for('faculty_dashboard')})
            return jsonify({"status": "error", "message": "Invalid Credentials"}), 401
        else:
            user = Student.query.filter_by(enrollment_no=identifier).first()
            if user and user.password == secret:
                session['enrollment_no'] = user.enrollment_no
                session['student_name'] = user.full_name
                return jsonify({"status": "success", "redirect": url_for('student_dashboard')})
            return jsonify({"status": "error", "message": "Invalid Enrollment or Password"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/faculty-dashboard')
def faculty_dashboard():
    if 'faculty_email' not in session: return redirect(url_for('login'))
    return render_template('Faculty_Dashboard.html', name=session.get('faculty_name'))

@app.route('/student-dashboard')
def student_dashboard():
    if 'enrollment_no' not in session: return redirect(url_for('login'))
    enroll = session['enrollment_no']
    history = db.session.query(AttendanceRecord, AttendanceSession).join(
        AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id
    ).filter(AttendanceRecord.enrollment_no == enroll).all()

    subject_data = {}
    for rec, sess in history:
        sub = sess.subject
        if sub not in subject_data: subject_data[sub] = {'total': 0, 'present': 0}
        subject_data[sub]['total'] += 1
        if rec.status == 'Present': subject_data[sub]['present'] += 1

    for sub in subject_data:
        total = subject_data[sub]['total']
        present = subject_data[sub]['present']
        subject_data[sub]['percent'] = round((present / total * 100), 1) if total > 0 else 0

    return render_template('Student_Dashboard.html', records=history, subject_stats=subject_data, name=session.get('student_name'))

# ATTENDANCE PROCESSING 
@app.route('/upload-classphoto')
def upload_classphoto():
    if 'faculty_email' not in session: return redirect(url_for('login'))
    fac = Faculty.query.filter_by(email=session['faculty_email']).all()
    subs = list(set([f.subject for f in fac]))
    return render_template('Upload_ClassPhoto.html', subjects=subs, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/process-classphoto', methods=['POST'])
def process_classphoto():

    if 'faculty_email' not in session:
        return jsonify({"status": "error"}), 401

    try:
        subject = request.form.get('subject')
        date = request.form.get('date')
        year = request.form.get('year')
        semester = request.form.get('semester')

        files = request.files.getlist('class_photos')

        new_sess = AttendanceSession(
            subject=subject,
            date=date,
            year=year,
            semester=semester,
            faculty_email=session['faculty_email']
        )
        db.session.add(new_sess)
        db.session.flush()

        all_std = Student.query.filter_by(
            year=year,
            semester=semester
        ).all()

        found = set()
        for index, f in enumerate(files):

            img = cv2.imdecode(
                np.frombuffer(f.read(), np.uint8),
                cv2.IMREAD_COLOR
            )
            if img is None:
                continue

            h, w = img.shape[:2]
            img_to_process = cv2.resize(
                img, (w * 2, h * 2),
                interpolation=cv2.INTER_CUBIC
            ) if w < 1000 else img

            faces = face_app.get(img_to_process)
            for face in faces:

                bbox = face.bbox.astype(int)
                emb = face.normed_embedding if hasattr(face, "normed_embedding") else _l2norm(face.embedding)

                box_color = (0, 0, 255)
                student_label = "Unknown"

                for s in all_std:
                    if s.face_embedding and (1 - cosine(emb, np.array(s.face_embedding))) > 0.3:
                        found.add(s.enrollment_no)
                        box_color = (0, 255, 0)
                        student_label = s.full_name
                        break
                cv2.rectangle(img_to_process,
                              (bbox[0], bbox[1]),
                              (bbox[2], bbox[3]),
                              box_color, 2)
                cv2.putText(img_to_process,
                            student_label,
                            (bbox[0], bbox[1]-10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            box_color,
                            2)
            filename = f"detected_{new_sess.id}_{index}.jpg"
            cv2.imwrite(os.path.join(UPLOAD_FOLDER, filename), img_to_process)

        # Save attendance records
        for s in all_std:
            status = "Present" if s.enrollment_no in found else "Absent"
            db.session.add(
                AttendanceRecord(
                    session_id=new_sess.id,
                    enrollment_no=s.enrollment_no,
                    student_name=s.full_name,
                    status=status
                )
            )
        db.session.commit()
        return redirect(url_for(
            'attendance_report',
             subject=subject,
             year=year,
             semester=semester
            
        ))
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/attendance-report/<subject>/<year>/<semester>')
def attendance_report(subject, year, semester):
    if 'faculty_email' not in session:
        return redirect(url_for('login'))

    all_sessions = AttendanceSession.query.filter_by(
        subject=subject,
        year=year,
        semester=semester,
        faculty_email=session['faculty_email']
    ).order_by(AttendanceSession.date).all()

    if not all_sessions:
        flash("No attendance sessions found!", "warning")
        return redirect(url_for('faculty_dashboard'))

    students = Student.query.filter_by(
        year=year,
        semester=semester
    ).all()

    table_data = []
    for student in students:
        row = {
            "enrollment_no": student.enrollment_no,
            "student_name": student.full_name,
            "attendance": [],
            "percentage": 0
        }

        present_count = 0

        for sess in all_sessions:
            record = AttendanceRecord.query.filter_by(
                session_id=sess.id,
                enrollment_no=student.enrollment_no
            ).first()

            if record:
                row["attendance"].append(record.status)
                if record.status == "Present":
                    present_count += 1
            else:
                row["attendance"].append("-")

        total_classes = len(all_sessions)
        row["percentage"] = round((present_count / total_classes) * 100, 1) if total_classes > 0 else 0

        table_data.append(row)

    return render_template(
    "Attendance_Report.html",
    sessions=all_sessions,
    table_data=table_data,
    subject=subject,
    year=year,
    semester=semester
)

@app.route('/download-report/<subject>/<year>/<semester>')
def download_report(subject, year, semester):

    if 'faculty_email' not in session:
        return redirect(url_for('login'))

    all_sessions = AttendanceSession.query.filter_by(
        subject=subject,
        year=year,
        semester=semester,
        faculty_email=session['faculty_email']
    ).order_by(AttendanceSession.date).all()

    if not all_sessions:
        flash("No attendance sessions found!", "warning")
        return redirect(url_for('faculty_dashboard'))

    dates = [s.date for s in all_sessions]

    students = Student.query.filter_by(
        year=year,
        semester=semester
    ).all()

    data = StringIO()
    writer = csv.writer(data)

    writer.writerow(["Subject", subject])
    writer.writerow(["Year", year])
    writer.writerow(["Semester", semester])
    writer.writerow([])

    header = ["Enrollment No", "Student Name"] + dates + ["Percentage"]
    writer.writerow(header)

    for student in students:
        row = [student.enrollment_no, student.full_name]
        present_count = 0

        for sess in all_sessions:
            record = AttendanceRecord.query.filter_by(
                session_id=sess.id,
                enrollment_no=student.enrollment_no
            ).first()

            if record:
                status = "P" if record.status == "Present" else "A"
                row.append(status)
                if record.status == "Present":
                    present_count += 1
            else:
                row.append("-")

        total_classes = len(all_sessions)
        percentage = round((present_count / total_classes) * 100, 1) if total_classes > 0 else 0
        row.append(f"{percentage}%")

        writer.writerow(row)
    output = data.getvalue()
    data.close()

    return Response(
        output,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=Full_Attendance_{subject}.csv"
        }
    )

@app.route('/report-error/<int:record_id>', methods=['GET', 'POST'])
def report_error(record_id):
    if 'enrollment_no' not in session: return redirect(url_for('login'))
    rec = AttendanceRecord.query.get_or_404(record_id)
    if request.method == 'POST':
        db.session.add(AttendanceError(record_id=record_id, student_enrollment=session['enrollment_no'], reason=request.form.get('reason')))
        db.session.commit()
        flash('Your request has been submitted successfully to the faculty!', 'success')
        return redirect(url_for('student_dashboard'))
    return render_template('Report_Error.html', record=rec)

@app.route('/faculty/review-requests')
def review_requests():
    if 'faculty_email' not in session: return redirect(url_for('login'))

    data = db.session.query(AttendanceError, AttendanceRecord, AttendanceSession).join(
        AttendanceRecord, AttendanceError.record_id == AttendanceRecord.id).join(
        AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id
    ).filter(AttendanceSession.faculty_email == session['faculty_email'], AttendanceError.status == 'Pending').all()
    return render_template('Review_Requests.html', requests=data)

@app.route('/faculty/approve-request/<int:error_id>')
def approve_request(error_id):
    if 'faculty_email' not in session: return redirect(url_for('login'))
    err = AttendanceError.query.get_or_404(error_id)
    rec = AttendanceRecord.query.get(err.record_id)
    rec.status = 'Present'; err.status = 'Resolved'; db.session.commit()
    return redirect(url_for('review_requests'))

@app.route('/faculty/reject-request/<int:error_id>')
def reject_request(error_id):
    if 'faculty_email' not in session: return redirect(url_for('login'))
    err = AttendanceError.query.get_or_404(error_id)
    err.status = 'Rejected'; db.session.commit()
    flash("Request Rejected Successfully", "error")
    return redirect(url_for('review_requests'))

@app.route('/faculty/all-reports')
def all_reports():
    if 'faculty_email' not in session:
        return redirect(url_for('login'))

    reports = db.session.query(
        AttendanceSession.subject,
        AttendanceSession.year,
        AttendanceSession.semester
    ).filter_by(
        faculty_email=session['faculty_email']
    ).distinct().all()

    return render_template('All_Reports_List.html', reports=reports)

@app.route('/faculty/manual-fix', methods=['GET', 'POST'])
def manual_fix():
    if 'faculty_email' not in session: return redirect(url_for('login'))
    fac_email = session['faculty_email']
    subjects = db.session.query(AttendanceSession.subject).filter_by(faculty_email=fac_email).distinct().all()
    subjects = [s[0] for s in subjects]
    return render_template('Manual_Fix.html', subjects=subjects)

@app.route('/daily_report/<int:session_id>')
def daily_report(session_id):

    if 'faculty_email' not in session:
        return redirect(url_for('login'))

    session_data = AttendanceSession.query.get_or_404(session_id)

    records = AttendanceRecord.query.filter_by(
        session_id=session_id
    ).all()

    images = [
        f for f in os.listdir(UPLOAD_FOLDER)
        if f.startswith(f"detected_{session_id}_")
    ]

    return render_template(
        "Daily_Report.html",
        session_data=session_data,
        records=records,
        images=images
    )

@app.route('/faculty/process-manual-fix', methods=['POST'])
def process_manual_fix():
    if 'faculty_email' not in session: return jsonify({"status": "error"}), 401
    enroll = request.form.get('enroll'); subject = request.form.get('subject')
    date = request.form.get('date'); new_status = request.form.get('status')
    try:
        sess = AttendanceSession.query.filter_by(subject=subject, date=date, faculty_email=session['faculty_email']).first()
        if not sess:
            flash(f"No attendance session found for {subject} on {date}", "error")
            return redirect(url_for('manual_fix'))
        record = AttendanceRecord.query.filter_by(session_id=sess.id, enrollment_no=enroll).first()
        if record:
            record.status = new_status
            db.session.commit()
            flash(f"Attendance for {enroll} updated to {new_status}!", "success")
        else:
            flash(f"Student {enroll} not found in this class session", "error")
        return redirect(url_for('manual_fix'))
    except Exception as e:
        db.session.rollback(); flash(f"Error: {str(e)}", "error"); return redirect(url_for('manual_fix'))

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True)