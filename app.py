from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets
import os

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'hotel_reservation_db'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# CSRF Token Generation
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

def validate_csrf_token(token):
    return token == session.get('_csrf_token')

# ============ PUBLIC ROUTES ============

# Updated index() route for app.py
# Replace your current index() function with this version

@app.route('/')
def index():
    """Homepage with featured rooms and camping spots"""
    try:
        cur = mysql.connection.cursor()
        
        # Get featured rooms with pricing
        cur.execute("""
            SELECT r.*, 
                   (SELECT MIN(price) FROM room_listed_prices WHERE room_id = r.id) as starting_price
            FROM rooms r 
            WHERE r.is_active = 1 
            ORDER BY r.created_at DESC 
            LIMIT 6
        """)
        featured_rooms = cur.fetchall()
        
        # Get featured camping spots
        cur.execute("""
            SELECT * 
            FROM camping_spots 
            WHERE status = 'available' 
            ORDER BY created_at DESC 
            LIMIT 6
        """)
        featured_camping = cur.fetchall()
        
        cur.close()
        
        return render_template('index.html', 
                             featured_rooms=featured_rooms,
                             featured_camping=featured_camping)
    except Exception as e:
        flash(f'Error loading homepage: {str(e)}', 'error')
        return render_template('index.html', 
                             featured_rooms=[],
                             featured_camping=[])

@app.route('/search-rooms', methods=['GET', 'POST'])
def search_rooms():
    """Search available rooms based on criteria"""
    if request.method == 'POST':
        csrf_token = request.form.get('csrf_token')
        if not validate_csrf_token(csrf_token):
            flash('Invalid security token. Please try again.', 'error')
            return redirect(url_for('index'))
        
        check_in = request.form.get('check_in')
        check_out = request.form.get('check_out')
        num_rooms = int(request.form.get('num_rooms', 1))
        adults = int(request.form.get('adults', 1))
        children = int(request.form.get('children', 0))
        
        # Validate dates
        try:
            check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
            check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()
            
            if check_in_date < datetime.now().date():
                flash('Check-in date cannot be in the past', 'error')
                return redirect(url_for('index'))
            
            if check_out_date <= check_in_date:
                flash('Check-out date must be after check-in date', 'error')
                return redirect(url_for('index'))
        except ValueError:
            flash('Invalid date format', 'error')
            return redirect(url_for('index'))
        
        # Store search criteria in session
        session['search_data'] = {
            'check_in': check_in,
            'check_out': check_out,
            'num_rooms': num_rooms,
            'adults': adults,
            'children': children
        }
        
        return redirect(url_for('offer_rooms'))
    
    return redirect(url_for('index'))

@app.route('/offer-rooms')
def offer_rooms():
    """Display available rooms based on search criteria"""
    search_data = session.get('search_data')
    
    if not search_data:
        flash('Please perform a search first', 'warning')
        return redirect(url_for('index'))
    
    try:
        check_in = search_data['check_in']
        check_out = search_data['check_out']
        num_rooms = search_data['num_rooms']
        adults = search_data['adults']
        children = search_data['children']
        
        total_guests = adults + children
        nights = (datetime.strptime(check_out, '%Y-%m-%d') - datetime.strptime(check_in, '%Y-%m-%d')).days
        
        cur = mysql.connection.cursor()
        
        # Find available rooms that match capacity
        cur.execute("""
            SELECT DISTINCT r.*, 
                   rlp.price as price_per_night,
                   rpt.name as rate_plan_name
            FROM rooms r
            JOIN room_listed_prices rlp ON r.id = rlp.room_id
            JOIN rate_plans rp ON rlp.rate_plan_id = rp.id
            JOIN rate_plan_types rpt ON rp.type_id = rpt.id
            WHERE r.is_active = 1 
            AND r.capacity >= %s
            AND r.id NOT IN (
                SELECT DISTINCT room_id 
                FROM reservations 
                WHERE status != 'cancelled'
                AND NOT (check_out_date <= %s OR check_in_date >= %s)
            )
            ORDER BY rlp.price ASC
        """, (total_guests, check_in, check_out))
        
        available_rooms = cur.fetchall()
        
        # Calculate total price for each room
        for room in available_rooms:
            room['total_price'] = room['price_per_night'] * nights * num_rooms
            room['nights'] = nights
        
        cur.close()
        
        return render_template('offer_rooms.html', 
                             rooms=available_rooms, 
                             search_data=search_data)
    
    except Exception as e:
        flash(f'Error fetching available rooms: {str(e)}', 'error')
        return redirect(url_for('index'))
    # ============================================================
