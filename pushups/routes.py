from flask import Blueprint,render_template

main = Blueprint('main',__name__)

@main.route('/')
def  create_app():
    print("Hello World")
