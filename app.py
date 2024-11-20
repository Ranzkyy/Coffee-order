from flask import Flask, render_template,jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('admin/index.html')

@app.route('/login')
def login():
    return render_template('admin/login.html')


if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)