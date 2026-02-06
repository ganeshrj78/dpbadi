from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from datetime import datetime, date
from werkzeug.utils import secure_filename
import os
import uuid
from config import Config
from models import db, Player, Session, Court, Attendance, Payment

app = Flask(__name__)
app.config.from_object(Config)

# File upload configuration
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_profile_photo(file):
    """Save uploaded profile photo and return filename"""
    if file and allowed_file(file.filename):
        # Generate unique filename
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return filename
    return None

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
                if not player.is_active:
                    flash('Your account has been deactivated. Please contact an admin.', 'error')
                    return render_template('login.html')
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

        elif action == 'update_photo':
            if 'profile_photo' in request.files:
                file = request.files['profile_photo']
                if file and file.filename:
                    # Delete old photo if exists
                    if player.profile_photo:
                        old_path = os.path.join(app.config['UPLOAD_FOLDER'], player.profile_photo)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    filename = save_profile_photo(file)
                    if filename:
                        player.profile_photo = filename
                        db.session.commit()
                        flash('Profile photo updated!', 'success')
                    else:
                        flash('Invalid file type. Please upload an image (PNG, JPG, GIF, WEBP).', 'error')

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

    # Get managed players (spouse, kids, etc.)
    managed_players = player.managed_players

    # Get upcoming sessions (not archived, future dates)
    upcoming_sessions = Session.query.filter(
        Session.date >= date.today(),
        Session.is_archived == False
    ).order_by(Session.date.asc()).all()

    # Get completed sessions (archived sessions) grouped by year-month
    archived_sessions = Session.query.filter_by(is_archived=True).order_by(Session.date.desc()).all()

    # Group archived by year-month
    archived_grouped = {}
    for sess in archived_sessions:
        key = sess.date.strftime('%Y-%m')
        label = sess.date.strftime('%B %Y')
        if key not in archived_grouped:
            archived_grouped[key] = {'label': label, 'sessions': []}
        archived_grouped[key]['sessions'].append(sess)

    # Sort by key (year-month) descending
    archived_sorted = sorted(archived_grouped.items(), key=lambda x: x[0], reverse=True)

    # Get attendance map for this player and managed players
    attendance_map = {}  # {player_id: {session_id: status}}
    players_to_track = [player] + list(managed_players)
    for p in players_to_track:
        attendance_map[p.id] = {}
        for att in Attendance.query.filter_by(player_id=p.id).all():
            attendance_map[p.id][att.session_id] = att.status

    # Get all players for showing attendance
    all_players = Player.query.order_by(Player.name).all()

    # Get all attendance records for sessions we're displaying
    all_sessions = upcoming_sessions + archived_sessions
    session_attendance = {}  # {session_id: {player_id: status}}
    for sess in all_sessions:
        session_attendance[sess.id] = {}
        for att in sess.attendances.all():
            session_attendance[sess.id][att.player_id] = att.status

    # Ensure current player and managed players have attendance records for upcoming sessions
    for sess in upcoming_sessions:
        for p in players_to_track:
            if sess.id not in attendance_map[p.id]:
                attendance = Attendance(player_id=p.id, session_id=sess.id, status='NO')
                db.session.add(attendance)
                attendance_map[p.id][sess.id] = 'NO'
                session_attendance[sess.id][p.id] = 'NO'
    db.session.commit()

    return render_template('player_sessions.html',
                         player=player,
                         managed_players=managed_players,
                         upcoming_sessions=upcoming_sessions,
                         archived_groups=archived_sorted,
                         attendance_map=attendance_map,
                         all_players=all_players,
                         session_attendance=session_attendance)


# Player payment - players can record their own and managed players' payments
@app.route('/player/payments', methods=['GET', 'POST'])
@login_required
def player_payments():
    if session.get('user_type') != 'player':
        return redirect(url_for('payments'))

    player_id = session.get('player_id')
    player = Player.query.get_or_404(player_id)
    managed_players = player.managed_players

    if request.method == 'POST':
        target_player_id = int(request.form.get('player_id', player_id))
        amount = float(request.form.get('amount'))
        method = request.form.get('method')
        date_str = request.form.get('date')
        notes = request.form.get('notes')

        # Verify target is self or managed player
        managed_player_ids = [p.id for p in managed_players]
        if target_player_id != player_id and target_player_id not in managed_player_ids:
            flash('You can only record payments for yourself or managed players', 'error')
            return redirect(url_for('player_payments'))

        payment_date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()

        payment = Payment(
            player_id=target_player_id,
            amount=amount,
            method=method,
            date=payment_date,
            notes=notes
        )
        db.session.add(payment)
        db.session.commit()

        target_player = Player.query.get(target_player_id)
        flash(f'Payment of ${amount:.2f} for {target_player.name} recorded successfully!', 'success')
        return redirect(url_for('player_payments'))

    # Get payments for player and managed players
    all_player_ids = [player_id] + [p.id for p in managed_players]
    all_payments = Payment.query.filter(Payment.player_id.in_(all_player_ids)).order_by(Payment.date.desc()).all()

    return render_template('player_payments.html',
                         player=player,
                         managed_players=managed_players,
                         payments=all_payments,
                         today=date.today().isoformat())


