# app/routes/auth.py
from flask import render_template, request, redirect, session, url_for, Flask,flash
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User,Role, ParkingLot,ParkingSpot,Reservation
import os
from datetime import datetime

# Initialize the app and configure the database
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///parking_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.urandom(24)

db.init_app(app)

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        name = request.form['name']
        address = request.form['address']
        pincode = request.form['pincode']

        if User.query.filter_by(email=email).first():
            return 'Email already registered.'

        if not email or not password or not name or not address or not pincode:
            return 'All fields are required.'

        if len(password) < 6:
            return 'Password must be at least 6 characters.'

        if not pincode.isdigit() or len(pincode) != 6:
            return 'Invalid pincode.'

        user_role = Role.query.filter_by(name='user').first()
        if not user_role:
            return 'Default role not found. Please contact admin.', 500

        hashed_pw = generate_password_hash(password)

        new_user = User(
            name=name,
            email=email,
            password_hash=hashed_pw,
            address=address,
            pincode=pincode,
            role_id=user_role.id
        )

        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('register.html', page='register')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session['user'] = user.id
            session['role'] = user.role.name.lower() if user.role else None

            if user.role.name == 'admin' or user.role.name == 'collaborator':
                return redirect(url_for('admin_dashboard'))
            elif session['role'] == 'user':
                return redirect(url_for('user_dashboard'))

        return 'Invalid credentials.'

    return render_template('login.html', page='login')


@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') not in ['admin', 'collaborator']:
        return redirect(url_for('login'))

    query = request.args.get('query', '')
    if query:
        lots = ParkingLot.query.filter(
            (ParkingLot.name.ilike(f"%{query}%")) |
            (ParkingLot.pin_code.ilike(f"%{query}%"))
        ).all()
    else:
        lots = ParkingLot.query.all()
    
    # Chart Data: Reservations per lot
    labels = []
    data = []
    for lot in lots:
        count = sum(spot.reservations.count() for spot in lot.spots)
        labels.append(lot.name)
        data.append(count)
    
    # Count available and occupied spots
    available_spots = sum(
        1 for lot in lots for spot in lot.spots if spot.status == 'A'
    )
    occupied_spots = sum(
        1 for lot in lots for spot in lot.spots if spot.status == 'O'
    )

    # Reservation count per user
    user_data = (
        db.session.query(User.name, db.func.count(Reservation.id))
        .join(Reservation)
        .join(Role)
        .filter(Role.name == 'user')
        .group_by(User.name)
        .all()
    )

    user_labels = [u[0] for u in user_data]
    user_counts = [u[1] for u in user_data]
    
    rating_labels = []
    rating_values = []
    for lot in lots:
        rated_reservations = Reservation.query.join(ParkingSpot).filter(
            ParkingSpot.lot_id == lot.id,
            Reservation.rating != None
        ).all()

        if rated_reservations:
            avg_rating = sum(r.rating for r in rated_reservations) / len(rated_reservations)
            rating_labels.append(lot.name)
            rating_values.append(round(avg_rating, 2))

    return render_template('admin_dashboard.html', lots=lots,query=query,chart_labels=labels,chart_data=data,available_spots=available_spots,occupied_spots=occupied_spots,user_labels=user_labels,user_counts=user_counts,rating_labels=rating_labels,rating_values=rating_values)

@app.route('/admin/create_collaborator', methods=['GET', 'POST'])
def create_collaborator():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        address = request.form['address']
        pincode = request.form['pincode']

        if User.query.filter_by(email=email).first():
            return 'Email already exists.'

        if not name or not email or not password or not address or not pincode:
            return 'All fields are required.'

        if len(password) < 6:
            return 'Password must be at least 6 characters.'

        if not pincode.isdigit() or len(pincode) != 6:
            return 'Invalid pincode.'

        collab_role = Role.query.filter_by(name='collaborator').first()
        if not collab_role:
            collab_role = Role(name='collaborator')
            db.session.add(collab_role)
            db.session.commit()

        hashed_pw = generate_password_hash(password)
        user = User(
            name=name,
            email=email,
            password_hash=hashed_pw,
            address=address,
            pincode=pincode,
            role_id=collab_role.id
        )
        db.session.add(user)
        db.session.commit()

        return redirect(url_for('admin_dashboard'))

    return render_template('create_collaborator.html')

@app.route('/admin/users')
def admin_users():
    if session.get('role') not in ['admin', 'collaborator']:
        return redirect(url_for('login'))
    
    query = request.args.get('query', '')
    users_query = User.query.join(Role).filter(Role.name == 'user')

    if query:
        users_query = users_query.filter(
            (User.name.ilike(f"%{query}%")) |
            (User.email.ilike(f"%{query}%"))
        )

    users = users_query.all()
    user_active_reservations = {
        user.id: Reservation.query.filter_by(user_id=user.id, release_time=None).count() > 0
        for user in users
    }
    return render_template('admin_users.html', users=users, query=query,active_status=user_active_reservations)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    user = User.query.get_or_404(user_id)

    # Check for any active reservation
    active_reservation = Reservation.query.filter_by(user_id=user.id, release_time=None).first()
    if active_reservation:
        return "User has an active parking reservation. Please release the spot before deleting."

    # If no active reservation, proceed with deletion
    Reservation.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()

    return redirect(url_for('admin_users'))


