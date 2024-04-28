import sqlite3
import hashlib
from . import get_db
from functools import wraps
from flask import (
    Blueprint, flash, redirect, session, 
    url_for, request, jsonify                   
    )

user = Blueprint('user', __name__)

def login_required(function):
    '''
    function wrapper that checks login status
    '''
    @wraps(function)
    def wrap(*args, **kwargs):
        user_info = session.get('user_info', None)
        if user_info is None:
            # not logged in
            flash("Please login first")
            return redirect(url_for("main.index"))
        else:
            # logged in
            return function(*args, **kwargs)
    return wrap

@user.route("/login", methods=['POST'])
def login():
    Account = request.form['Account']
    password = request.form['password']
    # hash password
    password = hashlib.sha256((password + Account).encode()).hexdigest()

    # check if user in stored in database
    db = get_db()
    user_info = db.cursor().execute(
        """ select *
            from Users
            where U_account = ? and U_password = ?""", (Account, password)
    ).fetchone()
    if user_info is None:
        # login failed
        flash("Login failed, please try again")
        return redirect(url_for('main.index'))
    elif user_info['U_account'] == 'cian':
        # admin login
        session['user_info'] = dict(user_info)
        return redirect(url_for('main.adminpage'))
    else:
        # login successfully
        session['user_info'] = dict(user_info)
        return redirect(url_for('main.userpage'))

    



@user.route("/logout", methods=['POST'])
@login_required
def logout():
    session['user_info'] = None
    flash("Logged out")
    return redirect(url_for('main.home'))





@user.route("/register-account-check", methods=['POST'])
def register_account_check():
    '''
    checks if account is already registered
    helper function handling ajax request
    '''
    account = request.form.get('Account')
    db = get_db()
    rst = db.cursor().execute(
        "select U_account from Users where U_account = ?", (account,)).fetchone()

    # empty string
    if account is None or account == '':
        response = jsonify(
            '<span style=\'color:red;\'>Please enter your account</span>')
    # account used
    elif rst:
        response = jsonify(
            '<span style=\'color:red;\'>Account has been registered</span>')
    else:
        response = jsonify(
            '<span style=\'color:green;\'>Account has not been registered</span>')

    # **Important**
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@user.route("/register", methods=['POST'])
def register():
    # get input values
    name = request.form['name']
    phonenumber = request.form['phonenumber']
    Account = request.form['Account']
    password = request.form['password']
    # latitude = request.form['latitude']
    # longitude = request.form['longitude']

    # check re-type password
    if password != request.form['re-password']:
        # sign-up fail
        flash("Please check: password and re-password need to be the same!")
        return redirect(url_for("main.sign_up"))

    # check any blanks:
    for k, v in request.form.items():
        if v == '':
            flash(f"Please check: '{k}' is not filled")
            return redirect(url_for("main.sign_up"))

    # check formats:
    # account
    for c in Account:
        if not (c.isdigit() or c.isalpha()):
            flash("Please check: Account can only contain letters and numbers")
            return redirect(url_for("main.sign_up"))

    # pwd
    for c in password:
        if not (c.isdigit() or c.isalpha()):
            flash("Please check: password can only contain letters and numbers")
            return redirect(url_for("main.sign_up"))

    # phone
    if len(phonenumber) != 10 or not phonenumber.isdigit():
        flash("Please check: phone number can only contain 10 digits")
        return redirect(url_for("main.sign_up"))

    # name
    if len(name.split()) != 2:
        flash("Please check: please fill in first name and last name")
        return redirect(url_for("main.sign_up"))
    for c in name:
        if not (c.isalpha() or c == ' '):
            flash("Please check: name can only contain letters and spaces")
            return redirect(url_for("main.sign_up"))

    # latitude and longitude
    # try:
    #     latitude = float(latitude)
    #     longitude = float(longitude)
    # except ValueError:
    #     flash("Please check: locations can only be float")
    #     return redirect(url_for("main.sign_up"))
    # if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
    #     flash("Please check: latitude and longitude must be in range")
    #     return redirect(url_for("main.sign_up"))

    # hash password + salt (account) before storing it
    password = hashlib.sha256((password + Account).encode()).hexdigest()

    # store newly registered user informations
    db = get_db()
    try:
        db.cursor().execute('''
            insert into Users (U_account, U_password, U_name, U_type, U_phone, U_balance)
            values (?, ?, ?, ?, ?, ?)
        ''', (Account, password, name, 0, phonenumber, 0))
            #  (Account, password, name, 0, latitude, longitude, phonenumber, 0))
    except sqlite3.IntegrityError:
        flash("User account is already registered, please try another account")
        return redirect(url_for("main.sign_up"))
    db.commit()

    # Register successfully
    flash("Registered Successfully, you may login now")
    return redirect(url_for("main.index"))


@user.route('/get_session', methods=['GET'])
def get_session():
    if request.method == 'GET':
        data = {}
        try:
            data['user_info'] = session['user_info']
        except:
            print('fail to get session')
        return jsonify(data)
    else:
        return jsonify({'user_info': 'nothing'})