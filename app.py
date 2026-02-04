from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from datetime import datetime, date
from config import Config
from models import db, Player, Session, Attendance, Payment

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# Create tables
with app.app_context():
    db.create_all()


# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# Admin-only decorator (allows both master admin and player admins)
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        if session.get('user_type') not in ['admin', 'player_admin']:
            flash('Admin access required', 'error')
            return redirect(url_for('player_profile'))
        return f(*args, **kwargs)
    return decorated_function


# Master admin only decorator (for sensitive operations like promoting admins)
def master_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        if session.get('user_type') not in ['admin', 'player_admin']:
            flash('Admin access required', 'error')
            return redirect(url_for('player_profile'))
        return f(*args, **kwargs)
    return decorated_function


# Auth routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_type = request.form.get('login_type', 'admin')

        if login_type == 'admin':
            password = request.form.get('password')
            if password == app.config['APP_PASSWORD']:
                session['authenticated'] = True
                session['user_type'] = 'admin'
                flash('Successfully logged in as admin!', 'success')
                return redirect(url_for('dashboard'))
            flash('Invalid password', 'error')
        else:
            # Player login
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('player_password')
            player = Player.query.filter(db.func.lower(Player.email) == email).first()
            if player and player.check_password(password):
                session['authenticated'] = True
                session['player_id'] = player.id
                if player.is_admin:
                    session['user_type'] = 'player_admin'
                    flash(f'Welcome back, {player.name}! (Admin)', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    session['user_type'] = 'player'
                    flash(f'Welcome back, {player.name}!', 'success')
                    return redirect(url_for('player_profile'))
            flash('Invalid email or password', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    session.pop('user_type', None)
    session.pop('player_id', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))


# Dashboard
@app.route('/')
@login_required
def dashboard():
    # Redirect non-admin players to their profile
    if session.get('user_type') == 'player':
        return redirect(url_for('player_profile'))
    # Admin and player_admin can access dashboard

    total_players = Player.query.count()
    upcoming_sessions = Session.query.filter(Session.date >= date.today()).count()

    # Calculate total outstanding balance
    players = Player.query.all()
    total_outstanding = sum(p.get_balance() for p in players)
    total_collected = sum(p.get_total_payments() for p in players)

    # Recent sessions
    recent_sessions = Session.query.order_by(Session.date.desc()).limit(5).all()

    # Recent payments
    recent_payments = Payment.query.order_by(Payment.date.desc()).limit(5).all()

    return render_template('dashboard.html',
                         total_players=total_players,
                         upcoming_sessions=upcoming_sessions,
                         total_outstanding=round(total_outstanding, 2),
                         total_collected=round(total_collected, 2),
                         recent_sessions=recent_sessions,
                         recent_payments=recent_payments)


# Player self-service profile
@app.route('/player/profile', methods=['GET', 'POST'])
@login_required
def player_profile():
    if session.get('user_type') != 'player':
        return redirect(url_for('dashboard'))

    player_id = session.get('player_id')
    player = Player.query.get_or_404(player_id)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_zelle':
            zelle_pref = request.form.get('zelle_preference')
            if zelle_pref in ['email', 'phone']:
                player.zelle_preference = zelle_pref
                db.session.commit()
                flash('Zelle preference updated!', 'success')

        elif action == 'change_password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            if not player.check_password(current_password):
                flash('Current password is incorrect', 'error')
            elif new_password != confirm_password:
                flash('New passwords do not match', 'error')
            elif len(new_password) < 4:
                flash('Password must be at least 4 characters', 'error')
            else:
                player.set_password(new_password)
                db.session.commit()
                flash('Password changed successfully!', 'success')

        return redirect(url_for('player_profile'))

    # Get attendance history
    attendances = player.attendances.join(Session).order_by(Session.date.desc()).all()
    payments = player.payments.order_by(Payment.date.desc()).all()

    return render_template('player_profile.html', player=player, attendances=attendances, payments=payments)


# Player sessions view - see all sessions and vote
@app.route('/player/sessions')
@login_required
def player_sessions():
    if session.get('user_type') != 'player':
        return redirect(url_for('sessions'))

    player_id = session.get('player_id')
    player = Player.query.get_or_404(player_id)

    # Get upcoming sessions
    upcoming_sessions = Session.query.filter(Session.date >= date.today()).order_by(Session.date.asc()).all()

    # Get completed sessions for current month
    today = date.today()
    first_of_month = today.replace(day=1)
    past_sessions = Session.query.filter(
        Session.date >= first_of_month,
        Session.date < today
    ).order_by(Session.date.desc()).all()

    # Get attendance map for this player
    attendance_map = {}
    for att in Attendance.query.filter_by(player_id=player_id).all():
        attendance_map[att.session_id] = att.status

    # Get all players for showing attendance
    all_players = Player.query.order_by(Player.name).all()

    # Get all attendance records for sessions we're displaying
    all_sessions = upcoming_sessions + past_sessions
    session_attendance = {}  # {session_id: {player_id: status}}
    for sess in all_sessions:
        session_attendance[sess.id] = {}
        for att in sess.attendances.all():
            session_attendance[sess.id][att.player_id] = att.status

    # Ensure current player has attendance records for all sessions
    for sess in all_sessions:
        if sess.id not in attendance_map:
            attendance = Attendance(player_id=player_id, session_id=sess.id, status='NO')
            db.session.add(attendance)
            attendance_map[sess.id] = 'NO'
            session_attendance[sess.id][player_id] = 'NO'
    db.session.commit()

    return render_template('player_sessions.html',
                         player=player,
                         upcoming_sessions=upcoming_sessions,
                         past_sessions=past_sessions,
                         attendance_map=attendance_map,
                         all_players=all_players,
                         session_attendance=session_attendance,
                         current_month=today.strftime('%B %Y'))


# Player attendance API - players can only update their own attendance
@app.route('/api/player/attendance', methods=['POST'])
@login_required
def update_player_attendance():
    if session.get('user_type') != 'player':
        return jsonify({'error': 'Player access only'}), 403

    player_id = session.get('player_id')
    data = request.get_json()
    session_id = data.get('session_id')
    status = data.get('status')

    if status not in ['YES', 'NO', 'TENTATIVE']:
        return jsonify({'error': 'Invalid status'}), 400

    attendance = Attendance.query.filter_by(player_id=player_id, session_id=session_id).first()

    if attendance:
        attendance.status = status
    else:
        attendance = Attendance(player_id=player_id, session_id=session_id, status=status)
        db.session.add(attendance)

    db.session.commit()

    # Return updated session info
    sess = Session.query.get(session_id)
    return jsonify({
        'success': True,
        'attendee_count': sess.get_attendee_count(),
        'cost_per_player': sess.get_cost_per_player()
    })


# Player routes
@app.route('/players')
@admin_required
def players():
    category = request.args.get('category', 'all')
    search_query = request.args.get('search', '').strip()

    # Start with base query
    query = Player.query

    # Apply category filter
    if category != 'all':
        query = query.filter_by(category=category)

    # Apply search filter
    if search_query:
        search_term = f'%{search_query}%'
        query = query.filter(
            db.or_(
                Player.name.ilike(search_term),
                Player.phone.ilike(search_term),
                Player.email.ilike(search_term)
            )
        )

    player_list = query.order_by(Player.name).all()
    return render_template('players.html', players=player_list, current_category=category, search_query=search_query)


@app.route('/players/add', methods=['GET', 'POST'])
@admin_required
def add_player():
    if request.method == 'POST':
        name = request.form.get('name')
        category = request.form.get('category', 'regular')
        phone = request.form.get('phone')
        email = request.form.get('email')
        password = request.form.get('password')
        zelle_preference = request.form.get('zelle_preference', 'email')

        if not name:
            flash('Name is required', 'error')
            return render_template('player_form.html', player=None)

        player = Player(name=name, category=category, phone=phone, email=email, zelle_preference=zelle_preference)
        if password:
            player.set_password(password)
        db.session.add(player)
        db.session.commit()
        flash(f'Player {name} added successfully!', 'success')
        return redirect(url_for('players'))

    return render_template('player_form.html', player=None)


@app.route('/players/<int:id>')
@admin_required
def player_detail(id):
    player = Player.query.get_or_404(id)
    attendances = player.attendances.join(Session).order_by(Session.date.desc()).all()
    payments = player.payments.order_by(Payment.date.desc()).all()
    return render_template('player_detail.html', player=player, attendances=attendances, payments=payments)


@app.route('/players/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_player(id):
    player = Player.query.get_or_404(id)

    if request.method == 'POST':
        player.name = request.form.get('name')
        player.category = request.form.get('category', 'regular')
        player.phone = request.form.get('phone')
        player.email = request.form.get('email')
        player.zelle_preference = request.form.get('zelle_preference', 'email')
        password = request.form.get('password')
        if password:
            player.set_password(password)
        db.session.commit()
        flash(f'Player {player.name} updated successfully!', 'success')
        return redirect(url_for('player_detail', id=id))

    return render_template('player_form.html', player=player)


@app.route('/players/<int:id>/delete', methods=['POST'])
@admin_required
def delete_player(id):
    player = Player.query.get_or_404(id)
    name = player.name
    db.session.delete(player)
    db.session.commit()
    flash(f'Player {name} deleted successfully!', 'success')
    return redirect(url_for('players'))


@app.route('/players/<int:id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_admin(id):
    player = Player.query.get_or_404(id)
    player.is_admin = not player.is_admin
    db.session.commit()
    status = 'promoted to admin' if player.is_admin else 'removed from admin'
    flash(f'{player.name} has been {status}!', 'success')
    return redirect(url_for('player_detail', id=id))


@app.route('/api/players/<int:id>/category', methods=['POST'])
@admin_required
def update_player_category(id):
    player = Player.query.get_or_404(id)
    data = request.get_json()
    category = data.get('category')

    if category not in ['regular', 'adhoc', 'kid']:
        return jsonify({'error': 'Invalid category'}), 400

    player.category = category
    db.session.commit()

    return jsonify({
        'success': True,
        'player_id': player.id,
        'category': player.category
    })


# Session routes
@app.route('/sessions')
@admin_required
def sessions():
    session_list = Session.query.order_by(Session.date.desc()).all()
    return render_template('sessions.html', sessions=session_list)


@app.route('/sessions/add', methods=['GET', 'POST'])
@admin_required
def add_session():
    if request.method == 'POST':
        date_str = request.form.get('date')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        courts = int(request.form.get('courts', 1))
        court_cost = float(request.form.get('court_cost', 0))
        birdie_cost = float(request.form.get('birdie_cost', 0))
        notes = request.form.get('notes')

        session_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        new_session = Session(
            date=session_date,
            start_time=start_time,
            end_time=end_time,
            courts=courts,
            court_cost=court_cost,
            birdie_cost=birdie_cost,
            notes=notes
        )
        db.session.add(new_session)
        db.session.commit()

        # Create attendance records for all players (default NO)
        players = Player.query.all()
        for player in players:
            attendance = Attendance(player_id=player.id, session_id=new_session.id, status='NO')
            db.session.add(attendance)
        db.session.commit()

        flash('Session created successfully!', 'success')
        return redirect(url_for('session_detail', id=new_session.id))

    return render_template('session_form.html', session=None)


@app.route('/sessions/<int:id>')
@admin_required
def session_detail(id):
    sess = Session.query.get_or_404(id)
    players = Player.query.order_by(Player.name).all()

    # Get attendance for all players
    attendance_map = {}
    for att in sess.attendances.all():
        attendance_map[att.player_id] = att.status

    # Ensure all players have attendance records
    for player in players:
        if player.id not in attendance_map:
            attendance = Attendance(player_id=player.id, session_id=id, status='NO')
            db.session.add(attendance)
            attendance_map[player.id] = 'NO'
    db.session.commit()

    return render_template('session_detail.html', session=sess, players=players, attendance_map=attendance_map)


@app.route('/sessions/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_session(id):
    sess = Session.query.get_or_404(id)

    if request.method == 'POST':
        sess.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        sess.start_time = request.form.get('start_time')
        sess.end_time = request.form.get('end_time')
        sess.courts = int(request.form.get('courts', 1))
        sess.court_cost = float(request.form.get('court_cost', 0))
        sess.birdie_cost = float(request.form.get('birdie_cost', 0))
        sess.notes = request.form.get('notes')
        db.session.commit()
        flash('Session updated successfully!', 'success')
        return redirect(url_for('session_detail', id=id))

    return render_template('session_form.html', session=sess)


@app.route('/sessions/<int:id>/delete', methods=['POST'])
@admin_required
def delete_session(id):
    sess = Session.query.get_or_404(id)
    db.session.delete(sess)
    db.session.commit()
    flash('Session deleted successfully!', 'success')
    return redirect(url_for('sessions'))


# Attendance API
@app.route('/api/attendance', methods=['POST'])
@admin_required
def update_attendance():
    data = request.get_json()
    player_id = data.get('player_id')
    session_id = data.get('session_id')
    status = data.get('status')

    if status not in ['YES', 'NO', 'TENTATIVE']:
        return jsonify({'error': 'Invalid status'}), 400

    attendance = Attendance.query.filter_by(player_id=player_id, session_id=session_id).first()

    if attendance:
        attendance.status = status
    else:
        attendance = Attendance(player_id=player_id, session_id=session_id, status=status)
        db.session.add(attendance)

    db.session.commit()

    # Return updated session costs
    sess = Session.query.get(session_id)
    return jsonify({
        'success': True,
        'attendee_count': sess.get_attendee_count(),
        'cost_per_player': sess.get_cost_per_player()
    })


# Payment routes
@app.route('/payments')
@admin_required
def payments():
    payment_list = Payment.query.order_by(Payment.date.desc()).all()

    # Calculate totals
    total_collected = sum(p.amount for p in payment_list)

    # Outstanding balances
    players = Player.query.all()
    balances = [(p, p.get_balance()) for p in players if p.get_balance() > 0]
    balances.sort(key=lambda x: x[1], reverse=True)

    return render_template('payments.html',
                         payments=payment_list,
                         total_collected=round(total_collected, 2),
                         outstanding_balances=balances)


@app.route('/payments/add', methods=['GET', 'POST'])
@admin_required
def add_payment():
    if request.method == 'POST':
        player_id = int(request.form.get('player_id'))
        amount = float(request.form.get('amount'))
        method = request.form.get('method')
        date_str = request.form.get('date')
        notes = request.form.get('notes')

        payment_date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()

        payment = Payment(
            player_id=player_id,
            amount=amount,
            method=method,
            date=payment_date,
            notes=notes
        )
        db.session.add(payment)
        db.session.commit()

        player = Player.query.get(player_id)
        flash(f'Payment of ${amount:.2f} from {player.name} recorded!', 'success')
        return redirect(url_for('payments'))

    players = Player.query.order_by(Player.name).all()
    return render_template('payment_form.html', players=players, payment=None, today=date.today().isoformat())


@app.route('/payments/<int:id>/delete', methods=['POST'])
@admin_required
def delete_payment(id):
    payment = Payment.query.get_or_404(id)
    db.session.delete(payment)
    db.session.commit()
    flash('Payment deleted successfully!', 'success')
    return redirect(url_for('payments'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