# Player attendance API - players can update their own and managed players' attendance
@app.route('/api/player/attendance', methods=['POST'])
@login_required
def update_player_attendance():
    if session.get('user_type') != 'player':
        return jsonify({'error': 'Player access only'}), 403

    current_player_id = session.get('player_id')
    current_player = Player.query.get(current_player_id)
    data = request.get_json()
    session_id = data.get('session_id')
    status = data.get('status')
    target_player_id = data.get('player_id', current_player_id)  # Default to self

    # Players can only use YES, NO, TENTATIVE (DROPOUT and FILLIN are admin-only)
    if status not in ['YES', 'NO', 'TENTATIVE']:
        return jsonify({'error': 'Invalid status'}), 400

    # Check if target player is self or a managed player
    managed_player_ids = [p.id for p in current_player.managed_players]
    if target_player_id != current_player_id and target_player_id not in managed_player_ids:
        return jsonify({'error': 'You can only vote for yourself or your managed players'}), 403

    attendance = Attendance.query.filter_by(player_id=target_player_id, session_id=session_id).first()

    if attendance:
        attendance.status = status
    else:
        attendance = Attendance(player_id=target_player_id, session_id=session_id, status=status)
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

        # Handle managed_by
        managed_by = request.form.get('managed_by')
        if managed_by:
            player.managed_by = int(managed_by)

        # Handle profile photo upload
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and file.filename:
                filename = save_profile_photo(file)
                if filename:
                    player.profile_photo = filename

        db.session.add(player)
        db.session.commit()
        flash(f'Player {name} added successfully!', 'success')
        return redirect(url_for('players'))

    all_players = Player.query.order_by(Player.name).all()
    return render_template('player_form.html', player=None, all_players=all_players)


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

        # Handle managed_by
        managed_by = request.form.get('managed_by')
        player.managed_by = int(managed_by) if managed_by else None

        # Handle profile photo upload
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and file.filename:
                # Delete old photo if exists
                if player.profile_photo:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], player.profile_photo)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = save_profile_photo(file)
                if filename:
                    player.profile_photo = filename

        db.session.commit()
        flash(f'Player {player.name} updated successfully!', 'success')
        return redirect(url_for('player_detail', id=id))

    all_players = Player.query.order_by(Player.name).all()
    return render_template('player_form.html', player=player, all_players=all_players)


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


@app.route('/players/<int:id>/toggle-active', methods=['POST'])
@admin_required
def toggle_active(id):
    player = Player.query.get_or_404(id)
    player.is_active = not player.is_active
    db.session.commit()
    status = 'activated' if player.is_active else 'deactivated'
    flash(f'{player.name} has been {status}!', 'success')
    return redirect(url_for('player_detail', id=id))


# Session routes
@app.route('/sessions')
@admin_required
def sessions():
    # Active sessions (not archived)
    active_sessions = Session.query.filter_by(is_archived=False).order_by(Session.date.desc()).all()

    # Archived sessions grouped by year and month
    archived_sessions = Session.query.filter_by(is_archived=True).order_by(Session.date.desc()).all()

    # Group archived by year-month
    archived_grouped = {}
    for sess in archived_sessions:
        key = sess.date.strftime('%Y-%m')
        label = sess.date.strftime('%B %Y')
        if key not in archived_grouped:
            archived_grouped[key] = {'label': label, 'sessions': []}
        archived_grouped[key]['sessions'].append(sess)

    # Sort by key (year-month) descending
    archived_sorted = sorted(archived_grouped.items(), key=lambda x: x[0], reverse=True)

    return render_template('sessions.html',
                          active_sessions=active_sessions,
                          archived_groups=archived_sorted)


