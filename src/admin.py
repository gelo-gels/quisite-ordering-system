import base64
import sqlite3
import json
from .login import login_required
from . import get_db
from flask import (
    Blueprint, request,
    session, redirect, url_for,
    json, jsonify, flash
)

manager = Blueprint('manager', __name__)

@manager.route('/search-ShopOrders', methods=['POST'])
def search_ShopOrders():
    UID = int(request.form['UID'])
    db = get_db()
    rst = db.cursor().execute(
        '''
        select SID
        from Stores
        where S_owner = ?
        ''', (UID,)
    ).fetchone()
    table = {'tableRow': []}
    append = table['tableRow'].append
    if rst is not None:
        SID = rst
        rst = db.cursor().execute(
            '''
            select OID,
                case
                    when O_status = 0 then 'Not finished'
                    when O_status = 1 then 'Finished'
                    else 'Canceled'
                end as Status,
                strftime('%Y/%m/%d %H:%M', O_start_time) as start_time, 
                case
                    when O_end_time is not NULL then strftime('%Y/%m/%d %H:%M', O_end_time)
                    else ''
                end as end_time,
                S_name, O_amount
            from Orders natural join Stores
            where SID = ?
            ''', (SID[0],)
        ).fetchall()
        for OID, Status, start_time, end_time, S_name, O_amount in rst:
            append({'Status': Status, 'start_time': start_time, 'end_time': end_time, 'S_name': S_name,
                    'OID': OID, 'total_price': O_amount})
    print(table['tableRow'])
    response = jsonify(table)
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@manager.route("/search-transactionRecord", methods=['POST'])
def search_transactionRecord():
    UID = request.form['UID']
    db = get_db()
    rst = db.cursor().execute(
        '''
        with Shop_Name(TID, S_name) as (
                select TID, S_name 
                from Transaction_Record left join Stores
                on T_Object = S_owner
            ),
            Subj_Name(TID, Subj_name) as (
                select TID, U_name as Subj_name
                from Transaction_Record, Users
                where T_Subject = UID
            ),
            Obj_Name(TID, Obj_name) as (
                select TID, U_name as Obj_name
                from Transaction_Record, Users
                where T_Object = UID
            )
        select TID, 
            case 
                when T_action = 2 then 'Recharge'
                when T_action = 1 then 'Recieve'
                when T_action = 0 then 'Payment'
            end as Action, 
            strftime('%Y/%m/%d %H:%M', T_time) as Time,
            case
                when T_action = 2 then Subj_name
                when T_action = 1 and is_refund = 0 then Obj_name
                when T_action = 1 and is_refund = 1 then S_name
                when T_action = 0 and is_refund = 0 then S_name
                when T_action = 0 and is_refund = 1 then Obj_name
            end as Trader,
            T_amount
        from Transaction_Record natural join Subj_Name natural join Obj_Name natural join Shop_Name
        where T_Subject = ?
        ''', (UID,)
    ).fetchall()
    transaction = [{'TID': TID, 'Action': Action, 'Time': Time, 'Trader': Trader, 'T_amount': T_amount}
                   for TID, Action, Time, Trader, T_amount in rst]
    table = {'tableRow': transaction}
    print(table['tableRow'])
    response = jsonify(table)
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@manager.route("/order-delete", methods=['POST'])
def order_delete():
    delete_OID = int(request.form['OID'])
    is_shopowner = request.form['is_shopowner']
    print("delete_OID: ", delete_OID, "is_shopowner? ", is_shopowner)
    # get user ID and shop owner ID
    db = get_db()
    customer_ID = db.cursor().execute(
        'select UID from Process_Order where OID = ?', (delete_OID, )
    ).fetchone()[0]
    SID = db.cursor().execute(
        'select SID from Orders where OID = ?', (delete_OID, )
    ).fetchone()[0]
    shop_owner_ID = db.cursor().execute(
        'select S_owner from Stores where SID = ?', (SID, )
    ).fetchone()[0]
    print("customer_ID: ", customer_ID, "shop_owner_ID: ", shop_owner_ID)

    # get canceled order data from db
    rst = db.cursor().execute("""
        select * 
        from Orders 
        where OID = ?
        """, (delete_OID, )).fetchone()

    if rst is None:
        return jsonify('Order not found'), 500
    try:
        # check if order is finished
        if rst['O_status'] == 0:
            # update order status to 'calceled'
            db.cursor().execute(
                'update Orders set O_status = -1 where OID = ?', (delete_OID, )
            )
        else:
            return jsonify('Order is already finished / canceled'), 500
        # update process order status to 'owner canceled' or 'user canceled'
        if is_shopowner == 'true':
            print("Shopowner cancels order")
            db.cursor().execute(
                'update Process_Order set PO_type = 3 where OID = ?', (
                    delete_OID, )
            )
        elif is_shopowner == 'false':
            print("User cancels order")
            db.cursor().execute(
                'update Process_Order set PO_type = 1 where OID = ?', (
                    delete_OID, )
            )
        # refund: add transaction record and update user balance
        # add transaction record: user <- shop
        db.cursor().execute('''
            insert into Transaction_Record (T_action, T_amount, is_refund, T_Subject, T_Object)
            values (?, ?, ?, ?, ?)
        ''', (1, rst['O_amount'], 1, customer_ID, shop_owner_ID))
        # add transaction record: shop -> user
        db.cursor().execute('''
            insert into Transaction_Record (T_action, T_amount, is_refund, T_Subject, T_Object)
            values (?, ?, ?, ?, ?)
        ''', (0, -rst['O_amount'], 1, shop_owner_ID, customer_ID))
        # update user balance
        db.cursor().execute('''
            update Users set U_balance = U_balance + ? where UID = ?
        ''', (rst['O_amount'], customer_ID))
        db.cursor().execute('''
            update Users set U_balance = U_balance - ? where UID = ?
        ''', (rst['O_amount'], shop_owner_ID))

        # update product quantity
        rst = db.cursor().execute('''
            select O_details
            from Orders
            where OID = ?
        ''', (delete_OID, )).fetchone()[0]
        product_details = json.loads(rst)['Products']
        # get all PIDs and Quantities
        PIDs = []
        Quantities = []
        for product in product_details:
            print(product.keys())
            PIDs.append(product['PID'])
            Quantities.append(product['Order_quantity'])

        # add quantity back to product, Note: if PID doesn't exist, this function does nothing(no error)
        for PID, quantity in zip(PIDs, Quantities):
            print(PID, quantity)
            db.cursor().execute(
                'update Products set P_quantity = P_quantity + ? where PID = ?', (
                    quantity, PID)
            )

    except Exception as e:
        print("ERROR : " + str(e))
        db.rollback()
        response = jsonify('cancel order failed')
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 500
        return response

    db.commit()
    response = jsonify({'msg': 'cancel order successfully'})
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@manager.route("/order-complete", methods=['POST'])
def order_complete():
    complete_OID = int(request.form['OID'])
    print("complete_OID: ", complete_OID)

    # get user ID and shop owner ID
    db = get_db()
    customer_ID = db.cursor().execute(
        'select UID from Process_Order where OID = ?', (complete_OID, )
    ).fetchone()[0]
    SID = db.cursor().execute(
        'select SID from Orders where OID = ?', (complete_OID, )
    ).fetchone()[0]
    shop_owner_ID = db.cursor().execute(
        'select S_owner from Stores where SID = ?', (SID, )
    ).fetchone()[0]
    print("customer_ID: ", customer_ID, "shop_owner_ID: ", shop_owner_ID)

    # get completed order data from db
    rst = db.cursor().execute("""
        select * 
        from Orders 
        where OID = ?
        """, (complete_OID, )).fetchone()

    if rst is None:
        return jsonify('Order not found'), 500
    try:
        # check if order is finished
        if rst['O_status'] == 0:
            # update order status to 'completed' and set end time
            db.cursor().execute('''
                update Orders set O_status = 1, O_end_time = datetime('now', 'localtime') where OID = ?
                ''', (complete_OID, ))
        else:
            return jsonify('Order is already finished / canceled'), 500

        # update process order status to 'order completed'
        db.cursor().execute(
            'update Process_Order set PO_type = 2 where OID = ?', (
                complete_OID, )
        )

    except:
        db.rollback()
        response = jsonify('complete order failed')
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 500
        return response

    db.commit()
    response = jsonify({'msg': 'complete order successfully'})
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response