# CAMPING BOOKING ROUTES
# Add these routes to your app.py file
# ============================================================

# ============ PUBLIC CAMPING ROUTES ============

@app.route('/camping')
def camping_spots():
    """Display all available camping spots"""
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT * FROM camping_spots 
            WHERE status = 'available' 
            ORDER BY price_per_night ASC
        """)
        spots = cur.fetchall()
        cur.close()
        return render_template('camping/camping_spots.html', spots=spots)
    except Exception as e:
        flash(f'Error loading camping spots: {str(e)}', 'error')
        return render_template('camping/camping_spots.html', spots=[])

@app.route('/camping/<int:spot_id>')
def camping_spot_detail(spot_id):
    """Display details of a specific camping spot"""
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM camping_spots WHERE id = %s", (spot_id,))
        spot = cur.fetchone()
        cur.close()
        
        if not spot:
            flash('Camping spot not found', 'error')
            return redirect(url_for('camping_spots'))
        
        return render_template('camping/camping_detail.html', spot=spot)
    except Exception as e:
        flash(f'Error loading camping spot: {str(e)}', 'error')
        return redirect(url_for('camping_spots'))

@app.route('/search-camping', methods=['POST'])
def search_camping():
    """Search available camping spots based on criteria"""
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token. Please try again.', 'error')
        return redirect(url_for('index'))
    
    check_in = request.form.get('check_in')
    check_out = request.form.get('check_out')
    num_guests = int(request.form.get('num_guests', 1))
    
    # Validate dates
    try:
        check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
        check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()
        
        if check_in_date < datetime.now().date():
            flash('Check-in date cannot be in the past', 'error')
            return redirect(url_for('index'))
        
        if check_out_date <= check_in_date:
            flash('Check-out date must be after check-in date', 'error')
            return redirect(url_for('index'))
    except ValueError:
        flash('Invalid date format', 'error')
        return redirect(url_for('index'))
    
    # Store search criteria in session
    session['camping_search'] = {
        'check_in': check_in,
        'check_out': check_out,
        'num_guests': num_guests
    }
    
    return redirect(url_for('offer_camping'))

@app.route('/offer-camping')
def offer_camping():
    """Display available camping spots based on search criteria"""
    search_data = session.get('camping_search')
    
    if not search_data:
        flash('Please perform a search first', 'warning')
        return redirect(url_for('camping_spots'))
    
    try:
        check_in = search_data['check_in']
        check_out = search_data['check_out']
        num_guests = search_data['num_guests']
        
        nights = (datetime.strptime(check_out, '%Y-%m-%d') - datetime.strptime(check_in, '%Y-%m-%d')).days
        
        cur = mysql.connection.cursor()
        
        # Find available camping spots that match capacity and are not booked
        cur.execute("""
            SELECT * FROM camping_spots
            WHERE status = 'available' 
            AND capacity >= %s
            AND id NOT IN (
                SELECT DISTINCT camping_spot_id 
                FROM camping_bookings 
                WHERE status != 'cancelled'
                AND NOT (check_out_date <= %s OR check_in_date >= %s)
            )
            ORDER BY price_per_night ASC
        """, (num_guests, check_in, check_out))
        
        available_spots = cur.fetchall()
        
        # Calculate total price for each spot
        for spot in available_spots:
            spot['total_price'] = spot['price_per_night'] * nights
            spot['nights'] = nights
        
        cur.close()
        
        return render_template('camping/offer_camping.html', 
                             spots=available_spots, 
                             search_data=search_data)
    
    except Exception as e:
        flash(f'Error fetching available camping spots: {str(e)}', 'error')
        return redirect(url_for('camping_spots'))

@app.route('/camping-booking/<int:spot_id>')
def camping_booking_form(spot_id):
    """Display camping booking form"""
    search_data = session.get('camping_search')
    
    if not search_data:
        flash('Please perform a search first', 'warning')
        return redirect(url_for('camping_spots'))
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM camping_spots WHERE id = %s AND status = 'available'", (spot_id,))
        spot = cur.fetchone()
        cur.close()
        
        if not spot:
            flash('Camping spot not found', 'error')
            return redirect(url_for('offer_camping'))
        
        nights = (datetime.strptime(search_data['check_out'], '%Y-%m-%d') - 
                 datetime.strptime(search_data['check_in'], '%Y-%m-%d')).days
        
        total_price = spot['price_per_night'] * nights
        
        return render_template('camping/camping_booking.html', 
                             spot=spot, 
                             search_data=search_data,
                             nights=nights,
                             total_price=total_price)
    
    except Exception as e:
        flash(f'Error loading booking form: {str(e)}', 'error')
        return redirect(url_for('offer_camping'))

@app.route('/create-camping-booking/<int:spot_id>', methods=['POST'])
def create_camping_booking(spot_id):
    """Create a new camping booking"""
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token. Please try again.', 'error')
        return redirect(url_for('camping_booking_form', spot_id=spot_id))
    
    search_data = session.get('camping_search')
    if not search_data:
        flash('Session expired. Please search again.', 'error')
        return redirect(url_for('camping_spots'))
    
    # Get form data
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    special_requests = request.form.get('special_requests', '')
    
    try:
        cur = mysql.connection.cursor()
        
        # Check if spot is still available
        cur.execute("""
            SELECT id FROM camping_bookings 
            WHERE camping_spot_id = %s 
            AND status != 'cancelled'
            AND NOT (check_out_date <= %s OR check_in_date >= %s)
        """, (spot_id, search_data['check_in'], search_data['check_out']))
        
        if cur.fetchone():
            flash('This camping spot is no longer available for the selected dates', 'error')
            cur.close()
            return redirect(url_for('offer_camping'))
        
        # Get or create client
        cur.execute("SELECT id FROM clients WHERE email = %s", (email,))
        client = cur.fetchone()
        
        if client:
            client_id = client['id']
        else:
            cur.execute("""
                INSERT INTO clients (first_name, last_name, email, phone)
                VALUES (%s, %s, %s, %s)
            """, (first_name, last_name, email, phone))
            client_id = cur.lastrowid
        
        # Get spot details
        cur.execute("SELECT price_per_night FROM camping_spots WHERE id = %s", (spot_id,))
        spot = cur.fetchone()
        
        # Calculate total price
        nights = (datetime.strptime(search_data['check_out'], '%Y-%m-%d') - 
                 datetime.strptime(search_data['check_in'], '%Y-%m-%d')).days
        total_price = spot['price_per_night'] * nights
        
        # Create camping booking
        cur.execute("""
            INSERT INTO camping_bookings 
            (client_id, camping_spot_id, check_in_date, check_out_date, 
             num_guests, total_price, special_requests, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmed')
        """, (client_id, spot_id, search_data['check_in'], search_data['check_out'],
              search_data['num_guests'], total_price, special_requests))
        
        booking_id = cur.lastrowid
        mysql.connection.commit()
        cur.close()
        
        # Clear search session
        session.pop('camping_search', None)
        
        flash(f'Camping booking confirmed! Booking ID: #{booking_id}', 'success')
        return redirect(url_for('camping_confirmation', booking_id=booking_id))
    
    except Exception as e:
        flash(f'Error creating camping booking: {str(e)}', 'error')
        return redirect(url_for('camping_booking_form', spot_id=spot_id))

@app.route('/camping-confirmation/<int:booking_id>')
def camping_confirmation(booking_id):
    """Display camping booking confirmation"""
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT cb.*, cs.name as spot_name, cs.location,
                   c.first_name, c.last_name, c.email, c.phone
            FROM camping_bookings cb
            JOIN camping_spots cs ON cb.camping_spot_id = cs.id
            JOIN clients c ON cb.client_id = c.id
            WHERE cb.id = %s
        """, (booking_id,))
        
        booking = cur.fetchone()
        cur.close()
        
        if not booking:
            flash('Booking not found', 'error')
            return redirect(url_for('camping_spots'))
        
        nights = (booking['check_out_date'] - booking['check_in_date']).days
        booking['nights'] = nights
        
        return render_template('camping/camping_confirmation.html', booking=booking)
    
    except Exception as e:
        flash(f'Error loading confirmation: {str(e)}', 'error')
        return redirect(url_for('camping_spots'))

