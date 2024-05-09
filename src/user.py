import base64
import sqlite3
import json
from .math import unique_order_number
from .login import login_required
from . import get_db, DISTANCE_BOUNDARY
from flask import (
    Blueprint, request,
    session, redirect, url_for,
    json, jsonify, flash
)
from datetime import datetime

costumer = Blueprint('costumer', __name__)

@costumer.route("/shop_add", methods=['POST'])
@login_required
def shop_add():
    # get input values
    user_info = session.get('user_info')
    UID = user_info['UID']
    meal_name = request.form['meal_name']
    meal_price = request.form['meal_price']
    meal_quantity = request.form['meal_quantity']
    meal_pic = request.files['meal_pic']    # image file

    # check if user is owner
    if(user_info['U_type'] == 0):
        flash("Please register your store first")
        return redirect(url_for("main.userpage"))

    # fetch shop_info
    db = get_db()
    shop_info = db.cursor().execute(
        """ select *
            from Stores
            where S_owner = ?""", (UID,)
    ).fetchone()
    SID = shop_info['SID']

    # check any blanks:
    for k, v in request.form.items():
        if v == '':
            flash(f"Please check: '{k}' is not filled")
            return redirect(url_for("main.userpage"))
    if(meal_pic.filename == ''):
        flash("Please upload a picture for the product")
        return redirect(url_for("main.userpage"))

    # get the extension of the file ex: png, jpeg
    meal_pic_extension = meal_pic.filename.split('.')[1]

    # check formats:
    # price and quantity
    if(int(meal_price) < 0 or int(meal_quantity) < 0):
        flash("Please check: price and quantity can only be non-negatives")
        return redirect(url_for("main.userpage"))

    # store newly added product informations
    db = get_db()
    try:
        db.cursor().execute('''
            insert into Products (P_name, P_price, P_quantity, P_image, P_imagetype, P_owner, P_store)
            values (?, ?, ?, ?, ?, ?, ?)
        ''', (meal_name, meal_price, meal_quantity, base64.b64encode(meal_pic.read()), meal_pic_extension, UID, SID))
    except sqlite3.IntegrityError:
        # print("something went wrong!!")
        flash(" oops something went wrong!!")
        return redirect(url_for("main.userpage"))
    # session['product_info'] = dict(product_info)       # not sure if needed
    db.commit()

    # Register successfully
    flash("Product added successfully")
    return redirect(url_for("main.userpage"))

    