@manager.route("/edit_price_and_quantity", methods=['POST'])
def edit_price_and_quantity():
    edit_price = request.form['edit_price']
    edit_quantity = request.form['edit_quantity']
    edit_PID = request.form['edit_PID']

    # check any blanks:
    for k, v in request.form.items():
        if v == '':
            flash(f"Please check: '{k}' is not filled")
            return redirect(url_for("main.nav"))

    try:
        int(edit_price)
        int(edit_quantity)
    except ValueError:
        flash("Invalid Value")
        return redirect(url_for("main.nav"))

    # check formats:
    # price and quantity
    if(int(edit_price) < 0 or int(edit_quantity) < 0):
        flash("Please check: price and quantity can only be non-negatives")
        return redirect(url_for("main.nav"))

    # update price & quantity
    db = get_db()
    db.cursor().execute("""
        update Products
        set P_price = ?, P_quantity = ?
        where PID = ?
    """, (edit_price, edit_quantity, edit_PID))
    db.commit()

    flash("Edit Successful")
    return redirect(url_for('main.nav'))


@manager.route("/delete_product", methods=['POST'])
def delete_product():
    delete_PID = request.form['delete_PID']

    # delete product from Products db
    db = get_db()
    db.cursor().execute("""
        delete from Products
        where PID = ?
    """, (delete_PID,))
    db.commit()

    flash("Delete Successful")
    return redirect(url_for('main.nav'))


