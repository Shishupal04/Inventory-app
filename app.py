import os
from flask import Flask, render_template, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date as dt_date
from sqlalchemy import func
import pandas as pd
from flask import send_file
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret123'

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

models(User, Sales, Purchase)

login_manager = LoginManager(app)

login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    product_name = db.Column(db.String(100))
    opening_stock = db.Column(db.Integer)
    purchase_price = db.Column(db.Float)
    selling_price = db.Column(db.Float)


class Sales(db.Model):
    __tablename__ = "sales"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer)
    quantity_sold = db.Column(db.Integer)
    date = db.Column(db.String(20))
    profit = db.Column(db.Float)


class Purchase(db.Model):
    __tablename__ = "purchase"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer)
    quantity = db.Column(db.Integer)
    date = db.Column(db.String(20))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route("/")
@login_required
def dashboard():

    total_products = Product.query.filter_by(user_id=current_user.id).count()
    products = Product.query.filter_by(user_id=current_user.id).all()

    total_sold = 0
    low_stock = []

    total_profit = db.session.query(func.sum(Sales.profit))\
        .join(Product, Sales.product_id == Product.id)\
        .filter(Product.user_id == current_user.id)\
        .scalar()

    total_profit = total_profit or 0

    for product in products:

        sold = db.session.query(func.sum(Sales.quantity_sold))\
            .filter(Sales.product_id == product.id)\
            .scalar()

        sold = sold or 0
        total_sold += sold

        closing = product.opening_stock - sold

        if closing < 20:
            low_stock.append({
                "name": product.product_name,
                "closing": closing
            })

    return render_template(
        "dashboard.html",
        total_products=total_products,
        total_sold=total_sold,
        total_profit=total_profit,
        low_stock=low_stock
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = generate_password_hash(request.form.get("password"))

        user = User(name=name, email=email, password=password)
        db.session.add(user)
        db.session.commit()

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/products")
@login_required
def products():
    user_products = Product.query.filter_by(user_id=current_user.id).all()
    return render_template("products.html", products=user_products)


@app.route("/add-product", methods=["GET", "POST"])
@login_required
def add_product():
    if request.method == "POST":
        product_name = request.form.get("product_name")
        opening_stock = request.form.get("opening_stock")
        purchase_price = float(request.form.get("purchase_price"))
        selling_price = float(request.form.get("selling_price"))

        new_product = Product(
            user_id=current_user.id,
            product_name=product_name,
            opening_stock=opening_stock,
            purchase_price=purchase_price,
            selling_price=selling_price
        )
        db.session.add(new_product)
        db.session.commit()

        return redirect(url_for("products"))
    return render_template("add_product.html")


@app.route("/sales")
@login_required
def sales():
    sales_data = (
        db.session.query(Sales, Product)
        .join(Product, Sales.product_id == Product.id)
        .filter(Product.user_id == current_user.id)
        .all()
    )
    return render_template("sales.html", sales_data=sales_data)


@app.route("/add-sales", methods=["GET", "POST"])
@login_required
def add_sales():
    products = Product.query.filter_by(user_id=current_user.id).all()

    if request.method == "POST":
        product_id = request.form.get("product_id")
        quantity_sold = int(request.form.get("quantity_sold"))
        sale_date = request.form.get("date")

        product = Product.query.get(product_id)

        total_sold = db.session.query(func.sum(Sales.quantity_sold))\
            .filter(Sales.product_id == product.id)\
            .scalar()

        total_sold = total_sold or 0

        available_stock = product.opening_stock - total_sold

        if quantity_sold > available_stock:
            return "Error: Not enough stock available"
        profit = (product.selling_price -
                  product.purchase_price) * quantity_sold
        new_sale = Sales(
            product_id=product_id,
            quantity_sold=quantity_sold,
            date=sale_date,
            profit=profit
        )

        db.session.add(new_sale)
        db.session.commit()

        return redirect(url_for("sales"))

    return render_template("add_sales.html", products=products)


@app.route("/delete-sale/<int:id>")
@login_required
def delete_sale(id):
    sale = Sales.query.get_or_404(id)
    db.session.delete(sale)
    db.session.commit()
    return redirect(url_for("sales"))


@app.route("/edit-sale/<int:id>", methods=["GET", "POST"])
@login_required
def edit_sale(id):
    sale = Sales.query.get_or_404(id)
    products = Product.query.filter_by(user_id=current_user.id).all()

    if request.method == "POST":
        sale.product_id = request.form.get("product_id")
        sale.quantity_sold = int(request.form.get("quantity_sold"))
        sale.date = request.form.get("date")

        product = Product.query.get(sale.product_id)

        sale.profit = (
            product.selling_price - product.purchase_price
        ) * sale.quantity_sold

        db.session.commit()
        return redirect(url_for("sales"))

    return render_template("edit_sale.html", sale=sale, products=products)


@app.route("/stock")
@login_required
def stock():
    products = Product.query.filter_by(user_id=current_user.id).all()

    stock_data = []

    for product in products:

        total_sold = db.session.query(func.sum(Sales.quantity_sold))\
            .filter(Sales.product_id == product.id)\
            .scalar()

        total_sold = total_sold or 0

        total_purchase = db.session.query(func.sum(Purchase.quantity))\
            .filter(Purchase.product_id == product.id)\
            .scalar()

        total_purchase = total_purchase or 0

        closing_stock = (
            int(product.opening_stock)
            + int(total_purchase)
            - int(total_sold)
        )

        stock_data.append({
            "product": product.product_name,
            "opening": product.opening_stock,
            "purchase": total_purchase,
            "sold": total_sold,
            "closing": closing_stock
        })

    return render_template("stock.html", stock_data=stock_data)


@app.route("/delete-product/<int:id>")
@login_required
def delete_product(id):
    product = Product.query.get_or_404(id)

    # delete related sales first
    Sales.query.filter_by(product_id=product.id).delete()

    db.session.delete(product)
    db.session.commit()

    return redirect(url_for("products"))


@app.route("/edit-product/<int:id>", methods=["GET", "POST"])
@login_required
def edit_product(id):
    product = Product.query.get_or_404(id)

    if request.method == "POST":
        product.product_name = request.form.get("product_name")
        product.opening_stock = int(request.form.get("opening_stock"))
        product.purchase_price = float(request.form.get("purchase_price"))
        product.selling_price = float(request.form.get("selling_price"))

        db.session.commit()
        return redirect(url_for("products"))

    return render_template("edit_product.html", product=product)


@app.route("/add-purchase", methods=["GET", "POST"])
@login_required
def add_purchase():
    products = Product.query.filter_by(user_id=current_user.id).all()

    if request.method == "POST":
        product_id = request.form.get("product_id")
        quantity = int(request.form.get("quantity"))
        purchase_date = request.form.get("date")

        new_purchase = Purchase(
            product_id=product_id,
            quantity=quantity,
            date=purchase_date
        )

        db.session.add(new_purchase)
        db.session.commit()

        return redirect(url_for("stock"))

    return render_template("add_purchase.html", products=products)


@app.route("/report")
@login_required
def report():
    selected_date = request.args.get("date")

    query = (
        db.session.query(Sales, Product)
        .join(Product, Sales.product_id == Product.id)
        .filter(Product.user_id == current_user.id)
    )

    if selected_date:
        query = query.filter(Sales.date == selected_date)

    report_data = query.all()

    return render_template("report.html", report_data=report_data)


@app.route("/export")
@login_required
def export():
    data = (
        db.session.query(Sales, Product)
        .join(Product, Sales.product_id == Product.id)
        .filter(Product.user_id == current_user.id)
        .all()
    )

    rows = []

    for sale, product in data:
        rows.append({
            "Date": sale.date,
            "Product": product.product_name,
            "Quantity": sale.quantity_sold,
            "Revenue": sale.quantity_sold * product.selling_price
        })

    df = pd.DataFrame(rows)

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        download_name="sales_report.xlsx",
        as_attachment=True
    )


@app.route("/monthly")
@login_required
def monthly():

    data = (
        db.session.query(
            func.substr(Sales.date, 1, 7).label("month"),
            func.sum(Sales.quantity_sold).label("qty"),
            func.sum(Sales.quantity_sold *
                     Product.selling_price).label("revenue"),
            func.sum(
                Sales.quantity_sold *
                (Product.selling_price - Product.purchase_price)
            ).label("profit")
        )
        .join(Product, Sales.product_id == Product.id)
        .filter(Product.user_id == current_user.id)
        .group_by("month")
        .all()
    )

    return render_template("monthly.html", data=data)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        from werkzeug.security import generate_password_hash

with app.app_context():
    db.create_all()

    if not User.query.first():
        user = User(
            name="Admin",
            email="admin@example.com",
            password=generate_password_hash("admin123")
        )
        db.session.add(user)
        db.session.commit()
    app.run(debug=True)
