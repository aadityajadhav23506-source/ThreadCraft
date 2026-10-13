from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
)
import sqlite3
import os
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "custom-shirt-demo-secret-key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_database():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shirt_type TEXT NOT NULL,
            color TEXT NOT NULL,
            fabric TEXT NOT NULL,
            collar TEXT NOT NULL,
            sleeve TEXT NOT NULL,
            size TEXT NOT NULL,
            price INTEGER NOT NULL,
            user_id INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Add user_id to an older cart table if necessary
    columns = [
        row["name"]
        for row in cursor.execute("PRAGMA table_info(cart)").fetchall()
    ]
    if "user_id" not in columns:
        cursor.execute(
            "ALTER TABLE cart ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0"
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            total INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'Placed',
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            shirt_type TEXT NOT NULL,
            color TEXT NOT NULL,
            fabric TEXT NOT NULL,
            collar TEXT NOT NULL,
            sleeve TEXT NOT NULL,
            size TEXT NOT NULL,
            price INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        )
    """)

    conn.commit()
    conn.close()


# ---------------- OPTIONS AND PRICE ----------------

SHIRT_TYPES = ["Formal Shirt", "Casual Shirt", "Printed Shirt"]
COLORS = [
    "White", "Black", "Blue", "Red", "Green",
    "Yellow", "Pink", "Grey", "Navy"
]
FABRICS = ["Cotton", "Linen", "Denim"]
COLLARS = [
    "Regular Collar", "Button-Down Collar",
    "Mandarin Collar", "Spread Collar"
]
SLEEVES = ["Full Sleeve", "Half Sleeve"]
SIZES = ["S", "M", "L", "XL", "XXL"]

FABRIC_PRICES = {
    "Cotton": 500,
    "Linen": 650,
    "Denim": 700
}


def calculate_price(shirt_type, fabric, sleeve, size):
    if shirt_type not in SHIRT_TYPES:
        raise ValueError("Invalid shirt type")

    if fabric not in FABRICS:
        raise ValueError("Invalid fabric")

    if sleeve not in SLEEVES:
        raise ValueError("Invalid sleeve")

    if size not in SIZES:
        raise ValueError("Invalid size")

    price = FABRIC_PRICES[fabric]

    if sleeve == "Full Sleeve":
        price += 50

    if size == "XL":
        price += 30
    elif size == "XXL":
        price += 50

    if shirt_type == "Printed Shirt":
        price += 100

    return price


# ---------------- LOGIN REQUIRED ----------------

def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "error")
            return redirect(
                url_for("login", next=request.path)
            )
        return route_function(*args, **kwargs)

    return wrapper


# ---------------- HOME ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please fill in all fields.", "error")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("register"))

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, password)
            )
            conn.commit()
            flash("Registration successful. Please login.", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("This email is already registered.", "error")
            return redirect(url_for("register"))

        finally:
            conn.close()

    return render_template("register.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, password)
        ).fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]

            next_page = request.args.get("next", "")

            allowed_next = {
                url_for("view_cart"),
                url_for("customize"),
                url_for("checkout")
            }

            if next_page in allowed_next:
                return redirect(next_page)

            return redirect(url_for("customize"))

        flash("Invalid email or password.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    flash("You have logged out.", "success")
    return redirect(url_for("home"))


# ---------------- CUSTOMIZE SHIRT ----------------

@app.route("/customize", methods=["GET"])
@login_required
def customize():
    return render_template(
        "customize.html",
        shirt_types=SHIRT_TYPES,
        colors=COLORS,
        fabrics=FABRICS,
        collars=COLLARS,
        sleeves=SLEEVES,
        sizes=SIZES
    )


# ---------------- ADD TO CART ----------------

@app.route("/add_to_cart", methods=["POST"])
@login_required
def add_to_cart():
    shirt_type = request.form.get("shirt_type", "")
    color = request.form.get("color", "")
    fabric = request.form.get("fabric", "")
    collar = request.form.get("collar", "")
    sleeve = request.form.get("sleeve", "")
    size = request.form.get("size", "")

    if color not in COLORS or collar not in COLLARS:
        flash("Please select valid shirt options.", "error")
        return redirect(url_for("customize"))

    try:
        price = calculate_price(
            shirt_type, fabric, sleeve, size
        )
    except ValueError:
        flash("Please select valid shirt options.", "error")
        return redirect(url_for("customize"))

    conn = get_db()
    conn.execute("""
        INSERT INTO cart
        (shirt_type, color, fabric, collar, sleeve, size, price, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        shirt_type, color, fabric, collar, sleeve,
        size, price, session["user_id"]
    ))
    conn.commit()
    conn.close()

    flash("Shirt added to cart.", "success")
    return redirect(url_for("view_cart"))