#BELOW THIS LINE ARE REDUNDANT FUNCTIONS

@manager.route("/shop_register", methods=['POST'])
@login_required
def shop_register():
    # get input values
    user_info = session.get('user_info')
    UID = user_info['UID']
    owner_phone = user_info['U_phone']
    shop_name = request.form['shop_name']
    shop_category = request.form['shop_category']
    # shop_latitude = request.form['shop_latitude']
    # shop_longitude = request.form['shop_longitude']

    # check any blanks:
    for k, v in request.form.items():
        if v == '':
            flash(f"Please check: '{k}' is not filled")
            return redirect(url_for("main.nav"))

    # check formats:
    # latitude and longitude
    # try:
    #     latitude = float(shop_latitude)
    #     longitude = float(shop_longitude)
    # except ValueError:
    #     flash("Please check: locations can only be float")
    #     return redirect(url_for("main.nav"))

    # if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
    #     flash("Please check: locations not possible")
    #     return redirect(url_for("main.nav"))

    # store newly registered store informations
    db = get_db()
    try:
        shop_info = db.cursor().execute('''
            insert into Stores (S_name, S_latitude, S_longitude, S_phone, S_foodtype, S_owner)
            values (?, ?, ?, ?, ?, ?)
        ''', (shop_name, longitude, owner_phone, shop_category, UID))
        # print(shop_name, latitude, longitude, owner_phone, shop_category, UID)
    except sqlite3.IntegrityError:
        flash("shop name has been registered !!")
        return redirect(url_for("main.nav"))
    session['shop_info'] = dict(shop_info)
    db.commit()

    # change user's type to owner
    db = get_db()
    try:
        user_info = db.cursor().execute('''
            update Users
            set U_type = ?
            where UID = ?
        ''', (1, UID))
    except sqlite3.IntegrityError:
        flash("show owner update failed")
        return redirect(url_for("main.nav"))
    # session['user_info'] = dict(user_info)
    db.commit()

    # Register successfully
    flash("Shop registered successfully")
    return redirect(url_for("main.nav"))


@manager.route("/register-shop_name-check", methods=['POST'])
def register_shop_name_check():
    '''
    checks if shop_name is already registered
    helper function handling ajax request
    '''
    shop_name = request.form.get('shop_name')
    db = get_db()
    rst = db.cursor().execute(
        "select S_name from Stores where S_name = ?", (shop_name,)).fetchone()

    # empty string
    if shop_name is None or shop_name == '':
        response = jsonify(
            '<span style=\'color:red;\'>Please enter your shop name</span>')
    # account used
    elif rst:
        response = jsonify(
            '<span style=\'color:red;\'>Shop name has been registered</span>')
    else:
        response = jsonify(
            '<span style=\'color:green;\'>Shop name has not been registered</span>')

    # **Important**
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@manager.route("/shop_add", methods=['POST'])
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
        return redirect(url_for("main.nav"))

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
            return redirect(url_for("main.nav"))
    if(meal_pic.filename == ''):
        flash("Please upload a picture for the product")
        return redirect(url_for("main.nav"))

    # get the extension of the file ex: png, jpeg
    meal_pic_extension = meal_pic.filename.split('.')[1]

    # check formats:
    # price and quantity
    if(int(meal_price) < 0 or int(meal_quantity) < 0):
        flash("Please check: price and quantity can only be non-negatives")
        return redirect(url_for("main.nav"))

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
        return redirect(url_for("main.nav"))
    # session['product_info'] = dict(product_info)       # not sure if needed
    db.commit()

    # Register successfully
    flash("Product added successfully")
    return redirect(url_for("main.nav"))