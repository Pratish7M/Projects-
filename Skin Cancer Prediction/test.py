import os
import numpy as np
from keras.models import load_model
from PIL import Image
import sqlite3
from dotenv import load_dotenv
import textwrap
import google.generativeai as genai
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, EmailField
from wtforms.validators import DataRequired, Length
from flask_sqlalchemy import SQLAlchemy
from flask_login import login_user, LoginManager, login_required, current_user, logout_user
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
# Load environment variables from .env

load_dotenv()
DB_PATH = r"C:\Users\HP\OneDrive\Desktop\Major Project Updated\instance\video-meeting.db"
# Configure Google Generative AI with API Key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
db = SQLAlchemy()
# Initialize the Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = "my-secrets"
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///video-meeting.db?check_same_thread=False"

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)
today = datetime.today().date()


# Load the pre-trained model
HybridCNN = load_model('./skin_cancerr.h5')

# Define class labels
classes = {
    4: 'Nevus',
    6: 'Melanoma',
    2: 'Seborrheic Keratosis',
    1: 'Basal Cell Carcinoma',
    5: 'Vascular Lesion',
    0: 'Actinic Keratosis',
    3: 'Dermatofibroma',
    7:'Normal Class'
}

def create_database():
    """Create the database and bookings table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create the bookings table if it doesn't exist
    query = '''CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    phone TEXT,
                    date TEXT NOT NULL,
                    message TEXT
                )'''
    
    cursor.execute(query)
    conn.commit()
    conn.close()


def save_booking(name, email, phone, date, message):
    """Insert booking data into the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check the number of bookings for the selected date
    query_check = "SELECT COUNT(*) FROM bookings WHERE date = ?"
    cursor.execute(query_check, (date,))
    booking_count = cursor.fetchone()[0]

    # Allow only 15 bookings per day
    if booking_count >= 15:
        flash("Sorry, the maximum number of bookings for this day has been reached. Please select another date.", "error")
        conn.close()
        return False

    # SQL query to insert booking data into the bookings table
    query_insert = '''INSERT INTO bookings (name, email, phone, date, message)
                      VALUES (?, ?, ?, ?, ?)'''
    
    cursor.execute(query_insert, (name, email, phone, date, message))
    conn.commit()
    conn.close()

    return True

# Call the function to create the database and table if it doesn't exist
create_database()


