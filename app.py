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
    jsonify,
)

from flask import get_flashed_messages

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

#flash message 
@app.context_processor
def utility_processor():
    def flash_messages():
        messages = get_flashed_messages(with_categories=True)
        return messages
    return dict(flash_messages=flash_messages)


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

#PRODUCTS - INDEX
@app.route('/admin/products')
def admin_products():
    if session.get('role') != 'admin':
        flash('Only admins can view this page.', 'error')
        return redirect(url_for('show_products'))

    products = list(db.products.find())
    return render_template('admin/products/index.html', products=products)


#PRODUCTS - ADD
@app.route('/admin/products/add', methods=['GET', 'POST'])
def add_product():
    if session.get('role') != 'admin':
        flash('Only admins can add products.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        category = request.form.get('category')
        stock = request.form.get('stock')
        
        try:
            price = float(request.form.get('price'))
        except ValueError:
            flash('Invalid price value.', 'error')
            return redirect(url_for('add_product'))

        image = request.files.get('image')
        
        if not (name and description and price and image):
            flash("All fields, including the image, are required.", 'error')
            return redirect(url_for('add_product'))

        if image:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"{timestamp}_{secure_filename(image.filename)}"
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_path)

            product_data = {
                'name': name,
                'description': description,
                'category': category,
                'price': price,
                'stock': stock,
                'image_filename': filename,
                'created_at': datetime.now()
            }
            db.products.insert_one(product_data)

            flash('Product added successfully!', 'success')
            return redirect(url_for('admin_products'))
        else:
            flash('Image upload failed. Please try again.', 'error')

    return render_template('admin/products/add.html')


#PRODUCTS - EDIT
@app.route('/admin/products/edit/<product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if session.get('role') != 'admin':
        flash('Only admins can edit products.', 'error')
        return redirect(url_for('login'))

    product = db.products.find_one({'_id': ObjectId(product_id)})

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        category = request.form.get('category')
        stock = request.form.get('stock')
        price = float(request.form.get('price'))
        
        image = request.files.get('image')
        image_filename = product['image_filename']
        if image:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            image_filename = f"{timestamp}_{secure_filename(image.filename)}"
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            image.save(image_path)

        db.products.update_one(
            {'_id': ObjectId(product_id)},
            {'$set': 
                {'name': name, 
                      'category': category, 
                      'stock': stock, 
                      'description': description, 
                      'price': price, 
                      'image_filename': image_filename
                    }}
        )

        flash('Product updated successfully!', 'success')
        return redirect(url_for('admin_products'))

    return render_template('admin/products/edit.html', product=product)


#PRODUCTS - DELETE
@app.route('/admin/products/delete/<product_id>', methods=['GET'])
def delete_product(product_id):
    if session.get('role') != 'admin':
        flash('Only admins can delete products.', 'error')
        return redirect(url_for('login'))

    product = db.products.find_one({'_id': ObjectId(product_id)})

    db.products.delete_one({'_id': ObjectId(product_id)})

    image_path = os.path.join(app.config['UPLOAD_FOLDER'], product['image_filename'])
    if os.path.exists(image_path):
        os.remove(image_path)

    flash('Product deleted successfully!', 'success')
    return redirect(url_for('admin_products'))


#USERS - INDEX
@app.route('/admin/users')
def admin_users():
    if session.get('role') != 'admin':
        flash('Only admins can view users.', 'error')
        return redirect(url_for('login'))

    users = list(db.users.find())
    return render_template('admin/users/index.html', users=users)


#USERS - ADD
@app.route('/admin/users/add', methods=['GET', 'POST'])
def add_user():
    if session.get('role') != 'admin':
        flash('Only admins can add users.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm-password')
        role = request.form.get('role', 'user') 

        print(f"Received username: {username}")
        print(f"Received password: {password}")
        print(f"Received confirm_password: {confirm_password}")
        print(f"Received role: {role}")

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('add_user'))

        existing_user = db.users.find_one({'username': username})
        
        if existing_user:
            flash('Username already exists', 'error')
        else:
            hashed_password = generate_password_hash(password)
            user_data = {
                'username': username,
                'password': hashed_password,
                'role': role
            }

            db.users.insert_one(user_data)
            flash('User added successfully!', 'success')
            return redirect(url_for('admin_users'))

    return render_template('admin/users/add.html')