# ============ ADMIN CAMPING ROUTES ============

@app.route('/admin/camping-spot/add', methods=['POST'])
def admin_add_camping_spot():
    """Add a new camping spot"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token', 'error')
        return redirect(url_for('admin_panel'))
    
    name = request.form.get('name')
    location = request.form.get('location')
    capacity = int(request.form.get('capacity'))
    price_per_night = float(request.form.get('price_per_night'))
    description = request.form.get('description')
    image_url = request.form.get('image_url', '')
    amenities = request.form.get('amenities', '')
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO camping_spots 
            (name, location, capacity, price_per_night, description, image_url, amenities, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'available')
        """, (name, location, capacity, price_per_night, description, image_url, amenities))
        mysql.connection.commit()
        cur.close()
        flash('Camping spot added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding camping spot: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/camping-spot/delete/<int:spot_id>', methods=['POST'])
def admin_delete_camping_spot(spot_id):
    """Delete a camping spot"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token', 'error')
        return redirect(url_for('admin_panel'))
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM camping_spots WHERE id = %s", (spot_id,))
        mysql.connection.commit()
        cur.close()
        flash('Camping spot deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting camping spot: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/camping-booking/delete/<int:booking_id>', methods=['POST'])
def admin_delete_camping_booking(booking_id):
    """Delete a camping booking"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token', 'error')
        return redirect(url_for('admin_panel'))
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM camping_bookings WHERE id = %s", (booking_id,))
        mysql.connection.commit()
        cur.close()
        flash('Camping booking deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting camping booking: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

# ============================================================
# UPDATE THE admin_panel() FUNCTION TO INCLUDE CAMPING DATA
# Replace the existing admin_panel function with this updated version:
# ============================================================

@app.route('/admin')
def admin_panel():
    """Admin dashboard - UPDATED VERSION WITH CAMPING"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    try:
        cur = mysql.connection.cursor()
        
        # Get all rooms
        cur.execute("SELECT * FROM rooms ORDER BY created_at DESC")
        rooms = cur.fetchall()
        
        # Get rate plan types
        cur.execute("SELECT * FROM rate_plan_types ORDER BY name")
        rate_plan_types = cur.fetchall()
        
        # Get rate plans with type names
        cur.execute("""
            SELECT rp.*, rpt.name as type_name
            FROM rate_plans rp
            JOIN rate_plan_types rpt ON rp.type_id = rpt.id
            ORDER BY rp.created_at DESC
        """)
        rate_plans = cur.fetchall()
        
        # Get reservations with client and room info
        cur.execute("""
            SELECT r.*, c.first_name, c.last_name, c.email, c.phone,
                   rm.name as room_name, rm.room_number
            FROM reservations r
            JOIN clients c ON r.client_id = c.id
            JOIN rooms rm ON r.room_id = rm.id
            ORDER BY r.created_at DESC
        """)
        reservations = cur.fetchall()
        
        # Get room prices
        cur.execute("""
            SELECT rlp.*, r.name as room_name, rp.name as rate_plan_name
            FROM room_listed_prices rlp
            JOIN rooms r ON rlp.room_id = r.id
            JOIN rate_plans rp ON rlp.rate_plan_id = rp.id
            ORDER BY rlp.created_at DESC
        """)
        room_prices = cur.fetchall()
        
        # Get camping spots
        cur.execute("SELECT * FROM camping_spots ORDER BY created_at DESC")
        camping_spots = cur.fetchall()
        
        # Get camping bookings with client and spot info
        cur.execute("""
            SELECT cb.*, c.first_name, c.last_name, c.email, c.phone,
                   cs.name as spot_name, cs.location
            FROM camping_bookings cb
            JOIN clients c ON cb.client_id = c.id
            JOIN camping_spots cs ON cb.camping_spot_id = cs.id
            ORDER BY cb.created_at DESC
        """)
        camping_bookings = cur.fetchall()
        
        cur.close()
        
        return render_template('admin/admin_panel.html',
                             rooms=rooms,
                             rate_plan_types=rate_plan_types,
                             rate_plans=rate_plans,
                             reservations=reservations,
                             room_prices=room_prices,
                             camping_spots=camping_spots,
                             camping_bookings=camping_bookings)
    except Exception as e:
        flash(f'Error loading admin panel: {str(e)}', 'error')
        return render_template('admin/admin_panel.html')

@app.route('/booking-form/<int:room_id>')
def booking_form(room_id):
    """Display booking form for selected room"""
    search_data = session.get('search_data')
    
    if not search_data:
        flash('Please perform a search first', 'warning')
        return redirect(url_for('index'))
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT r.*, rlp.price as price_per_night, rpt.name as rate_plan_name
            FROM rooms r
            JOIN room_listed_prices rlp ON r.id = rlp.room_id
            JOIN rate_plans rp ON rlp.rate_plan_id = rp.id
            JOIN rate_plan_types rpt ON rp.type_id = rpt.id
            WHERE r.id = %s AND r.is_active = 1
            LIMIT 1
        """, (room_id,))
        
        room = cur.fetchone()
        cur.close()
        
        if not room:
            flash('Room not found', 'error')
            return redirect(url_for('offer_rooms'))
        
        nights = (datetime.strptime(search_data['check_out'], '%Y-%m-%d') - 
                 datetime.strptime(search_data['check_in'], '%Y-%m-%d')).days
        
        total_price = room['price_per_night'] * nights * search_data['num_rooms']
        
        return render_template('booking_form.html', 
                             room=room, 
                             search_data=search_data,
                             nights=nights,
                             total_price=total_price)
    
    except Exception as e:
        flash(f'Error loading booking form: {str(e)}', 'error')
        return redirect(url_for('offer_rooms'))