@costumer.route("/order_made", methods=['POST'])
@login_required
def order_made():
    '''
    called when any order has been made
    '''

    json_data = request.json
    '''
    request.json format:
    {
        "PIDs": List[int],
        "Quantities": List[int],
        "S_owner": int,
        "Type": int,
    }
    '''

    # get user data
    UID = session['user_info']['UID']
    db = get_db()
    user_info = db.cursor().execute('''
        select *
        from Users
        where UID = ?
        ''', (UID,)).fetchone()

    # get shop owner UID & shop SID
    shop_owner_UID = json_data['S_owner']
    SID = db.cursor().execute('''
        select SID
        from Stores
        where S_owner = ?
    ''', (shop_owner_UID,)).fetchone()['SID']
    print("shop_owner_UID:", shop_owner_UID)

    # check all ordered products one by one
    Subtotal = 0
    Products = []
    non_sufficient_product_name = []
    for PID, Quantity in zip(json_data['PIDs'], json_data['Quantities']):
        db = get_db()
        rst = db.cursor().execute('''
            select *
            from Products
            where PID = ?
            ''', (PID,)).fetchone()
        # check if product exists
        if rst is None:
            return jsonify({
                'message': 'Failed to create order: one or more products does not exist'
            }), 200
        # product exists, check if product is sufficient
        elif Quantity > rst['P_quantity']:
            non_sufficient_product_name.append(rst['P_name'])
        # # calculate subtotal
        # Subtotal += rst['P_price'] * Quantity

        rst = dict(rst)
        rst['P_image'] = base64.b64encode(rst['P_image']).decode()
        rst['Order_quantity'] = Quantity
        del rst['P_quantity']  # useless
        Products.append(rst)

        # Calculate subtotal after checking all products
        Subtotal = sum(rst['P_price'] * Quantity for rst, Quantity in zip(Products, json_data['Quantities']))

    # check if product quantity sufficient
    if len(non_sufficient_product_name) > 0:
        return jsonify({
            'message': "Failed to create order: insufficient quantity of {}".format(
                non_sufficient_product_name)
        }), 200
    # check if wallet ballence sufficient
    # calculate fee
    # lat1, lon1 = db.cursor().execute("select U_latitude, U_longitude from Users where UID = ?",
    #                                  (UID, )).fetchone()
    # lat2, lon2 = db.cursor().execute("select S_latitude, S_longitude from Stores where S_owner = ?",
    #                                  (shop_owner_UID, )).fetchone()
    # distance = float(distance_between_locations(lat1, lon1, lat2, lon2))

    # Delivery_fee = 0 if json_data['Type'] == '0' else max(
    #     int(round(distance * 10)), 10)
    Total = Subtotal
    if Total > user_info['U_balance']:
        return jsonify({
            'message': "Failed to create order: insufficient balance"
        }), 200

    # create successful, update database
    try:
        # update Users
        # customer
        db = get_db()
        db.cursor().execute('''
            update Users
            set U_balance = U_balance - ?
            where UID = ?
        ''', (Total, user_info['UID']))
        # shop owner
        db.cursor().execute('''
            update Users
            set U_balance = U_balance + ?
            where UID = ?
        ''', (Total, shop_owner_UID))

        # update Orders
        details_str = json.dumps({
            'Products': Products,
            'Subtotal': Subtotal,
            # 'Delivery_fee': Delivery_fee,
        })
        order_number = unique_order_number()
        rst = db.cursor().execute('''
            insert into Orders (O_unique_number, O_status, O_end_time, O_amount, O_type, O_details, SID)
            values (?, ?, ?, ?, ?, ?, ?)
        ''', (order_number, 0, None, Total, json_data['Type'], details_str, SID))
            #  (0, None, distance, Total, json_data['Type'], details_str, SID))

        # update Process_Order
        OID = rst.lastrowid
        db.cursor().execute('''
            insert into Process_Order (UID, OID, PO_type)
            values (?, ?, ?)
        ''', (UID, OID, 0))

        # update Transaction_Record
        # user -> shop
        db.cursor().execute('''
            insert into Transaction_Record (T_action, T_amount, T_Subject, T_Object)
            values (?, ?, ?, ?)
        ''', (0, -Total, UID, shop_owner_UID))
        # shop <- user
        db.cursor().execute('''
            insert into Transaction_Record (T_action, T_amount, T_Subject, T_Object)
            values (?, ?, ?, ?)
        ''', (1, Total, shop_owner_UID, UID))

        # update Products
        for PID, Quantity in zip(json_data['PIDs'], json_data['Quantities']):
            db.cursor().execute('''
                update Products
                set P_quantity = P_quantity - ?
                where PID = ?
            ''', (Quantity, PID))
    except Exception as e:
        print(type(e), str(e))
        db.rollback()
        return jsonify({
            'message': 'Failed to create order: please try again'
        }), 200

    db.commit()

    return jsonify({
        'message': 'Order made successfully'
    }), 200


@costumer.route("/order_preview", methods=['POST'])
@login_required
def order_preview():
    '''
    called before any order has been made
    caculates the price
    '''
    try:
        PIDs = []
        Quantities = []

        for PID, Q in zip(request.form.getlist('PIDs'), request.form.getlist('Quantities')):
            Q = 0 if Q == '' else int(Q)
            if Q > 0:
                PIDs.append(PID)
                Quantities.append(Q)

        if len(Quantities) == 0:
            return jsonify('Failed to create order: please select at least on product'), 500
    except ValueError:
        return jsonify('Please check: order content must be valid'), 500

    # query product infos
    db = get_db()
    db.cursor().execute("DROP TABLE IF EXISTS PID_list")
    db.cursor().execute("""
        create temp table PID_list(PID INTEGER PRIMARY KEY)
    """)
    for P in PIDs:
        db.cursor().execute("""
        insert into PID_list values (?)
        """, (P, ))

    rst = db.cursor().execute("""
    select * from PID_list natural join Products
    """).fetchall()

    # decode image + calculate price
    if len(rst) != len(Quantities):
        return "Product modified by store, please try again!", 500
    Products = [dict(r) for r in rst]

    Subtotal = 0
    for r, q in zip(Products, Quantities):
        r['P_image'] = base64.b64encode(r['P_image']).decode()
        r['Order_quantity'] = q
        Subtotal += r['P_price'] * q

    # calculate fee
    # lat1, lon1 = db.cursor().execute("select U_latitude, U_longitude from Users where UID = ?",
    #                                  (session['user_info']['UID'], )).fetchone()
    # lat2, lon2 = db.cursor().execute("select S_latitude, S_longitude from Stores where S_owner = ?",
    #                                  (Products[0]['P_owner'], )).fetchone()
    # distance = float(distance_between_locations(lat1, lon1, lat2, lon2))

    # Delivery_fee = 0 if request.form['Dilivery'] == '0' else max(
    #     int(round(distance * 10)), 10)

    db.cursor().execute("drop table PID_list")

    return jsonify({
        'Products': Products,
        'Subtotal': Subtotal,
        # 'Delivery_fee': Delivery_fee,
        # 'Distance': distance,
        'Type': request.form['PickUp'],
        'S_owner': Products[0]['P_owner']
    }), 200

