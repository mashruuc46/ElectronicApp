from flask import Flask, render_template, url_for, flash, redirect
from flask import request, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, relationship, joinedload
from database_setup import Base, Catagory, Item, User
from flask import make_response, flash
from oauth2client.client import flow_from_clientsecrets, FlowExchangeError
from flask import session as login_session
import httplib2
import requests
import json
import random
import string


CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']

app = Flask(__name__)

app.config['SECRET_KEY'] = '6d22391e94319de409da02ff3f19dd83'

engine = create_engine('sqlite:///catalog.db?check_same_thread=False')

Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

# Create anti-forgery state token


@app.route('/login')
def Login():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(
            json.dumps('Current user is already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    print data['email']
    if session.query(User).filter_by(email=data['email']).count() != 0:
        current_user = session.query(User).filter_by(email=data['email']).one()
    else:
        newUser = User(name=data['name'],
                       email=data['email'])
        session.add(newUser)
        session.commit()
        current_user = newUser

    login_session['user_id'] = current_user.id
    print current_user.id

    output = ''
    output += login_session['username']
    output += login_session['picture']
    return output


@app.route('/gdisconnect')
def gdisconnect():
    access_token = login_session['access_token']
    print 'In gdisconnect access token is %s', access_token
    print 'User name is: '
    print login_session['username']
    if access_token is None:
        print 'Access Token is None'
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = ('https://accounts.google.com/o/oauth2/revoke?token=%s'
           % access_token)
    h = httplib2.Http()
    result = \
        h.request(uri=url, method='POST', body=None, headers={
                  'content-type': 'application/x-www-form-urlencoded'})[0]

    print url
    print 'result is '
    print result
    if result['status'] == '200':
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        del login_session['user_id']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        flash("Successfully logged out", "success")
        return redirect('/index')
        # return response
    else:
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


# Show all Category
@app.route("/")
@app.route("/index")
def showCatagory():
    # Show all Restaurants
    catagory = session.query(Catagory).all()
    items = session.query(Item).all()
    return render_template('index.html', catagory=catagory, items=items)


# Show New Items
@app.route("/")
@app.route("/item/new/")
def showNewItem():

    return render_template('new_item.html')

# Display catagory Item


@app.route('/catagory/<int:catagory_id>/')
@app.route('/catagory/<int:catagory_id>/item/')
def showItem(catagory_id):
    """Show all Items"""
    catagory = session.query(Catagory).filter_by(
        id=catagory_id).one()
    items = session.query(Item).filter_by(
        catagory_id=catagory_id).all()
    return render_template('items.html', items=items,
                           catagory=catagory)

# Create new Catagory


@app.route('/catagory/item/new', methods=['GET', 'POST'])
def createNewItem():
    # check if username is logged in
    if 'username' not in login_session:
        return redirect('/login')
    user_id = login_session['user_id']
    allcatagory = session.query(Catagory).all()
    if request.method == 'POST':
        if request.form['item_catagory_id'] == "":
            flash('Please select a catagory name.', "danger")
            return render_template('new_item.html',
                                   allcatagory=allcatagory)
        catagory = session.query(Catagory).filter_by(
            id=request.form['item_catagory_id']).one()
        if catagory.user_id != login_session['user_id']:
            flash('Sorry, you are not allowed to Add a menu', "danger")
            return redirect(url_for('index'))
        newItem = Item(name=request.form['item_name'],
                       description=request.form['item_description'],
                       price=request.form['item_price'],
                       catagory_id=request.form['item_catagory_id'],
                       user_id=user_id)
        session.add(newItem)
        flash('Successfully created', 'success')
        session.commit()
        return redirect(url_for('showNewItem',
                                _id=request.form['item_catagory_id'
                                                 ]))
    else:
        return render_template('new_item.html', allcatagory=allcatagory)


# Selecting a specific catagory Item
@app.route('/catagory/<string:catagory_name>/item/')
def showspecificcatagoryMenu(catagory_name):
    """Show all Items"""
    catagory = session.query(Catagory).all()
    specific_res_name = session.query(Catagory).filter_by(
        name=catagory_name).one()
    items = session.query(Item).filter_by(
        catagory_id=specific_res_name.id).all()
    countitem = session.query(Item).filter_by(
        catagory_id=specific_res_name.id).count()
    return render_template('specific_catagory_item.html',
                           items=items, catagory=catagory,
                           specific_res_name=specific_res_name,
                           countitem=countitem)

# Selecting a specific item


@app.route('/catagory/<string:catagory_name>/<string:item_name>/')
def showSpecificItem(catagory_name, item_name):
    catagory = session.query(Catagory).filter_by(
        name=catagory_name).one()
    item = session.query(Item).filter_by(
        name=item_name).one()
    return render_template('specific_item.html',
                           item=item, catagory=catagory)

# Create new catagory


@app.route('/catagory/new/', methods=['GET', 'POST'])
def createNewCatagory():
    if 'username' not in login_session:
        return redirect('/login')
    user_id = login_session['user_id']
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        newcatagory = Catagory(name=request.form['catagory_name'],
                               user_id=user_id)
        session.add(newcatagory)
        flash('Successfully created', "success")
        session.commit()
        return redirect(url_for('showCatagory'))
    else:
        return render_template('new_catagory.html')


# Delete Catagory
@app.route('/catagory/<int:catagory_id>/catagory/delete',
           methods=['GET', 'POST'])
def deleteCatagory(catagory_id):
    # check if username is logged in
    if 'username' not in login_session:
        return redirect('/login')
    delCatagory = session.query(Catagory).filter_by(
        id=catagory_id).one()
    if delCatagory.user_id != login_session['user_id']:
        flash('Sorry, you are not allowed to Delete', "danger")
        return redirect(url_for('showCatagory'))
    if request.method == 'POST':
        session.delete(delCatagory)
        session.commit()
        flash('Successfully Deleted', 'success')
        return redirect(url_for('showCatagory'))
    else:
        return render_template('delete_catagory.html',
                               delCatagory=delCatagory)

# Edit Catagory


@app.route('/catagory/<int:catagory_id>/catagory/edit',
           methods=['GET', 'POST'])
def editCatagory(catagory_id):
    # check if username is logged in
    if 'username' not in login_session:
        return redirect('/login')
    editCatagory = session.query(Catagory).filter_by(
        id=catagory_id).one()
    if editCatagory.user_id != login_session['user_id']:
        flash('Sorry, you are not allowed to edit', "danger")
        return redirect(url_for('showNewItem'))
    if request.method == 'POST':
        if request.form['catagory_name']:
            editCatagory.name = request.form['catagory_name']
            session.add(editCatagory)
            session.commit()
            flash('Successfully Edited', 'success')
            return redirect(url_for('showCatagory'))
    else:
        return render_template('edit_catagory.html',
                               catagory_id=catagory_id,
                               editCatagory=editCatagory)


# Edit exists item
@app.route('/catagory/<int:catagory_id>/item/<int:item_id>/edit',
           methods=['GET', 'POST'])
def editMenu(catagory_id, item_id):
    # check if username is logged in
    if 'username' not in login_session:
        return redirect('/login')
    items = session.query(Item).filter_by(id=item_id).one()
    if items.user_id != login_session['user_id']:
        flash('Sorry, you are not allowed to edit', "danger")
        return redirect(url_for('showItem', catagory_id=catagory_id))
    if request.method == 'POST':
        if request.form['item_name']:
            items.name = request.form['item_name']
        if request.form['item_description']:
            items.description = request.form['item_description']
        if request.form['item_price']:
            items.price = request.form['item_price']
            session.add(items)
            session.commit()
            flash('Successfully Edited', 'success')
            return redirect(url_for('showItem',
                                    catagory_id=catagory_id))
    else:
        return render_template('edit_item.html', catagory_id=catagory_id,
                               item_id=item_id, item=items)

# Delete  item


@app.route('/catagory/<int:catagory_id>/item/<int:item_id>/delete',
           methods=['GET', 'POST'])
def deleteMenu(catagory_id, item_id):

    # check if username is logged in
    if 'username' not in login_session:
        return redirect('/login')
    item = session.query(Item).filter_by(id=item_id).one()
    if item.user_id != login_session['user_id']:
        flash('Sorry, you are not allowed to delete', "danger")
        return redirect(url_for('showItem', catagory_id=catagory_id))

    if request.method == 'POST':
        session.delete(item)
        session.commit()
        flash('Successfully Deleted', 'success')
        return redirect(url_for('showItem', catagory_id=catagory_id))
    else:
        return render_template('delete_item.html',
                               catagory_id=catagory_id,
                               item_id=item_id,
                               item=item)

# JSON  View


@app.route('/json')
def jSONView():
    """Return JSON for all catagory information"""
    catagory = session.query(Catagory).options(
        joinedload(Catagory.items)).all()
    return jsonify(catagory=[dict(c.serialize, items=[i.serialize
                                                      for i in c.items])
                             for c in catagory])


@app.route('/catagory/json')
def categoriesJSON():
    """Return JSON for all the categories"""
    categorys = session.query(Catagory).all()
    return jsonify(categories=[c.serialize for c in categorys])


@app.route('/catagory/<int:catagory_id>/json')
def categoryJSON(category_id):
    """Return JSON of all the items for a catagory"""
    catagory = session.query(Catagory).filter_by(id=catagory_id).one()
    items = session.query(Item).filter_by(
        catagory_id=catagory_id).all()
    return jsonify(items=[i.serialize for i in items])


@app.route('/item/json')
def itemsJSON():

    items = session.query(Item).all()
    return jsonify(items=[i.serialize for i in items])


@app.route('/catagory/<int:catagory_id>/item/<int:item_id>/json')
def itemJSON(category_id, item_id):
    """Return JSON for an item"""
    item = session.query(Item).filter_by(id=item_id).one()
    return jsonify(item=item.serialize)


if __name__ == '__main__':
    app.config['SECRET_KEY'] = '6d22391e94319de409da02ff3f19dd83'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