@app.route('/create-reservation/<int:room_id>', methods=['POST'])
def create_reservation(room_id):
    """Create a new reservation"""
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token. Please try again.', 'error')
        return redirect(url_for('booking_form', room_id=room_id))
    
    search_data = session.get('search_data')
    if not search_data:
        flash('Session expired. Please search again.', 'error')
        return redirect(url_for('index'))
    
    # Get form data
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    special_requests = request.form.get('special_requests', '')
    
    try:
        cur = mysql.connection.cursor()
        
        # Create or get client
        cur.execute("SELECT id FROM clients WHERE email = %s", (email,))
        client = cur.fetchone()
        
        if client:
            client_id = client['id']
        else:
            cur.execute("""
                INSERT INTO clients (first_name, last_name, email, phone)
                VALUES (%s, %s, %s, %s)
            """, (first_name, last_name, email, phone))
            client_id = cur.lastrowid
        
        # Get room price
        cur.execute("""
            SELECT rlp.price 
            FROM room_listed_prices rlp 
            WHERE rlp.room_id = %s 
            LIMIT 1
        """, (room_id,))
        price_info = cur.fetchone()
        
        if not price_info:
            flash('Room pricing not found', 'error')
            return redirect(url_for('offer_rooms'))
        
        nights = (datetime.strptime(search_data['check_out'], '%Y-%m-%d') - 
                 datetime.strptime(search_data['check_in'], '%Y-%m-%d')).days
        
        total_amount = price_info['price'] * nights * search_data['num_rooms']
        
        # Create reservation
        cur.execute("""
            INSERT INTO reservations 
            (client_id, room_id, check_in_date, check_out_date, 
             num_adults, num_children, num_rooms, total_amount, 
             special_requests, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'confirmed')
        """, (client_id, room_id, search_data['check_in'], search_data['check_out'],
              search_data['adults'], search_data['children'], search_data['num_rooms'],
              total_amount, special_requests))
        
        reservation_id = cur.lastrowid
        mysql.connection.commit()
        cur.close()
        
        # Store reservation details for confirmation page
        session['last_reservation'] = {
            'id': reservation_id,
            'room_id': room_id,
            'client_name': f"{first_name} {last_name}",
            'email': email,
            'check_in': search_data['check_in'],
            'check_out': search_data['check_out'],
            'total_amount': total_amount
        }
        
        # Clear search data
        session.pop('search_data', None)
        
        return redirect(url_for('reservation_created'))
    
    except Exception as e:
        flash(f'Error creating reservation: {str(e)}', 'error')
        return redirect(url_for('booking_form', room_id=room_id))