#USER - EDIT
@app.route('/admin/users/edit/<user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if session.get('role') != 'admin':
        flash('Only admins can edit users.', 'error')
        return redirect(url_for('login'))

    user = db.users.find_one({'_id': ObjectId(user_id)})

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', user['role'])

        update_data = {'username': username, 'role': role}
        
        if password:
            hashed_password = generate_password_hash(password)
            update_data['password'] = hashed_password

        db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': update_data}
        )

        flash('User updated successfully!', 'success')
        return redirect(url_for('admin_users'))

    return render_template('admin/users/edit.html', user=user)


#USERS - DELETE
@app.route('/admin/users/delete/<user_id>', methods=['GET'])
def delete_user(user_id):
    if session.get('role') != 'admin':
        flash('Only admins can delete users.', 'error')
        return redirect(url_for('login'))

    db.users.delete_one({'_id': ObjectId(user_id)})

    flash('User deleted successfully!', 'success')
    return redirect(url_for('admin_users'))


#ADMIN - ORDERS

@app.route('/admin/orders')
def admin_orders():
    if session.get('role') != 'admin':
        flash('Only admins can view orders.', 'error')
        return redirect(url_for('login'))

    orders = list(db.orders.find())
    
    for order in orders:
        # Periksa apakah kunci 'items' ada dalam order
        if 'items' in order:
            for item in order['items']:
                product = db.products.find_one({'_id': item['product_id']})
                if product:
                    item['product_name'] = product['name']
                else:
                    item['product_name'] = 'Product not found'
        else:
            order['items'] = []  # Jika tidak ada items, set sebagai list kosong atau Anda bisa menambahkan logika lain

    return render_template('admin/orders/index.html', orders=orders)


@app.route('/admin/orders/view/<order_id>', methods=['GET'])
def view_order(order_id):
    if session.get('role') != 'admin':
        flash('Only admins can view order details.', 'error')
        return redirect(url_for('login'))

    # Fetch the order from the database
    order = db.orders.find_one({'_id': ObjectId(order_id)})

    if order is None:
        flash('Order not found!', 'error')
        return redirect(url_for('admin_orders'))

    # Ensure 'items' is a list, if not an empty list
    if not isinstance(order.get('items'), list):
        order['items'] = []  # Set to empty list if not iterable

    # Fetch product details for each item in the order
    for item in order['items']:
        product = db.products.find_one({'_id': item['product_id']})
        
        # If the product is found, add its details to the item
        if product:
            item['product'] = product  # Add the entire product object to the item
        else:
            item['product'] = {'name': 'Product not found'}  # Default if the product isn't found

    return render_template('admin/orders/view.html', order=order)


#ADMIN - DELETE ORDERS
@app.route('/admin/orders/delete/<order_id>', methods=['GET'])
def delete_order(order_id):
    if session.get('role') != 'admin':
        flash('Only admins can delete orders.', 'error')
        return redirect(url_for('login'))

    # Menghapus order berdasarkan ID dari database
    db.orders.delete_one({'_id': ObjectId(order_id)})  # Gantilah 'orders' dengan nama koleksi yang sesuai

    flash('Order deleted successfully!', 'success')
    return redirect(url_for('admin_orders'))


#ROUTE USERS
@app.route('/products')
def show_products():
    products = list(db.products.find())
    return render_template('products.html', products=products)


@app.route('/product/<product_id>')
def detail_product(product_id):
    if 'username' not in session:
        flash("Please log in to view product details.", "error")
        return redirect(url_for('login'))
    
    product = db.products.find_one({'_id': ObjectId(product_id)})
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for('show_products'))
    
    return render_template('user/detail-product.html', product=product)

