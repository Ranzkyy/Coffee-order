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
app.config['SECRET_KEY'] = 'geforce'

#format idr
def format_rupiah(value):
    return "Rp{:,.0f}".format(float(value)).replace(',', '.')
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

        total_sales = db.orders.aggregate([
            {"$match": {"status": "done"}},
            {"$group": {"_id": None, "total_sales": {"$sum": "$total_price"}}} 
        ])
        
        total_sales = list(total_sales)
        total_sales = total_sales[0]['total_sales'] if total_sales else 0

        return render_template('admin/index.html', total_users=total_users, total_products=total_products, total_sales=total_sales)
    
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

####### <<<==== ADMIN ROUTES ====>>> #######

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
        if 'items' in order:
            for item in order['items']:
                product = db.products.find_one({'_id': item['product_id']})
                if product:
                    item['product_name'] = product['name']
                else:
                    item['product_name'] = 'Product not found'
        else:
            order['items'] = []

    return render_template('admin/orders/index.html', orders=orders)


@app.route('/admin/orders/view/<order_id>', methods=['GET'])
def view_order(order_id):
    if session.get('role') != 'admin':
        flash('Only admins can view order details.', 'error')
        return redirect(url_for('login'))

    order = db.orders.find_one({'_id': ObjectId(order_id)})

    if order is None:
        flash('Order not found!', 'error')
        return redirect(url_for('admin_orders'))

    if not isinstance(order.get('items'), list):
        order['items'] = []

    for item in order['items']:
        product = db.products.find_one({'_id': item['product_id']})
        
        if product:
            item['product'] = product
        else:
            item['product'] = {'name': 'Product not found'}

    return render_template('admin/orders/view.html', order=order)


#ADMIN - DELETE ORDERS
@app.route('/admin/orders/delete/<order_id>', methods=['GET'])
def delete_order(order_id):
    if session.get('role') != 'admin':
        flash('Only admins can delete orders.', 'error')
        return redirect(url_for('login'))

    db.orders.delete_one({'_id': ObjectId(order_id)})

    flash('Order deleted successfully!', 'success')
    return redirect(url_for('admin_orders'))

@app.route('/admin/orders/update_status/<order_id>', methods=['POST'])
def update_order_status(order_id):
    data = request.get_json()
    new_status = data.get('status')
    
    if new_status not in ['pending', 'proceed', 'done']:
        return jsonify({'error': 'Invalid status'}), 400

    order = db.orders.find_one({"_id": ObjectId(order_id)})
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    db.orders.update_one(
        {"_id": ObjectId(order_id)}, 
        {"$set": {"status": new_status}}
    )
    
    return jsonify({'message': 'Order status updated successfully'})



######## <<<==== END ADMIN ====>>> ########


#ROUTE USER
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


@app.route('/order')
def your_order():
    if 'username' not in session:
        flash("Please log in to view your cart.", "error")
        return redirect(url_for('login'))

    user = db.users.find_one({"username": session["username"]})
    if not user:
        flash("User not found. Please log in again.", "error")
        return redirect(url_for('logout'))

    try:
        cart_items = get_cart_items(user["_id"])
        total_amount = sum(item['total_price'] for item in cart_items)
    except Exception as e:
        flash(f"Error loading cart items: {str(e)}", "error")
        cart_items = []
        total_amount = 0

    try:
        orders = list(db.orders.find({"user_id": user["_id"]}).sort("date", -1))
    except Exception as e:
        flash(f"Error fetching orders: {str(e)}", "error")
        orders = []

    active_tab = request.args.get('active_tab', 'pending')

    return render_template(
        'user/order.html',
        cart_items=cart_items,
        total_amount=total_amount,
        orders=orders,
        active_tab=active_tab
    )


def add_to_cart(user_id, product_id, quantity):
    cart = db.carts.find_one({"user_id": ObjectId(user_id)})

    if not cart:
        cart = {"user_id": ObjectId(user_id), "items": []}
    else:
        cart_items = cart["items"]

    #ngambil informasi produk
    product = db.products.find_one({"_id": ObjectId(product_id)})
    if not product:
        return  #kalo produk tidak ditemukan, kita hentikan proses

    #ngambil informasi gambar produk, defaultnya kosong
    product_image = product.get('image_filename', '') 

    item_found = False
    for item in cart["items"]:
        if item["product_id"] == ObjectId(product_id):
            item["quantity"] += quantity
            item_found = True
            break

    if not item_found:
        cart["items"].append({
            "product_id": ObjectId(product_id),
            "quantity": quantity,
            "product_image": product_image  # Menyimpan gambar produk di cart
        })

    db.carts.update_one(
        {"user_id": ObjectId(user_id)},
        {"$set": {"items": cart["items"]}},
        upsert=True
    )

