from functools import wraps
from flask_login import LoginManager, login_required, current_user
from flask import Flask, render_template, request
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
import logging
from collections import defaultdict
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch

app = Flask(__name__)

# ADD HERE


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            return "Admin access required"
        return func(*args, **kwargs)
    return wrapper


app.config['SECRET_KEY'] = 'secret123'

database_url = os.environ.get("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_message = None
login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(20), default="staff")


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100))
    opening_stock = db.Column(db.Integer)
    purchase_price = db.Column(db.Float)
    selling_price = db.Column(db.Float)
    gst = db.Column(db.Float, default=0)
    user_id = db.Column(db.Integer)


class Sales(db.Model):
    __tablename__ = "sales"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, index=True)
    quantity_sold = db.Column(db.Integer)
    date = db.Column(db.String(20))
    profit = db.Column(db.Float)


class Purchase(db.Model):
    __tablename__ = "purchase"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, index=True)
    quantity = db.Column(db.Integer)
    date = db.Column(db.String(20), index=True)


# ADD THIS BLOCK HERE
with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route("/")
@login_required
def dashboard():

    products = Product.query.filter_by(user_id=current_user.id).all()
    sales = Sales.query.filter_by(user_id=current_user.id).all()

    total_products = len(products)
    total_sold = sum(s.quantity_sold for s in sales)

    total_profit = 0
    monthly_profit = defaultdict(int)

    for s in sales:
        product = Product.query.get(s.product_id)

        profit = (s.selling_price - product.purchase_price) * s.quantity_sold
        total_profit += profit

        month = s.date[:7]
        monthly_profit[month] += profit

    chart_labels = list(monthly_profit.keys())
    chart_data = list(monthly_profit.values())

    return render_template(
        "dashboard.html",
        total_products=total_products,
        total_sold=total_sold,
        total_profit=total_profit,
        chart_labels=chart_labels,
        chart_data=chart_data
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = generate_password_hash(request.form.get("password"))
        if User.query.filter_by(email=email).first():
            return "Email already exists"
        user = User(name=name, email=email, password=password)
        if not User.query.first():
            role = "admin"
        else:
            role = "staff"
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
        if not User.query.first():
            admin = User(
                name="Admin",
                email="admin@inventory.com",
                password=generate_password_hash("admin123")
            )
        db.session.add(admin)
        db.session.commit()
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
        opening_stock = int(request.form.get("opening_stock"))
        purchase_price = float(request.form.get("purchase_price"))
        selling_price = float(request.form.get("selling_price"))
        if opening_stock < 0:
            return "Invalid stock"
        new_product = Product(
            user_id=current_user.id,
            product_name=product_name,
            opening_stock=opening_stock,
            purchase_price=purchase_price,
            selling_price=selling_price
        )
        gst = float(request.form["gst"])
        product = Product(
            product_name=product_name,
            opening_stock=opening_stock,
            purchase_price=purchase_price,
            selling_price=selling_price,
            gst=gst,
            user_id=current_user.id
        )
        exists = Product.query.filter_by(
            user_id=current_user.id,
            product_name=product_name
        ).first()

        if exists:
            return "Product already exists"
        db.session.add(new_product)
        db.session.commit()

        return redirect(url_for("products"))
    return render_template("add_product.html")


@app.route("/sales")
@login_required
def sales():
    sales = Sales.query.filter_by(user_id=current_user.id).all()

    total_sales = sum(
        s.quantity_sold * s.selling_price
        for s in sales
    )

    return render_template(
        "sales.html",
        sales=sales,
        total_sales=total_sales
    )


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
        if quantity_sold <= 0:
            return "Invalid quantity"
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


@app.route("/delete-product/<int:id>")
@login_required
@admin_required
def delete_product(id):
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

    for p in products:

        purchased = db.session.query(
            db.func.sum(Purchase.quantity)
        ).filter_by(product_id=p.id).scalar() or 0

        sold = db.session.query(
            db.func.sum(Sales.quantity_sold)
        ).filter_by(product_id=p.id).scalar() or 0

        closing = p.opening_stock + purchased - sold

        stock_data.append({
            "name": p.product_name,
            "opening": p.opening_stock,
            "purchased": purchased,
            "sold": sold,
            "closing": closing
        })

    return render_template("stock.html", stock_data=stock_data)


@app.route("/delete-product/<int:id>")
@login_required
def delete_product(id):
    product = Product.query.get_or_404(id)

    if product.user_id != current_user.id:
        return "Unauthorized", 403

    # delete related sales first
    Purchase.query.filter_by(product_id=product.id).delete()
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
    revenue = sum(
        s.quantity_sold * s.selling_price
        for s in sales
    )

    if selected_date:
        query = query.filter(Sales.date == selected_date)

    report_data = query.all()

    return render_template("report.html", report_data=report_data)


@app.route("/gst-report")
@login_required
def gst_report():

    month = request.args.get("month")

    sales_query = Sales.query.filter_by(user_id=current_user.id)

    if month:
        sales_query = sales_query.filter(Sales.date.startswith(month))

    sales = sales_query.all()

    gst_0_taxable = 0
    gst_5_taxable = 0
    gst_5_amount = 0

    for s in sales:
        product = Product.query.get(s.product_id)
        taxable = s.quantity_sold * s.selling_price

        if product.gst == 0:
            gst_0_taxable += taxable
        elif product.gst == 5:
            gst_5_taxable += taxable
            gst_5_amount += taxable * 0.05

    total_gst = gst_5_amount

    return render_template(
        "gst_report.html",
        gst_0_taxable=gst_0_taxable,
        gst_5_taxable=gst_5_taxable,
        gst_5_amount=gst_5_amount,
        total_gst=total_gst
    )


@app.route("/invoice/<int:sale_id>")
@login_required
def invoice(sale_id):

    sale = Sales.query.get_or_404(sale_id)
    product = Product.query.get(sale.product_id)

    taxable = sale.quantity_sold * sale.selling_price
    gst_amount = taxable * (product.gst / 100)
    total = taxable + gst_amount

    file_path = f"/tmp/invoice_{sale_id}.pdf"

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Invoice", styles['Heading1']))
    story.append(Spacer(1, 12))

    data = [
        ["Product", product.product_name],
        ["Qty", sale.quantity_sold],
        ["Price", sale.selling_price],
        ["Taxable", taxable],
        ["CGST", cgst],
        ["SGST", sgst],
        ["Total", total],
    ]
    table = Table(data)
    story.append(table)

    doc = SimpleDocTemplate(file_path, pagesize=A4)
    doc.build(story)

    return send_file(file_path, as_attachment=True)


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

    sales = Sales.query.filter_by(user_id=current_user.id).all()

    data = defaultdict(int)

    for s in sales:
        month = s.date[:7]   # YYYY-MM
        data[month] += s.quantity_sold * s.selling_price

    monthly = [
        {"month": k, "total": v}
        for k, v in sorted(data.items())
    ]

    return render_template("monthly.html", monthly=monthly)


if __name__ == "__main__":
    app.run(debug=True)