@app.route('/order/<product_id>', methods=['GET', 'POST'])
def order(product_id):
    if 'username' not in session:
        flash("Please log in to place an order.", "error")
        return redirect(url_for('login'))

    try:
        product_id = ObjectId(product_id)
    except Exception as e:
        flash("Invalid product ID.", "error")
        return redirect(url_for('show_products'))

    product = db.products.find_one({'_id': product_id})
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for('show_products'))

    if request.method == 'POST':
        quantity = int(request.form.get('quantity'))
        return render_template('user/order.html', product=product, quantity=quantity, total_price=product['price'] * quantity)

    return render_template('product_details.html', product=product)



#
@app.route('/submit_order', methods=['POST'])
def submit_order():
    # Retrieve form data
    full_name = request.form.get('fullName')
    phone_number = request.form.get('phoneNumber')
    address = request.form.get('address')
    quantity = request.form.get('quantity')
    product_id = request.form.get('product_id')

    # Query the product details (ensure ObjectId)
    try:
        product_id = ObjectId(product_id)
    except Exception as e:
        flash("Invalid product ID.", "error")
        return redirect(url_for('show_products'))

    product = db.products.find_one({'_id': product_id})
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for('show_products'))

    # Calculate the total price
    total_price = product['price'] * int(quantity)

    # Create order data
    order_data = {
        'full_name': full_name,
        'phone_number': phone_number,
        'address': address,
        'product_id': product_id,
        'quantity': int(quantity),
        'total_price': total_price,
        'status': 'pending',  # Default status is 'pending'
        'created_at': datetime.now()  # Add created_at timestamp
    }

    # Insert the order into the 'orders' collection
    db.orders.insert_one(order_data)

    # Create a WhatsApp message formatted string
    message = f"Order Details:\n\nFull Name: {full_name}\nPhone Number: {phone_number}\nProduct: {product['name']}\nQuantity: {quantity}\nTotal Price: {total_price} IDR\nAddress: {address}"

    # URL encode the message to prevent special characters causing issues
    encoded_message = urllib.parse.quote_plus(message)

    # WhatsApp API URL (replace your phone number here)
    whatsapp_url = f"https://wa.me/6281287757087?text={encoded_message}"

    # Redirect to WhatsApp
    return redirect(whatsapp_url)

def add_to_cart(user_id, product_id, quantity):
    # Temukan cart pengguna berdasarkan user_id
    cart = db.carts.find_one({"user_id": ObjectId(user_id)})
    
    # Jika cart belum ada untuk pengguna ini, buat cart baru dengan items kosong
    if not cart:
        cart = {"user_id": ObjectId(user_id), "items": []}
    else:
        # Jika sudah ada cart, ambil daftar items yang ada
        cart_items = cart["items"]

    # Cek apakah produk sudah ada di cart
    item_found = False
    for item in cart["items"]:
        if item["product_id"] == ObjectId(product_id):
            # Jika produk sudah ada, tambahkan jumlahnya
            item["quantity"] += quantity
            item_found = True
            break

    # Jika produk belum ada di cart, tambahkan sebagai item baru
    if not item_found:
        cart["items"].append({"product_id": ObjectId(product_id), "quantity": quantity})

    # Simpan perubahan ke database
    db.carts.update_one(
        {"user_id": ObjectId(user_id)},
        {"$set": {"items": cart["items"]}},
        upsert=True
    )

# Fungsi untuk mendapatkan item dari cart pengguna tertentu
def get_cart_items(user_id):
    cart = db.carts.find_one({"user_id": ObjectId(user_id)})
    if not cart:
        return []

    cart_items = []
    for item in cart["items"]:
        product = db.products.find_one({"_id": item["product_id"]})
        if product:
            cart_items.append({
                "product": product,
                "quantity": item["quantity"],
                "total_price": product["price"] * item["quantity"]
            })
    return cart_items



# Route untuk melihat keranjang
@app.route('/cart')
def view_cart():
    if 'username' not in session:
        flash("Please log in to view cart.", "error")
        return redirect(url_for('login'))  # Check if logged in

    user = db.users.find_one({"username": session["username"]})
    cart_items = get_cart_items(user["_id"])
    total_amount = sum(item['total_price'] for item in cart_items)
    return render_template('user/cart.html', cart_items=cart_items, total_amount=total_amount)