def get_cart_items(user_id):
    try:
        user_id = ObjectId(user_id)
    except Exception:
        return []

    # Fetching cart items
    cart = db.carts.find_one({"user_id": user_id})
    if not cart:
        return []

    cart_items = []
    for item in cart.get("items", []):
        try:
            product = db.products.find_one({"_id": ObjectId(item["product_id"])})
            if product:
                cart_items.append({
                    "product": product,
                    "quantity": item["quantity"],
                    "total_price": product["price"] * item["quantity"],
                    "product_image": item.get("product_image", '')
                })
        except Exception as e:
            print(f"Error fetching product details: {e}")
            continue

    return cart_items



@app.route('/cart')
def view_cart():
    if 'username' not in session:
        flash("Please log in to view your cart.", "error")
        return redirect(url_for('login'))

    user = db.users.find_one({"username": session["username"]})
    if not user:
        flash("User not found. Please log in again.", "error")
        return redirect(url_for('logout'))

    try:
        cart_items = get_cart_items(user["_id"])
        total_amount = sum(item['total_price'] for item in cart_items)
    except Exception as e:
        flash(f"Error loading cart items: {str(e)}", "error")
        cart_items = []
        total_amount = 0

    #Fetch orders
    try:
        orders = list(db.orders.find({"user_id": user["_id"]}).sort("date", -1))
    except Exception as e:
        flash(f"Error fetching orders: {str(e)}", "error")
        orders = []

    active_tab = request.args.get('active_tab', 'pending')

    return render_template(
        'user/cart.html',
        cart_items=cart_items,
        total_amount=total_amount,
        orders=orders,
        active_tab=active_tab
    )

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


@app.route('/checkout_selected', methods=['POST'])
def checkout_selected():
    if 'username' not in session:
        flash("Please log in to proceed to checkout.", "error")
        return redirect(url_for('login'))
    selected_item = request.form.get('selected_item')
    if not selected_item:
        flash("No item selected for checkout.", "warning")
        return redirect(url_for('view_cart'))

    product = db.products.find_one({"_id": ObjectId(selected_item)})

    if not product:
        flash("Selected item not found.", "error")
        return redirect(url_for('view_cart'))

    flash("Checkout successful for selected item.", "success")
    return render_template('user/checkout.html', products=[product])


# Route untuk checkout
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'username' not in session:
        flash("Please log in to checkout.", "error")
        return redirect(url_for('login'))

    user = db.users.find_one({"username": session["username"]})
    cart_items = get_cart_items(user["_id"])

    if request.method == 'POST':
        full_name = request.form.get('fullName')
        phone_number = request.form.get('phoneNumber')
        payment_method = request.form.get('paymentMethod')
        address = request.form.get('address')

        message = (
            f"Order Details:\n\n"
            f"Full Name     : {full_name}\n"
            f"Phone Number  : {phone_number}\n"
            f"Metode Pembayaran : {payment_method}\n"
            f"Address       : {address}\n\n"
            f"Items:\n"
        )

        total_price = 0  # Inisialisasi total harga

        for item in cart_items:
            product = db.products.find_one({'_id': item['product']['_id']}) 
            item_name = product['name']
            item_image = product.get('image_filename', '') 
            item_price = item['total_price'] // item['quantity']
            item_quantity = item['quantity']
            total_price += item['total_price']

            # Format untuk item
            message += (
                f" - {item_name:<14} | {item_price} IDR x {item_quantity} items\n"
            )

            # Simpan setiap produk sebagai pesanan terpisah
            order_data = {
                'user_id': ObjectId(user["_id"]),
                'full_name': full_name,
                'phone_number': phone_number,
                'payment_method': payment_method,
                'address': address,
                'product_name': item_name,
                'product_image': item_image,  
                'quantity': item_quantity,
                'price': item_price,
                'total_price': item['total_price'],
                'status': 'pending',  #status defaultnya pending bisa diubah di dahsboard admin
                'created_at': datetime.now() 
            }

            db.orders.insert_one(order_data)

        #hapus keranjang setelah order selesai
        db.carts.delete_one({"user_id": ObjectId(user["_id"])})

        encoded_message = urllib.parse.quote_plus(message)
        whatsapp_url = f"https://wa.me/6285155452451?text={encoded_message}"

        return redirect(whatsapp_url)

    total_price = sum(item['total_price'] for item in cart_items)
    return render_template('user/checkout.html', cart_items=cart_items, total_price=total_price)

@app.route('/cart/delete/<product_id>', methods=['POST'])
def delete_from_cart(product_id):
    if 'username' not in session:
        flash("Please log in to manage your cart.", "error")
        return redirect(url_for('login'))

    user = db.users.find_one({"username": session["username"]})
    if not user:
        flash("User not found", "error")
        return redirect(url_for('view_cart'))

    cart = db.carts.find_one({"user_id": ObjectId(user["_id"])})
    if not cart:
        flash("Your cart is empty.", "error")
        return redirect(url_for('view_cart'))

    updated_items = [item for item in cart["items"] if str(item["product_id"]) != product_id]
    
    if not updated_items:
        db.carts.delete_one({"user_id": ObjectId(user["_id"])})
    else:
        db.carts.update_one(
            {"user_id": ObjectId(user["_id"])},
            {"$set": {"items": updated_items}}
        )

    flash("Product removed from cart.", "success")
    return redirect(url_for('view_cart'))



@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404
if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)