@app.route('/reservation-created')
def reservation_created():
    """Confirmation page after successful booking"""
    reservation = session.get('last_reservation')
    
    if not reservation:
        flash('No reservation found', 'error')
        return redirect(url_for('index'))
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM rooms WHERE id = %s", (reservation['room_id'],))
        room = cur.fetchone()
        cur.close()
        
        return render_template('reservation_created.html', 
                             reservation=reservation, 
                             room=room)
    except Exception as e:
        flash(f'Error loading confirmation: {str(e)}', 'error')
        return redirect(url_for('index'))

# ============ ADMIN AUTH ROUTES ============

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_panel'))
    
    if request.method == 'POST':
        csrf_token = request.form.get('csrf_token')
        if not validate_csrf_token(csrf_token):
            flash('Invalid security token', 'error')
            return render_template('auth/admin_login.html')
        
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT * FROM admins WHERE username = %s AND is_active = 1", (username,))
            admin = cur.fetchone()
            cur.close()
            
            if admin and check_password_hash(admin['password'], password):
                session['admin_logged_in'] = True
                session['admin_id'] = admin['id']
                session['admin_username'] = admin['username']
                flash('Login successful!', 'success')
                return redirect(url_for('admin_panel'))
            else:
                flash('Invalid credentials', 'error')
        except Exception as e:
            flash(f'Login error: {str(e)}', 'error')
    
    return render_template('auth/admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_logged_in', None)
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('admin_login'))

