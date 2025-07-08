import os
import numpy as np
from keras.models import load_model
from PIL import Image
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

# Load environment variables from .env

load_dotenv()

# Configure Google Generative AI with API Key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
db = SQLAlchemy()
# Initialize the Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = "my-secrets"
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///video-meeting.db"
db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


# Load the pre-trained model
model_path = './skin.keras'  # Adjust the path to your model
DermaNet = load_model(model_path)

# Define class labels
classes = {
    4: 'Nevus',
    6: 'Melanoma',
    2: 'Seborrheic Keratosis',
    1: 'Basal Cell Carcinoma',
    5: 'Vascular Lesion',
    0: 'Actinic Keratosis',
    3: 'Dermatofibroma'
}

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
    password = PasswordField(label="Password", validators=[DataRequired()])

@login_manager.user_loader
def load_user(user_id):
    return Register.query.get(int(user_id))


@app.route("/login", methods=["POST", "GET"])
def login():
    form = LoginForm()
    if request.method == "POST" and form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        user = Register.query.filter_by(email=email, password=password).first()
        if user:
            login_user(user)
            return redirect(url_for("dashboard"))

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
        
        new_user = Register(
            email=form.email.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            username=form.username.data,
            password=form.password.data
        )
        db.session.add(new_user)
        db.session.commit()
        flash("Account created successfully! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", form=form)



@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", first_name=current_user.first_name, last_name=current_user.last_name)



@app.route("/meeting")
@login_required
def meeting():
    return render_template("meeting.html", username=current_user.username)


@app.route("/join", methods=["GET", "POST"])
@login_required
def join():
    if request.method == "POST":
        room_id = request.form.get("roomID")
        return redirect(f"/meeting?roomID={room_id}")

    return render_template("join.html")

# Image preprocessing function
def preprocess_image(image):
    if image.mode == 'RGBA':
        image = image.convert('RGB')
    image = image.resize((28, 28))  # Adjust size as per your model
    image_array = np.array(image) / 255.0  # Normalize
    image_array = np.expand_dims(image_array, axis=0)  # Add batch dimension
    return image_array

@app.route('/')
def homepage():
    return render_template('index.html')

# Define the main route

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
        img_array = preprocess_image(img)

        # Make prediction
        prediction = DermaNet.predict(img_array)
        pred_label = np.argmax(prediction, axis=1)[0]
        pred_class = classes[pred_label]

        return render_template('result.html', class_name=pred_class, image_path=filename)

    return render_template('upload.html')




def get_gemini_response(question):
    model = genai.GenerativeModel('gemini-pro')
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