def email_exists(email):
    """Check if the email exists in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Query to check if the email exists in the users table (update with your actual table name)
    query = "SELECT 1 FROM register WHERE email = ? LIMIT 1"
    cursor.execute(query, (email,))
    result = cursor.fetchone()

    conn.close()

    return result is not None 

class Register(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(50), unique=True, nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)

    def is_active(self):
        return True

    def get_id(self):
        return str(self.id)

    def is_authenticated(self):
        return True


with app.app_context():
    db.create_all()


class RegistrationForm(FlaskForm):
    email = EmailField(label='Email', validators=[DataRequired()])
    first_name = StringField(label="First Name", validators=[DataRequired()])
    last_name = StringField(label="Last Name", validators=[DataRequired()])
    username = StringField(label="Username", validators=[DataRequired(), Length(min=4, max=20)])
    password = PasswordField(label="Password", validators=[DataRequired(), Length(min=8, max=20)])


class LoginForm(FlaskForm):
    email = EmailField(label='Email', validators=[DataRequired()])
    password = PasswordField(label="Password", validators=[DataRequired(), Length(min=8, max=20)])

    
@login_manager.user_loader
def load_user(user_id):
    return Register.query.get(int(user_id))


@app.route("/login", methods=["POST", "GET"])
def login():
    form = LoginForm()
    if request.method == "POST" and form.validate_on_submit():
        email = form.email.data
        password = form.password.data

        # Directly compare plain text passwords
        user = Register.query.filter_by(email=email, password=password).first()

        if user:  # No hashing, direct match
            login_user(user)  # Logs the user in
            flash("Login successful!", "success")

            if user.email.strip() == "admin@gmail.com":  # Ensure no spaces
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password. Please try again.", "danger")

    return render_template("login.html", form=form)





@app.route("/logout", methods=["GET"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully!", "info")
    return redirect(url_for("login"))



@app.route("/register", methods=["POST", "GET"])
def register():
    form = RegistrationForm()
    if request.method == "POST" and form.validate_on_submit():
        # Check if the email already exists
        existing_user = Register.query.filter_by(email=form.email.data).first()
        if existing_user:
            flash("This email is already registered. Please use a different email.", "danger")
            return redirect(url_for("register"))

        # Store the password as plain text (⚠ No hashing for now)
        new_user = Register(
            email=form.email.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            username=form.username.data,
            password=form.password.data  # No hashing
        )

        try:
            db.session.add(new_user)
            db.session.commit()
            flash("Account created successfully! You can now log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            db.session.rollback()  # Rollback in case of an error
            flash(f"Error: {str(e)}", "danger")
        finally:
            db.session.close()  # Ensure session is closed to release lock

    return render_template("register.html", form=form)




@app.route("/dashboard")
@login_required
def dashboard():

    return render_template("dashboard.html", first_name=current_user.first_name, last_name=current_user.last_name)


def send_email(recipient_email, subject, message):
    sender_email = "chavansiddhesh105477@gmail.com"  # Replace with your Gmail address
    password = "irld qqpj tmvx lsih"
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(message, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


@app.route("/admin/dashboard", methods=["GET", "POST"])
@login_required
def admin_dashboard():
    if not current_user.is_authenticated or current_user.username != "admin":
        flash("Unauthorized access!", "error")
        return redirect(url_for("homepage"))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Fetch all bookings
    cursor.execute("SELECT * FROM bookings")
    bookings = cursor.fetchall()

    # Fetch all unique email addresses
    cursor.execute("SELECT DISTINCT email FROM bookings")
    emails = [row[0] for row in cursor.fetchall()]

    conn.close()

    if request.method == "POST":
        recipient_email = request.form.get("recipient_email")
        subject = request.form.get("subject")
        message = request.form.get("message")

        if send_email(recipient_email, subject, message):
            flash("Email sent successfully!", "success")
        else:
            flash("Failed to send email.", "error")

    return render_template("admin_dashboard.html", bookings=bookings, emails=emails)





@app.route("/blood_test")
@login_required
def blood_test():
    return render_template("Blood_test.html", first_name=current_user.first_name, last_name=current_user.last_name,email=current_user.email)






@app.route("/meeting")
def meeting():
    return render_template("meeting.html")


@app.route("/join", methods=["GET", "POST"])
@login_required
def join():
    if request.method == "POST":
        room_id = request.form.get("roomID")
        return redirect(f"/meeting?roomID={room_id}")

    return render_template("join.html")

def preprocess_image(image, target_size=(28, 28)):
    # Convert RGBA images to RGB by removing the alpha channel
    if image.mode == 'RGBA':
        image = image.convert('RGB')
    # Convert grayscale images (L mode) to RGB by repeating the grayscale values across 3 channels
    elif image.mode == 'L':  # 'L' mode is for grayscale images
        image = image.convert('RGB')
        
    image = image.resize(target_size)  # Resize to the target size expected by the model
    image_array = np.array(image) / 255.0  # Normalize pixel values
    if image_array.shape[-1] != 3:  # Ensure the image has 3 color channels (RGB)
        raise ValueError("Input image must have 3 color channels (RGB).")
    
    image_array = np.expand_dims(image_array, axis=0)  # Add batch dimension
    return image_array



@app.route('/', methods=['POST', 'GET'])
def homepage():
    today = datetime.today().date()

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        date = request.form.get('date')
        message = request.form.get('message')

        if not email_exists(email):
            flash("Sorry, this email is not registered. Please register first.", "error")
            return redirect(url_for('homepage'))

        selected_date = datetime.strptime(date, "%Y-%m-%d").date()

        if selected_date < today:
            flash("Please select a valid future date for booking.", "error")
            return redirect(url_for('homepage'))

        if save_booking(name, email, phone, date, message):
            flash("Booking successfully made!", "success")

            sender_email = "chavansiddhesh105477@gmail.com"  # Replace with your Gmail address
            receiver_email = email
            password = "irld qqpj tmvx lsih"  # Replace with your Gmail password or app password

            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = receiver_email
            msg['Subject'] = "Appointment Scheduled"
            body = f"Hello {name},\n\nYour appointment is scheduled for {date}. We look forward to seeing you!\n\nBest regards,\nPratish Clinic"
            msg.attach(MIMEText(body, 'plain'))

            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                    server.login(sender_email, password)
                    server.sendmail(sender_email, receiver_email, msg.as_string())
                print("Email sent successfully!")
            except Exception as e:
                print(f"Failed to send email: {e}")
            
            return redirect(url_for('homepage'))

        return redirect(url_for('homepage'))

    return render_template('index.html', today=today)






@app.route('/upload', methods=['GET', 'POST'])
def upload_image():
    if request.method == 'POST':
        # Check if an image was uploaded
        if 'file' not in request.files:
            return "No file uploaded", 400

        file = request.files['file']
        if file.filename == '':
            return "No selected file", 400

        # Secure the filename and create uploads directory if it doesn't exist
        filename = secure_filename(file.filename)
        uploads_dir = 'static/uploads'

        if not os.path.exists(uploads_dir):
            os.makedirs(uploads_dir)

        img_path = os.path.join(uploads_dir, filename)
        print(f"Saving image to: {img_path}")  # Debug print
        file.save(img_path)  # Save the file to the uploads directory

        # Open and preprocess the image
        img = Image.open(file)
        try:
            img_array = preprocess_image(img)  # Ensure correct image format
        except ValueError as e:
            return str(e), 400  # If the image is not in RGB format, return an error

        # Make prediction using the HybridCNN model
        prediction = HybridCNN.predict(img_array)  # Model is correctly loaded here
        pred_label = np.argmax(prediction, axis=1)[0]
        pred_class = classes[pred_label]

        # Render the result page with the predicted class and image
        return render_template('result.html', class_name=pred_class, image_path=filename)

    return render_template('upload.html')

# def get_gemini_response(question):
#     model = genai.GenerativeModel('gemini-pro')
#     response = model.generate_content(question)
#     return response.text

def get_gemini_response(question):
    model = genai.GenerativeModel("models/gemini-1.5-pro-latest")
    response = model.generate_content(question)
    return response.text

# Home route
@app.route("/chat", methods=["GET", "POST"])
def chat():
    response = ""
    if request.method == "POST":
        input_text = request.form["input"]
        response = get_gemini_response(input_text)
    return render_template("chat.html", response=response)


# Run the app
if __name__ == '__main__':
    app.run(debug=True)