@app.route('/add_to_cart/<product_id>', methods=['POST'])
def add_to_cart_route(product_id):
    if 'username' not in session:
        flash("Please log in to add items to cart.", "error")
        return redirect(url_for('login'))

    quantity = int(request.form.get('quantity', 1))
    user = db.users.find_one({"username": session["username"]})
    add_to_cart(user["_id"], product_id, quantity)
    flash('Product added to cart', 'success')
    return redirect(url_for('view_cart'))

# Route untuk checkout
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'username' not in session:
        flash("Please log in to checkout.", "error")
        return redirect(url_for('login'))

    # Mendapatkan data pengguna
    user = db.users.find_one({"username": session["username"]})
    cart_items = get_cart_items(user["_id"])

    if request.method == 'POST':
        # Mendapatkan data dari form
        full_name = request.form.get('fullName')
        phone_number = request.form.get('phoneNumber')
        address = request.form.get('address')

        # Inisialisasi pesan dengan format tabel
        message = (
            f"Order Details:\n\n"
            f"Full Name     : {full_name}\n"
            f"Phone Number  : {phone_number}\n"
            f"Address       : {address}\n\n"
            f"Items:\n"
        )

        # Tambahkan setiap item ke pesan dengan format tabel
        total_price = 0  # Inisialisasi total harga
        order_items = []  # Menyimpan informasi item pesanan
        for item in cart_items:
            item_name = item['product']['name']
            item_price = item['total_price'] // item['quantity']
            item_quantity = item['quantity']
            total_price += item['total_price']

            # Format untuk item
            message += (
                f" - {item_name:<14} | {item_price} IDR x {item_quantity} items\n"
            )

            # Menyimpan detail item pesanan untuk dimasukkan ke dalam orders
            order_items.append({
                'product_id': item['product']['_id'],
                'quantity': item_quantity,
                'price': item_price,
                'total_price': item['total_price']
            })

        # Tambahkan total harga di akhir pesan
        message += f"\n*Total Price     : {total_price} IDR*"

        # Encode pesan untuk WhatsApp
        encoded_message = urllib.parse.quote_plus(message)
        whatsapp_url = f"https://wa.me/6285155452451?text={encoded_message}"

        # Simpan order ke db.orders
        order_data = {
            'user_id': ObjectId(user["_id"]),
            'full_name': full_name,
            'phone_number': phone_number,
            'address': address,
            'items': order_items,  # Menyimpan detail produk yang dipesan
            'total_price': total_price,
            'status': 'pending',  # Status order masih pending
            'created_at': datetime.now()  # Timestamp pembuatan order
        }
        
        # Insert order ke dalam collection 'orders'
        db.orders.insert_one(order_data)

        # Hapus keranjang setelah order selesai
        db.carts.delete_one({"user_id": ObjectId(user["_id"])})

        # Redirect ke WhatsApp untuk konfirmasi order
        return redirect(whatsapp_url)

    # Hitung total harga untuk tampilan checkout
    total_price = sum(item['total_price'] for item in cart_items)
    return render_template('user/checkout.html', cart_items=cart_items, total_price=total_price)


@app.route('/cart/delete/<product_id>', methods=['POST'])
def delete_from_cart(product_id):
    if 'username' not in session:
        flash("Please log in to manage your cart.", "error")
        return redirect(url_for('login'))  # Check if logged in

    # Get user details  
    user = db.users.find_one({"username": session["username"]})
    if not user:
        flash("User not found", "error")
        return redirect(url_for('view_cart'))

    # Find the user's cart
    cart = db.carts.find_one({"user_id": ObjectId(user["_id"])})
    if not cart:
        flash("Your cart is empty.", "error")
        return redirect(url_for('view_cart'))

    # Check if product exists in cart and remove it
    updated_items = [item for item in cart["items"] if str(item["product_id"]) != product_id]
    
    # If items list is empty, remove the cart document
    if not updated_items:
        db.carts.delete_one({"user_id": ObjectId(user["_id"])})
    else:
        db.carts.update_one(
            {"user_id": ObjectId(user["_id"])},
            {"$set": {"items": updated_items}}
        )

    flash("Product removed from cart.", "success")
    return redirect(url_for('view_cart'))  # Redirect to the cart page after deletion

if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)