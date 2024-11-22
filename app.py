import os
from os.path import join, dirname
from dotenv import load_dotenv
from flask import (
    Flask,
    request,
    render_template,
    redirect,
    url_for,
    flash,
    session,
    jsonify
)
from pymongo import MongoClient
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from datetime import datetime
from bson import ObjectId
import urllib.parse
import urllib

# Load environment variables
dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME = os.environ.get("DB_NAME")

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]

app = Flask(__name__)
app.secret_key = 'geforce'

#format idr
def format_rupiah(value):
    return "Rp{:,.0f}".format(value).replace(',', '.')
app.jinja_env.filters['rupiah'] = format_rupiah

#setting untuk folder tempat image di upload
UPLOAD_FOLDER = 'static/img/upload'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

#homepage, pengunjung bisa liat homepage tanpa login
@app.route('/')
def home():
    products = list(db.products.find())
    return render_template('index.html', products=products)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = db.users.find_one({'username': username})

        if user and check_password_hash(user['password'], password):
            session['username'] = username
            session['role'] = user['role']  
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm-password')

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register')) 

        existing_user = db.users.find_one({'username': username})
        
        if existing_user:
            flash('Username already exists', 'error')
        else:
            hashed_password = generate_password_hash(password)

            user_data = {
                'username': username,
                'password': hashed_password,
                'role': 'user' 
            }
            db.users.insert_one(user_data)
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get('role') == 'admin':
        total_users = db.users.count_documents({})
        total_products = db.products.count_documents({})
        return render_template('admin/index.html', total_users=total_users, total_products=total_products)
    return redirect(url_for('login'))

@app.route('/user_dashboard')
def user_dashboard():
    products = list(db.products.find())
    if session.get('role') == 'user':
        return render_template('index.html', products=products)
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('role', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# <====ADMIN ROUTES====> #

#PRODUCTS
@app.route('/admin/products')
def admin_products():
    if session.get('role') != 'admin':
        flash('Only admins can view this page.', 'error')
        return redirect(url_for('show_products'))

    products = list(db.products.find())
    return render_template('admin/products/index.html', products=products)



if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)