@app.route('/admin/reservations')
def admin_reservations():
    if session.get('role') not in ['admin', 'collaborator']:
        return redirect(url_for('login'))

    filter_status = request.args.get('status', 'all')

    if filter_status == 'active':
        reservations = Reservation.query.filter_by(release_time=None).order_by(Reservation.parking_time.desc()).all()
    elif filter_status == 'completed':
        reservations = Reservation.query.filter(Reservation.release_time.isnot(None)).order_by(Reservation.parking_time.desc()).all()
    else:
        reservations = Reservation.query.order_by(Reservation.parking_time.desc()).all()

    return render_template('admin_reservations.html', reservations=reservations, filter_status=filter_status)

@app.route('/admin/add_lot', methods=['GET', 'POST'])
def add_lot():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        address = request.form['address']
        pin_code = request.form['pin_code']
        price = float(request.form['price'])
        max_spots = int(request.form['max_spots'])

        lot = ParkingLot(name=name, address=address, pin_code=pin_code,
                         price=price, max_spots=max_spots)
        db.session.add(lot)
        db.session.commit()

        # Auto-generate parking spots
        for _ in range(max_spots):
            spot = ParkingSpot(lot_id=lot.id, status='A')
            db.session.add(spot)
        db.session.commit()

        return redirect(url_for('admin_dashboard'))

    return render_template('add_lot.html')

@app.route('/admin/spot/<int:spot_id>/details')
def spot_details(spot_id):
    if session.get('role') not in ['admin', 'collaborator']:
        return redirect(url_for('login'))

    spot = ParkingSpot.query.get_or_404(spot_id)

    # Get latest reservation for this spot
    reservation = Reservation.query.filter_by(spot_id=spot.id).order_by(Reservation.parking_time.desc()).first()

    return render_template('admin_spot_details.html', spot=spot, reservation=reservation)

@app.route('/admin/lot/<int:lot_id>/spots')
def view_lot_spots(lot_id):
    if session.get('role') not in ['admin', 'collaborator']:
        return redirect(url_for('login'))

    lot = ParkingLot.query.get_or_404(lot_id)
    return render_template('admin_lot_spots.html', lot=lot)