# ============ ADMIN CRUD - ROOMS ============

@app.route('/admin/room/add', methods=['POST'])
def admin_add_room():
    """Add a new room"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token', 'error')
        return redirect(url_for('admin_panel'))
    
    name = request.form.get('name')
    room_number = request.form.get('room_number')
    description = request.form.get('description')
    capacity = int(request.form.get('capacity'))
    size_sqm = float(request.form.get('size_sqm', 0))
    bed_type = request.form.get('bed_type')
    image_url = request.form.get('image_url', '')
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO rooms (name, room_number, description, capacity, 
                             size_sqm, bed_type, image_url, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
        """, (name, room_number, description, capacity, size_sqm, bed_type, image_url))
        mysql.connection.commit()
        cur.close()
        flash('Room added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding room: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/room/delete/<int:room_id>', methods=['POST'])
def admin_delete_room(room_id):
    """Delete a room"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token', 'error')
        return redirect(url_for('admin_panel'))
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM rooms WHERE id = %s", (room_id,))
        mysql.connection.commit()
        cur.close()
        flash('Room deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting room: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

# ============ ADMIN CRUD - RATE PLANS ============

@app.route('/admin/rate-plan/add', methods=['POST'])
def admin_add_rate_plan():
    """Add a new rate plan"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token', 'error')
        return redirect(url_for('admin_panel'))
    
    name = request.form.get('name')
    type_id = int(request.form.get('type_id'))
    description = request.form.get('description', '')
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO rate_plans (name, type_id, description)
            VALUES (%s, %s, %s)
        """, (name, type_id, description))
        mysql.connection.commit()
        cur.close()
        flash('Rate plan added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding rate plan: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/rate-plan/delete/<int:plan_id>', methods=['POST'])
def admin_delete_rate_plan(plan_id):
    """Delete a rate plan"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token', 'error')
        return redirect(url_for('admin_panel'))
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM rate_plans WHERE id = %s", (plan_id,))
        mysql.connection.commit()
        cur.close()
        flash('Rate plan deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting rate plan: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

# ============ ADMIN CRUD - ROOM PRICES ============

@app.route('/admin/room-price/add', methods=['POST'])
def admin_add_room_price():
    """Add room pricing"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token', 'error')
        return redirect(url_for('admin_panel'))
    
    room_id = int(request.form.get('room_id'))
    rate_plan_id = int(request.form.get('rate_plan_id'))
    price = float(request.form.get('price'))
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO room_listed_prices (room_id, rate_plan_id, price)
            VALUES (%s, %s, %s)
        """, (room_id, rate_plan_id, price))
        mysql.connection.commit()
        cur.close()
        flash('Room price added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding room price: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/room-price/delete/<int:price_id>', methods=['POST'])
def admin_delete_room_price(price_id):
    """Delete room pricing"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token', 'error')
        return redirect(url_for('admin_panel'))
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM room_listed_prices WHERE id = %s", (price_id,))
        mysql.connection.commit()
        cur.close()
        flash('Room price deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting room price: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

# ============ ADMIN - RESERVATIONS ============

@app.route('/admin/reservation/delete/<int:reservation_id>', methods=['POST'])
def admin_delete_reservation(reservation_id):
    """Delete a reservation"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    csrf_token = request.form.get('csrf_token')
    if not validate_csrf_token(csrf_token):
        flash('Invalid security token', 'error')
        return redirect(url_for('admin_panel'))
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM reservations WHERE id = %s", (reservation_id,))
        mysql.connection.commit()
        cur.close()
        flash('Reservation deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting reservation: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

# ============ ERROR HANDLERS ============


@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('errors/500.html'), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)