def search_menu(SID, meal):
    db = get_db()
    rst = db.cursor().execute('''
        select *
        from Products
        where P_store = ? and instr(lower(P_name), lower(?)) > 0
        ''', (SID, meal)).fetchall()
    # instr(a, b) > 0 means if a contains substring b

    rst = [dict(r) for r in rst]
    for r in rst:
        r['P_image'] = base64.b64encode(r['P_image']).decode()
    return rst


@costumer.route("/search-shops", methods=['POST'])
def search_shops():
    search = {i: request.form[i] for i in [
        'meal']}
    # desc = 'desc' if request.form["desc"] == 'true' else ''
    db = get_db()
    rst = db.cursor().execute(
        f'''
        SELECT SID, S_name, S_foodtype
        FROM Stores
        ''',
        search
    ).fetchall()

    # Optionally, you can order the results here in Python
    # based on a specific criterion, for example, shop name.
    # You can replace this with your desired ordering logic.
    rst = sorted(rst, key=lambda x: x[1])

    table = {'tableRow': []}
    append = table['tableRow'].append
    for SID, S_name, S_foodtype in rst:
        menu = search_menu(SID, search['meal'])
        if menu:
            append({'shop_name': S_name, 'foodtype': S_foodtype,
                    'menu': menu})

            # Call updateMealTable() immediately after fetching the menu
            # updateMealTable({'name': S_name})  # Pass the shop object as argument
    
    # print("Table:", table)  # Debugging
    response = jsonify(table)
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@costumer.route("/order-detail", methods=['POST'])
def order_detail():
    OID = request.form['OID']
    db = get_db()
    details_str = db.cursor().execute(
        'select O_details from Orders where OID = ?', (OID, )).fetchone()[0]
    details = json.loads(details_str)
    return jsonify(details), 200


@costumer.route("/search-MyOrders", methods=['POST'])
def search_MyOrders():
    UID = int(request.form['UID'])
    # print("UID:", UID)  # Debugging
    db = get_db()
    rst = db.cursor().execute(
        '''
        select 
            O_unique_number,
            case
                when O_status = 0 then 'Pending'
                when O_status = 1 then 'Finished'
                else 'Cancelled'
            end as Status, 
            strftime('%Y/%m/%d %H:%M', O_start_time) as start_time, 
            case
                when O_end_time is not NULL then strftime('%Y/%m/%d %H:%M', O_end_time)
                else ''
            end as end_time, S_name, OID, O_amount
        from Process_Order natural join Orders natural join Stores
        where UID = ?
        ''', (UID,)
    ).fetchall()
    # print("Result set:", rst)  # Debugging
    table = {'tableRow': []}
    append = table['tableRow'].append
    for unique_number, Status, start_time, end_time, S_name, OID, O_amount in rst:
        append({'unique_number': unique_number, 'Status': Status, 'start_time': start_time, 'end_time': end_time, 'S_name': S_name,
                'OID': OID, 'total_price': O_amount})
    # print("Table:", table['tableRow'])
    response = jsonify(table)
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


def get_products_from_db():

    db = get_db()
    rst = db.cursor().execute(
            "SELECT * FROM Products"
        ).fetchall()

    # conn.close()