# ---------------- VIEW CART ----------------

@app.route("/cart")
@login_required
def view_cart():
    conn = get_db()
    items = conn.execute(
        "SELECT * FROM cart WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()
    conn.close()

    total = sum(item["price"] for item in items)

    return render_template(
        "cart.html",
        items=items,
        total=total
    )


# ---------------- REMOVE FROM CART ----------------

@app.route("/remove_from_cart/<int:item_id>", methods=["POST"])
@login_required
def remove_from_cart(item_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM cart WHERE id = ? AND user_id = ?",
        (item_id, session["user_id"])
    )
    conn.commit()
    conn.close()

    flash("Item removed from cart.", "success")
    return redirect(url_for("view_cart"))


# ---------------- CHECKOUT ----------------

@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    conn = get_db()

    items = conn.execute(
        "SELECT * FROM cart WHERE user_id = ?",
        (session["user_id"],)
    ).fetchall()

    if not items:
        conn.close()
        flash("Your cart is empty.", "error")
        return redirect(url_for("view_cart"))

    total = sum(item["price"] for item in items)

    if request.method == "POST":
        customer_name = request.form.get(
            "customer_name", ""
        ).strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()

        if not customer_name or not phone or not address:
            conn.close()
            flash("Please fill in all checkout fields.", "error")
            return redirect(url_for("checkout"))

        if not phone.isdigit() or len(phone) != 10:
            conn.close()
            flash("Enter a valid 10-digit phone number.", "error")
            return redirect(url_for("checkout"))

        try:
            cursor = conn.execute("""
                INSERT INTO orders
                (user_id, customer_name, phone, address,
                 total, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session["user_id"],
                customer_name,
                phone,
                address,
                total,
                "Placed",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))

            order_id = cursor.lastrowid

            for item in items:
                conn.execute("""
                    INSERT INTO order_items
                    (order_id, shirt_type, color, fabric,
                     collar, sleeve, size, price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order_id,
                    item["shirt_type"],
                    item["color"],
                    item["fabric"],
                    item["collar"],
                    item["sleeve"],
                    item["size"],
                    item["price"]
                ))

            conn.execute(
                "DELETE FROM cart WHERE user_id = ?",
                (session["user_id"],)
            )

            conn.commit()
            conn.close()

            return redirect(
                url_for("order_confirmation", order_id=order_id)
            )

        except Exception:
            conn.rollback()
            conn.close()
            app.logger.exception("Checkout failed")
            flash("Order could not be placed. Please try again.", "error")
            return redirect(url_for("checkout"))

    conn.close()

    return render_template(
        "checkout.html",
        items=items,
        total=total
    )


# ---------------- ORDER CONFIRMATION ----------------

@app.route("/order-confirmation/<int:order_id>")
@login_required
def order_confirmation(order_id):
    conn = get_db()

    order = conn.execute("""
        SELECT * FROM orders
        WHERE id = ? AND user_id = ?
    """, (order_id, session["user_id"])).fetchone()

    if order is None:
        conn.close()
        abort(404)

    items = conn.execute("""
        SELECT * FROM order_items
        WHERE order_id = ?
    """, (order_id,)).fetchall()

    conn.close()

    return render_template(
        "order_confirmation.html",
        order=order,
        items=items
    )


# ---------------- RUN APP ----------------

# Create database tables for local and Render deployment
create_database()

# Run locally
if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