@app.route('/sessions/add', methods=['GET', 'POST'])
@admin_required
def add_session():
    if request.method == 'POST':
        date_str = request.form.get('date')
        birdie_cost = float(request.form.get('birdie_cost', 0))
        notes = request.form.get('notes')
        court_count = int(request.form.get('court_count', 1))

        session_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        new_session = Session(
            date=session_date,
            birdie_cost=birdie_cost,
            notes=notes
        )
        db.session.add(new_session)
        db.session.flush()  # Get the session ID

        # Add courts
        for i in range(court_count):
            court_name = request.form.get(f'court_name_{i}', f'Court {i+1}')
            court_start = request.form.get(f'court_start_{i}', '6:30 AM')
            court_end = request.form.get(f'court_end_{i}', '9:30 AM')
            court_cost = float(request.form.get(f'court_cost_{i}', 30))

            court = Court(
                session_id=new_session.id,
                name=court_name,
                start_time=court_start,
                end_time=court_end,
                cost=court_cost
            )
            db.session.add(court)

        # Create attendance records for all players (default NO, category from player)
        players = Player.query.all()
        for player in players:
            attendance = Attendance(player_id=player.id, session_id=new_session.id, status='NO', category=player.category)
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
    category_map = {}
    for att in sess.attendances.all():
        attendance_map[att.player_id] = att.status
        category_map[att.player_id] = att.category

    # Ensure all players have attendance records
    for player in players:
        if player.id not in attendance_map:
            attendance = Attendance(player_id=player.id, session_id=id, status='NO', category=player.category)
            db.session.add(attendance)
            attendance_map[player.id] = 'NO'
            category_map[player.id] = player.category
    db.session.commit()

    return render_template('session_detail.html', session=sess, players=players, attendance_map=attendance_map, category_map=category_map)


@app.route('/sessions/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_session(id):
    sess = Session.query.get_or_404(id)

    if request.method == 'POST':
        sess.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        sess.birdie_cost = float(request.form.get('birdie_cost', 0))
        sess.notes = request.form.get('notes')
        court_count = int(request.form.get('court_count', 1))

        # Delete existing courts and recreate
        Court.query.filter_by(session_id=id).delete()

        # Add courts
        for i in range(court_count):
            court_name = request.form.get(f'court_name_{i}', f'Court {i+1}')
            court_start = request.form.get(f'court_start_{i}', '6:30 AM')
            court_end = request.form.get(f'court_end_{i}', '9:30 AM')
            court_cost = float(request.form.get(f'court_cost_{i}', 30))

            court = Court(
                session_id=id,
                name=court_name,
                start_time=court_start,
                end_time=court_end,
                cost=court_cost
            )
            db.session.add(court)

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


@app.route('/sessions/<int:id>/toggle-archive', methods=['POST'])
@admin_required
def toggle_archive(id):
    sess = Session.query.get_or_404(id)
    sess.is_archived = not sess.is_archived
    db.session.commit()
    status = 'archived' if sess.is_archived else 'unarchived'
    flash(f'Session {status} successfully!', 'success')
    return redirect(url_for('session_detail', id=id))


# Attendance API
@app.route('/api/attendance', methods=['POST'])
@admin_required
def update_attendance():
    data = request.get_json()
    player_id = data.get('player_id')
    session_id = data.get('session_id')
    status = data.get('status')

    if status not in ['YES', 'NO', 'TENTATIVE', 'DROPOUT', 'FILLIN']:
        return jsonify({'error': 'Invalid status'}), 400

    attendance = Attendance.query.filter_by(player_id=player_id, session_id=session_id).first()

    if attendance:
        attendance.status = status
    else:
        player = Player.query.get(player_id)
        attendance = Attendance(player_id=player_id, session_id=session_id, status=status, category=player.category if player else 'regular')
        db.session.add(attendance)

    db.session.commit()

    # Return updated session costs
    sess = Session.query.get(session_id)
    return jsonify({
        'success': True,
        'attendee_count': sess.get_attendee_count(),
        'cost_per_player': sess.get_cost_per_player()
    })


# Attendance category API - update player category for a specific session
@app.route('/api/attendance/category', methods=['POST'])
@admin_required
def update_attendance_category():
    data = request.get_json()
    player_id = data.get('player_id')
    session_id = data.get('session_id')
    category = data.get('category')

    if category not in ['regular', 'adhoc', 'kid']:
        return jsonify({'error': 'Invalid category'}), 400

    attendance = Attendance.query.filter_by(player_id=player_id, session_id=session_id).first()

    if attendance:
        attendance.category = category
    else:
        attendance = Attendance(player_id=player_id, session_id=session_id, status='NO', category=category)
        db.session.add(attendance)

    db.session.commit()

    return jsonify({
        'success': True,
        'player_id': player_id,
        'session_id': session_id,
        'category': category
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