@app.route('/admin/delete_spot/<int:spot_id>')
def delete_spot(spot_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    spot = ParkingSpot.query.get_or_404(spot_id)

    if spot.status == 'A':
        db.session.delete(spot)
        db.session.commit()

    return redirect(url_for('view_lot_spots', lot_id=spot.lot_id))


@app.route('/admin/delete_lot/<int:lot_id>')
def delete_lot(lot_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    lot = ParkingLot.query.get_or_404(lot_id)
    if all(spot.status == 'A' for spot in lot.spots):
        for spot in lot.spots:
            db.session.delete(spot)
        db.session.delete(lot)
        db.session.commit()
        flash('Parking lot deleted successfully.', 'success')
    else:
        flash('Cannot delete lot: One or more spots are still occupied.', 'danger')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/search')
def admin_search():
    if session.get('role') not in ['admin', 'collaborator']:
        return redirect(url_for('login'))

    query = request.args.get('query', '')
    results = []

    if query:
        results = ParkingLot.query.filter(
            (ParkingLot.name.ilike(f"%{query}%")) |
            (ParkingLot.pin_code.ilike(f"%{query}%"))
        ).all()

    return render_template('admin_search.html', lots=results, query=query)

@app.route('/admin/summary')
def admin_summary():
    if session.get('role') not in ['admin', 'collaborator']:
        return redirect(url_for('login'))

    lots = ParkingLot.query.all()

    # Chart 1: Revenue from each parking lot (assume cost is stored per reservation)
    labels = []
    revenues = []
    for lot in lots:
        lot_revenue = sum(
            res.cost or 0 for spot in lot.spots for res in spot.reservations
        )
        labels.append(lot.name)
        revenues.append(round(lot_revenue, 2))

    # Chart 2: Available vs. Occupied
    available_spots = sum(1 for lot in lots for spot in lot.spots if spot.status == 'A')
    occupied_spots = sum(1 for lot in lots for spot in lot.spots if spot.status == 'O')
    
    lot_data = []

    for lot in lots:
        ratings = []
        for spot in lot.spots:
            for res in spot.reservations:
                if res.rating is not None:
                    ratings.append(res.rating)
        avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None
        lot_data.append({
            'name': lot.name,
            'total_spots': lot.max_spots,
            'available_spots': sum(1 for s in lot.spots if s.status == 'A'),
            'avg_rating': avg_rating
        })

    return render_template(
        'admin_summary.html',
        labels=labels,
        revenues=revenues,
        available_spots=available_spots,
        occupied_spots=occupied_spots,
        lot_data=lot_data
    )

@app.route('/admin/feedback')
def admin_feedback():
    if session.get('role') not in ['admin', 'collaborator']:
        return redirect(url_for('login'))

    feedbacks = Reservation.query.filter(Reservation.rating != None).order_by(Reservation.parking_time.desc()).all()
    return render_template('admin_feedback.html', feedbacks=feedbacks)


@app.route('/user/dashboard')
def user_dashboard():
    if session.get('role') != 'user':
        return redirect(url_for('login'))
    
    user_id = session.get('user')
    if not isinstance(user_id, int):
        return redirect(url_for('login'))

    lots = ParkingLot.query.all()

    active_res = Reservation.query.filter_by(user_id=user_id, release_time=None).first()
    history = Reservation.query.filter(Reservation.user_id == user_id, Reservation.release_time != None).all()

    return render_template('user_dashboard.html', lots=lots, active_res=active_res, history=history)


@app.route('/user/reserve/<int:lot_id>', methods=['GET', 'POST'])
def reserve_spot(lot_id):
    if session.get('role') != 'user':
        return redirect(url_for('login'))
    
    user_id = session.get('user')
    if not isinstance(user_id, int):
        return redirect(url_for('login'))

    if request.method == 'POST':
        vehicle_number = request.form['vehicle_number']

        # Find first available spot
        spot = ParkingSpot.query.filter_by(lot_id=lot_id, status='A').first()
        if not spot:
            return "No available spots in this lot."

        # Prevent double reservation
        existing = Reservation.query.filter_by(user_id=user_id, release_time=None).first()
        if existing:
            return 'You already have an active reservation.'

        spot.status = 'O'
        reservation = Reservation(
            user_id=user_id,
            spot_id=spot.id,
            vehicle_number=vehicle_number,
            parking_time=datetime.now()
        )
        db.session.add(reservation)
        db.session.commit()

        return redirect(url_for('user_dashboard'))

    return render_template('user_reserve.html')


@app.route('/user/release/<int:reservation_id>')
def release_spot(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.release_time is not None:
        return "Spot already released."

    reservation.release_time = datetime.now()

    # Calculate cost
    lot_price = reservation.spot.lot.price
    duration_hours = (reservation.release_time - reservation.parking_time).total_seconds() / 3600
    reservation.cost = round(duration_hours * lot_price, 2)

    reservation.spot.status = 'A'
    db.session.commit()

    return redirect(url_for('user_dashboard'))

@app.route('/user/feedback')
def user_feedback():
    if session.get('role') != 'user':
        return redirect(url_for('login'))
    
    user_id = session.get('user')
    if not isinstance(user_id, int):
        return redirect(url_for('login'))

    reservations = (
        Reservation.query
        .filter_by(user_id=user_id)
        .filter(Reservation.release_time.isnot(None))
        .order_by(Reservation.parking_time.desc())
        .all()
    )
    return render_template('user_feedback.html', reservations=reservations)


@app.route('/user/rating/<int:reservation_id>', methods=['POST'])
def submit_rating(reservation_id):
    if session.get('role') != 'user':
        return redirect(url_for('login'))
    
    user_id = session.get('user')
    if not isinstance(user_id, int):
        return redirect(url_for('login'))

    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.user_id != user_id:
        return "Unauthorized", 403

    try:
        rating = float(request.form['rating'])
        if not (0.5 <= rating <= 5.0):
            return "Invalid rating", 400
    except ValueError:
        return "Invalid input", 400

    reservation.rating = rating
    db.session.commit()
    return redirect(url_for('user_feedback'))

@app.route('/user/summary')
def user_summary():
    if session.get('role') != 'user':
        return redirect(url_for('login'))
    
    user_id = session.get('user')
    if not isinstance(user_id, int):
        return redirect(url_for('login'))

    # Reservation count per lot
    lot_data = (
        db.session.query(ParkingLot.name, db.func.count(Reservation.id))
        .join(ParkingSpot, ParkingSpot.lot_id == ParkingLot.id)
        .join(Reservation, Reservation.spot_id == ParkingSpot.id)
        .filter(Reservation.user_id == user_id)
        .group_by(ParkingLot.name)
        .all()
    )
    lot_labels = [row[0] for row in lot_data]
    lot_counts = [row[1] for row in lot_data]

    # Average rating per lot
    rating_data = (
        db.session.query(ParkingLot.name, db.func.avg(Reservation.rating))
        .join(ParkingSpot, ParkingSpot.lot_id == ParkingLot.id)
        .join(Reservation, Reservation.spot_id == ParkingSpot.id)
        .filter(Reservation.user_id == user_id, Reservation.rating != None)
        .group_by(ParkingLot.name)
        .all()
    )
    rating_labels = [row[0] for row in rating_data]
    rating_values = [round(row[1], 2) for row in rating_data]

    return render_template(
        'user_summary.html',
        lot_labels=lot_labels,
        lot_counts=lot_counts,
        rating_labels=rating_labels,
        rating_values=rating_values
    )


@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('role', None)
    return redirect(url_for('login'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run()