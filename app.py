from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from datetime import datetime, date
from werkzeug.utils import secure_filename
import os
import uuid
import logging
from logging.handlers import RotatingFileHandler
from config import Config
from models import db, Player, Session, Court, Attendance, Payment, BirdieBank, DropoutRefund
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.config.from_object(Config)

# CSRF Protection
csrf = CSRFProtect(app)

# Rate Limiting
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Logging Configuration
if not os.path.exists('logs'):
    os.makedirs('logs')

# Security audit log
security_handler = RotatingFileHandler('logs/security.log', maxBytes=10240000, backupCount=10)
security_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
security_handler.setLevel(logging.INFO)

security_logger = logging.getLogger('security')
security_logger.setLevel(logging.INFO)
security_logger.addHandler(security_handler)

# Application log
app_handler = RotatingFileHandler('logs/app.log', maxBytes=10240000, backupCount=10)
app_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
app_handler.setLevel(logging.INFO)
app.logger.addHandler(app_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('BP Badminton startup')

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
@limiter.limit("10 per minute")  # Rate limit: 10 login attempts per minute
def login():
    if request.method == 'POST':
        login_type = request.form.get('login_type', 'admin')
        client_ip = request.remote_addr

        if login_type == 'admin':
            password = request.form.get('password')
            if password == app.config['APP_PASSWORD']:
                session['authenticated'] = True
                session['user_type'] = 'admin'
                security_logger.info(f'ADMIN_LOGIN_SUCCESS - IP: {client_ip}')
                flash('Successfully logged in as admin!', 'success')
                return redirect(url_for('dashboard'))
            security_logger.warning(f'ADMIN_LOGIN_FAILED - IP: {client_ip}')
            flash('Invalid password', 'error')
        else:
            # Player login
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('player_password')
            player = Player.query.filter(db.func.lower(Player.email) == email).first()
            if player and player.check_password(password):
                if not player.is_approved:
                    security_logger.info(f'LOGIN_PENDING_APPROVAL - Email: {email}, IP: {client_ip}')
                    flash('Your registration is pending approval. Please wait for admin approval.', 'error')
                    return render_template('login.html')
                if not player.is_active:
                    security_logger.warning(f'LOGIN_INACTIVE_ACCOUNT - Email: {email}, IP: {client_ip}')
                    flash('Your account has been deactivated. Please contact an admin.', 'error')
                    return render_template('login.html')
                session['authenticated'] = True
                session['player_id'] = player.id
                if player.is_admin:
                    session['user_type'] = 'player_admin'
                    security_logger.info(f'PLAYER_ADMIN_LOGIN_SUCCESS - Player: {player.name} (ID: {player.id}), IP: {client_ip}')
                    flash(f'Welcome back, {player.name}! (Admin)', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    session['user_type'] = 'player'
                    security_logger.info(f'PLAYER_LOGIN_SUCCESS - Player: {player.name} (ID: {player.id}), IP: {client_ip}')
                    flash(f'Welcome back, {player.name}!', 'success')
                    return redirect(url_for('player_profile'))
            security_logger.warning(f'PLAYER_LOGIN_FAILED - Email: {email}, IP: {client_ip}')
            flash('Invalid email or password', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    session.pop('user_type', None)
    session.pop('player_id', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour")  # Rate limit: 5 registrations per hour per IP
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        client_ip = request.remote_addr

        # Validation
        if not name or not email or not password:
            flash('Name, email, and password are required', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html')

        if len(password) < 4:
            flash('Password must be at least 4 characters', 'error')
            return render_template('register.html')

        # Check if email already exists
        existing_player = Player.query.filter(db.func.lower(Player.email) == email).first()
        if existing_player:
            security_logger.warning(f'REGISTRATION_DUPLICATE_EMAIL - Email: {email}, IP: {client_ip}')
            flash('An account with this email already exists', 'error')
            return render_template('register.html')

        # Create new player (pending approval)
        player = Player(
            name=name,
            email=email,
            phone=phone,
            category='regular',
            is_approved=False,
            is_active=True
        )
        player.set_password(password)

        db.session.add(player)
        db.session.commit()

        security_logger.info(f'REGISTRATION_SUCCESS - Name: {name}, Email: {email}, IP: {client_ip}')
        flash('Registration successful! Please wait for admin approval.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


# Dashboard
@app.route('/')
@login_required
def dashboard():
    # Redirect non-admin players to their profile
    if session.get('user_type') == 'player':
        return redirect(url_for('player_profile'))
    # Admin and player_admin can access dashboard

    total_players = Player.query.filter_by(is_approved=True).count()
    upcoming_sessions = Session.query.filter(Session.date >= date.today()).count()

    # Calculate total outstanding balance
    players = Player.query.filter_by(is_approved=True).all()
    total_outstanding = sum(p.get_balance() for p in players)
    total_collected = sum(p.get_total_payments() for p in players)

    # Pending approvals
    pending_approvals = Player.query.filter_by(is_approved=False).order_by(Player.created_at.desc()).all()

    # Recent sessions
    recent_sessions = Session.query.order_by(Session.date.desc()).limit(5).all()

    # Recent payments
    recent_payments = Payment.query.order_by(Payment.date.desc()).limit(5).all()

    return render_template('dashboard.html',
                         total_players=total_players,
                         upcoming_sessions=upcoming_sessions,
                         total_outstanding=round(total_outstanding, 2),
                         total_collected=round(total_collected, 2),
                         pending_approvals=pending_approvals,
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

        if action == 'update_profile':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            phone = request.form.get('phone', '').strip()

            if not name:
                flash('Name is required', 'error')
            else:
                # Check if email is taken by another player
                if email:
                    existing = Player.query.filter(
                        db.func.lower(Player.email) == email,
                        Player.id != player.id
                    ).first()
                    if existing:
                        flash('This email is already in use by another player', 'error')
                        return redirect(url_for('player_profile'))

                player.name = name
                player.email = email if email else None
                player.phone = phone if phone else None
                db.session.commit()
                flash('Profile updated successfully!', 'success')

        elif action == 'update_zelle':
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

    # Get active sessions (not archived) - includes past sessions until archived
    upcoming_sessions = Session.query.filter(
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
@csrf.exempt  # API endpoint uses JSON
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

    # Check if voting is frozen for this session
    sess = Session.query.get(session_id)
    if sess and sess.voting_frozen:
        return jsonify({'error': 'Voting is frozen for this session'}), 403

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
        gender = request.form.get('gender', 'male')
        dob_str = request.form.get('date_of_birth')

        if not name:
            flash('Name is required', 'error')
            return render_template('player_form.html', player=None)

        player = Player(name=name, category=category, phone=phone, email=email, zelle_preference=zelle_preference, gender=gender, is_approved=True)

        # Handle date of birth
        if dob_str:
            player.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date()

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
        player.gender = request.form.get('gender', 'male')
        dob_str = request.form.get('date_of_birth')
        player.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None

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
@csrf.exempt  # API endpoint uses JSON
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


@app.route('/players/<int:id>/approve', methods=['POST'])
@admin_required
def approve_player(id):
    player = Player.query.get_or_404(id)
    player.is_approved = True
    db.session.commit()
    admin_info = f"Admin" if session.get('user_type') == 'admin' else f"Player Admin (ID: {session.get('player_id')})"
    security_logger.info(f'PLAYER_APPROVED - Player: {player.name} (ID: {player.id}), By: {admin_info}, IP: {request.remote_addr}')
    flash(f'{player.name} has been approved!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/players/<int:id>/reject', methods=['POST'])
@admin_required
def reject_player(id):
    player = Player.query.get_or_404(id)
    name = player.name
    email = player.email
    admin_info = f"Admin" if session.get('user_type') == 'admin' else f"Player Admin (ID: {session.get('player_id')})"
    security_logger.info(f'PLAYER_REJECTED - Player: {name}, Email: {email}, By: {admin_info}, IP: {request.remote_addr}')
    db.session.delete(player)
    db.session.commit()
    flash(f'Registration for {name} has been rejected and removed.', 'success')
    return redirect(url_for('dashboard'))


# Session routes
@app.route('/sessions')
@admin_required
def sessions():
    # Active sessions (not archived) - sorted by date ascending (earliest first)
    active_sessions = Session.query.filter_by(is_archived=False).order_by(Session.date.asc()).all()

    # All sessions grouped by year and month for summary
    all_sessions = Session.query.order_by(Session.date.desc()).all()

    # Group all sessions by year-month for monthly summary
    monthly_summary = {}
    for sess in all_sessions:
        key = sess.date.strftime('%Y-%m')
        label = sess.date.strftime('%B %Y')
        if key not in monthly_summary:
            monthly_summary[key] = {
                'label': label,
                'sessions': [],
                'total_sessions': 0,
                'archived_sessions': 0,
                'birdie_charges': 0,
                'regular_charges': 0,
                'adhoc_charges': 0,
                'kid_charges': 0,
                'total_refunds': 0,
                'total_collection': 0
            }
        monthly_summary[key]['sessions'].append(sess)
        monthly_summary[key]['total_sessions'] += 1
        if sess.is_archived:
            monthly_summary[key]['archived_sessions'] += 1
        monthly_summary[key]['birdie_charges'] += sess.get_birdie_cost_total()
        monthly_summary[key]['regular_charges'] += sess.get_regular_player_charges()
        monthly_summary[key]['adhoc_charges'] += sess.get_adhoc_player_charges()
        monthly_summary[key]['kid_charges'] += sess.get_kid_player_charges()
        monthly_summary[key]['total_refunds'] += sess.get_total_refunds()
        monthly_summary[key]['total_collection'] += sess.get_total_collection()

    # Calculate if month is fully archived
    for key in monthly_summary:
        monthly_summary[key]['is_fully_archived'] = (
            monthly_summary[key]['total_sessions'] == monthly_summary[key]['archived_sessions']
        )

    # Sort by key (year-month) descending
    monthly_sorted = sorted(monthly_summary.items(), key=lambda x: x[0], reverse=True)

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

    # Get all active players grouped by category for the attendance matrix
    regular_players = Player.query.filter_by(is_active=True, category='regular').order_by(Player.name).all()
    adhoc_players = Player.query.filter_by(is_active=True, category='adhoc').order_by(Player.name).all()
    kid_players = Player.query.filter_by(is_active=True, category='kid').order_by(Player.name).all()

    # Build attendance map: {session_id: {player_id: status}}
    attendance_map = {}
    for sess in active_sessions:
        attendance_map[sess.id] = {}
        for att in sess.attendances.all():
            attendance_map[sess.id][att.player_id] = att.status

    return render_template('sessions.html',
                          active_sessions=active_sessions,
                          archived_groups=archived_sorted,
                          monthly_summary=monthly_sorted,
                          regular_players=regular_players,
                          adhoc_players=adhoc_players,
                          kid_players=kid_players,
                          attendance_map=attendance_map)


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
            court_type = request.form.get(f'court_type_{i}', 'regular')
            court_start = request.form.get(f'court_start_{i}', '6:30 AM')
            court_end = request.form.get(f'court_end_{i}', '9:30 AM')
            court_cost = float(request.form.get(f'court_cost_{i}', 30))

            court = Court(
                session_id=new_session.id,
                name=court_name,
                court_type=court_type,
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
            court_type = request.form.get(f'court_type_{i}', 'regular')
            court_start = request.form.get(f'court_start_{i}', '6:30 AM')
            court_end = request.form.get(f'court_end_{i}', '9:30 AM')
            court_cost = float(request.form.get(f'court_cost_{i}', 30))

            court = Court(
                session_id=id,
                name=court_name,
                court_type=court_type,
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


@app.route('/sessions/<int:id>/toggle-voting-freeze', methods=['POST'])
@admin_required
def toggle_voting_freeze(id):
    sess = Session.query.get_or_404(id)
    sess.voting_frozen = not sess.voting_frozen
    db.session.commit()
    status = 'frozen' if sess.voting_frozen else 'unfrozen'
    flash(f'Voting {status} for this session!', 'success')
    return redirect(url_for('session_detail', id=id))


@app.route('/sessions/bulk-archive', methods=['POST'])
@admin_required
def bulk_archive_sessions():
    session_ids = request.form.getlist('session_ids')
    if not session_ids:
        flash('No sessions selected', 'error')
        return redirect(url_for('sessions'))

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        if sess and not sess.is_archived:
            sess.is_archived = True
            count += 1

    db.session.commit()
    flash(f'{count} session(s) archived successfully!', 'success')
    return redirect(url_for('sessions'))


@app.route('/sessions/bulk-unarchive', methods=['POST'])
@admin_required
def bulk_unarchive_sessions():
    session_ids = request.form.getlist('session_ids')
    if not session_ids:
        flash('No sessions selected', 'error')
        return redirect(url_for('sessions'))

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        if sess and sess.is_archived:
            sess.is_archived = False
            count += 1

    db.session.commit()
    flash(f'{count} session(s) unarchived successfully!', 'success')
    return redirect(url_for('sessions'))


@app.route('/sessions/bulk-freeze-voting', methods=['POST'])
@admin_required
def bulk_freeze_voting():
    session_ids = request.form.getlist('session_ids')
    if not session_ids:
        flash('No sessions selected', 'error')
        return redirect(url_for('sessions'))

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        if sess and not sess.voting_frozen:
            sess.voting_frozen = True
            count += 1

    db.session.commit()
    flash(f'Voting frozen for {count} session(s)!', 'success')
    return redirect(url_for('sessions'))


@app.route('/sessions/bulk-unfreeze-voting', methods=['POST'])
@admin_required
def bulk_unfreeze_voting():
    session_ids = request.form.getlist('session_ids')
    if not session_ids:
        flash('No sessions selected', 'error')
        return redirect(url_for('sessions'))

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        if sess and sess.voting_frozen:
            sess.voting_frozen = False
            count += 1

    db.session.commit()
    flash(f'Voting unfrozen for {count} session(s)!', 'success')
    return redirect(url_for('sessions'))


@app.route('/api/bulk-attendance', methods=['POST'])
@admin_required
def bulk_attendance():
    """Bulk update attendance for selected sessions"""
    data = request.get_json()
    session_ids = data.get('session_ids', [])
    category = data.get('category', 'all')  # 'regular', 'adhoc', 'kid', or 'all'
    status = data.get('status', 'YES')  # 'YES', 'NO', 'TENTATIVE', or 'CLEAR'

    if not session_ids:
        return jsonify({'success': False, 'error': 'No sessions selected'})

    # Get players based on category
    if category == 'regular':
        players = Player.query.filter_by(is_active=True, category='regular').all()
    elif category == 'adhoc':
        players = Player.query.filter_by(is_active=True, category='adhoc').all()
    elif category == 'kid':
        players = Player.query.filter_by(is_active=True, category='kid').all()
    else:
        players = Player.query.filter_by(is_active=True).all()

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        if not sess:
            continue

        for player in players:
            # Find existing attendance or create new
            attendance = Attendance.query.filter_by(session_id=session_id, player_id=player.id).first()

            if status == 'CLEAR':
                if attendance:
                    db.session.delete(attendance)
                    count += 1
            else:
                if attendance:
                    attendance.status = status
                    attendance.category = player.category
                else:
                    attendance = Attendance(
                        session_id=session_id,
                        player_id=player.id,
                        status=status,
                        category=player.category
                    )
                    db.session.add(attendance)
                count += 1

    db.session.commit()
    return jsonify({'success': True, 'count': count})


@app.route('/api/bulk-player-attendance', methods=['POST'])
@admin_required
def bulk_player_attendance():
    """Bulk update attendance for a single player across multiple sessions"""
    data = request.get_json()
    player_id = data.get('player_id')
    session_ids = data.get('session_ids', [])
    status = data.get('status', 'YES')

    if not player_id:
        return jsonify({'success': False, 'error': 'No player specified'})

    if not session_ids:
        return jsonify({'success': False, 'error': 'No sessions specified'})

    player = Player.query.get(player_id)
    if not player:
        return jsonify({'success': False, 'error': 'Player not found'})

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        if not sess:
            continue

        attendance = Attendance.query.filter_by(session_id=session_id, player_id=player_id).first()

        if status == 'CLEAR':
            if attendance:
                db.session.delete(attendance)
                count += 1
        else:
            if attendance:
                attendance.status = status
                attendance.category = player.category
            else:
                attendance = Attendance(
                    session_id=session_id,
                    player_id=player_id,
                    status=status,
                    category=player.category
                )
                db.session.add(attendance)
            count += 1

    db.session.commit()
    return jsonify({'success': True, 'count': count})


# Dropout Refund routes
@app.route('/sessions/<int:id>/refunds')
@admin_required
def session_refunds(id):
    sess = Session.query.get_or_404(id)

    # Get all dropouts for this session
    dropouts = Attendance.query.filter_by(session_id=id, status='DROPOUT').all()
    fillins = Attendance.query.filter_by(session_id=id, status='FILLIN').all()

    # Get existing refunds
    refunds = DropoutRefund.query.filter_by(session_id=id).all()
    refund_map = {r.player_id: r for r in refunds}

    # Calculate suggested refund
    suggested_refund = sess.calculate_suggested_refund()

    return render_template('session_refunds.html',
                         session=sess,
                         dropouts=dropouts,
                         fillins=fillins,
                         refunds=refunds,
                         refund_map=refund_map,
                         suggested_refund=suggested_refund)


@app.route('/sessions/<int:id>/refunds/add', methods=['POST'])
@admin_required
def add_dropout_refund(id):
    sess = Session.query.get_or_404(id)
    player_id = int(request.form.get('player_id'))
    refund_amount = float(request.form.get('refund_amount', 0))
    instructions = request.form.get('instructions', '').strip()

    # Check if refund already exists
    existing = DropoutRefund.query.filter_by(session_id=id, player_id=player_id).first()
    if existing:
        flash('Refund already exists for this player. Edit the existing one.', 'error')
        return redirect(url_for('session_refunds', id=id))

    suggested_amount = sess.calculate_suggested_refund()

    refund = DropoutRefund(
        player_id=player_id,
        session_id=id,
        refund_amount=refund_amount,
        suggested_amount=suggested_amount,
        instructions=instructions,
        status='pending'
    )
    db.session.add(refund)
    db.session.commit()

    player = Player.query.get(player_id)
    flash(f'Refund of ${refund_amount:.2f} created for {player.name}', 'success')
    return redirect(url_for('session_refunds', id=id))


@app.route('/refunds/<int:id>/update', methods=['POST'])
@admin_required
def update_dropout_refund(id):
    refund = DropoutRefund.query.get_or_404(id)
    session_id = refund.session_id

    action = request.form.get('action')

    if action == 'update':
        old_amount = refund.refund_amount
        new_amount = float(request.form.get('refund_amount', refund.refund_amount))
        refund.refund_amount = new_amount
        refund.instructions = request.form.get('instructions', '').strip()

        # If already processed, update the corresponding payment record
        if refund.status == 'processed':
            # Find and update the payment record
            payment = Payment.query.filter_by(
                player_id=refund.player_id,
                method='Refund'
            ).filter(
                Payment.notes.like(f'%Dropout refund for session {refund.session.date.strftime("%b %d, %Y")}%')
            ).first()

            if payment:
                payment.amount = -new_amount
                payment.notes = f'Dropout refund for session {refund.session.date.strftime("%b %d, %Y")}. {refund.instructions or ""}'.strip()
                flash(f'Refund updated from ${old_amount:.2f} to ${new_amount:.2f} and payment record adjusted', 'success')
            else:
                flash('Refund updated but could not find corresponding payment record', 'error')
        else:
            flash('Refund updated successfully!', 'success')

    elif action == 'process':
        refund.status = 'processed'
        refund.processed_date = datetime.utcnow()

        # Create a negative payment (credit) for the player
        payment = Payment(
            player_id=refund.player_id,
            amount=-refund.refund_amount,  # Negative amount = credit/refund
            method='Refund',
            date=datetime.utcnow(),
            notes=f'Dropout refund for session {refund.session.date.strftime("%b %d, %Y")}. {refund.instructions or ""}'.strip()
        )
        db.session.add(payment)
        flash(f'Refund of ${refund.refund_amount:.2f} processed and credited to {refund.player.name}', 'success')

    elif action == 'cancel':
        # If already processed, remove the payment record
        if refund.status == 'processed':
            payment = Payment.query.filter_by(
                player_id=refund.player_id,
                method='Refund'
            ).filter(
                Payment.notes.like(f'%Dropout refund for session {refund.session.date.strftime("%b %d, %Y")}%')
            ).first()

            if payment:
                db.session.delete(payment)
                flash('Refund cancelled and payment record removed', 'success')
            else:
                flash('Refund cancelled but could not find corresponding payment record', 'error')
        else:
            flash('Refund cancelled', 'success')

        refund.status = 'cancelled'

    db.session.commit()
    return redirect(url_for('session_refunds', id=session_id))


@app.route('/refunds/<int:id>/delete', methods=['POST'])
@admin_required
def delete_dropout_refund(id):
    refund = DropoutRefund.query.get_or_404(id)
    session_id = refund.session_id
    db.session.delete(refund)
    db.session.commit()
    flash('Refund deleted successfully!', 'success')
    return redirect(url_for('session_refunds', id=session_id))


# Attendance API
@app.route('/api/attendance', methods=['POST'])
@csrf.exempt  # API endpoint uses JSON
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
@csrf.exempt  # API endpoint uses JSON
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


# Birdie Bank routes (admin only)
@app.route('/birdie-bank')
@admin_required
def birdie_bank():
    transactions = BirdieBank.query.order_by(BirdieBank.date.desc()).all()
    current_stock = BirdieBank.get_current_stock()
    total_spent = BirdieBank.get_total_spent()

    # Get sessions for linking usage
    sessions_list = Session.query.order_by(Session.date.desc()).limit(20).all()

    return render_template('birdie_bank.html',
                         transactions=transactions,
                         current_stock=current_stock,
                         total_spent=total_spent,
                         sessions=sessions_list,
                         today=date.today().isoformat())


@app.route('/birdie-bank/add', methods=['POST'])
@admin_required
def add_birdie_transaction():
    transaction_type = request.form.get('transaction_type')
    quantity = int(request.form.get('quantity'))
    cost = float(request.form.get('cost', 0))
    notes = request.form.get('notes')
    date_str = request.form.get('date')
    session_id = request.form.get('session_id')

    transaction_date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()

    transaction = BirdieBank(
        transaction_type=transaction_type,
        quantity=quantity,
        cost=cost if transaction_type == 'purchase' else 0,
        notes=notes,
        date=transaction_date,
        session_id=int(session_id) if session_id else None
    )
    db.session.add(transaction)
    db.session.commit()

    if transaction_type == 'purchase':
        flash(f'Added {quantity} birdies to inventory (${cost:.2f})', 'success')
    else:
        flash(f'Recorded usage of {quantity} birdies', 'success')

    return redirect(url_for('birdie_bank'))


@app.route('/birdie-bank/<int:id>/delete', methods=['POST'])
@admin_required
def delete_birdie_transaction(id):
    transaction = BirdieBank.query.get_or_404(id)
    db.session.delete(transaction)
    db.session.commit()
    flash('Transaction deleted successfully!', 'success')
    return redirect(url_for('birdie_bank'))


# Admin password reset (for player admins)
@app.route('/admin/reset-password', methods=['GET', 'POST'])
@admin_required
def reset_admin_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Verify current admin password
        if current_password != app.config['APP_PASSWORD']:
            flash('Current admin password is incorrect', 'error')
            return redirect(url_for('reset_admin_password'))

        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('reset_admin_password'))

        if len(new_password) < 4:
            flash('Password must be at least 4 characters', 'error')
            return redirect(url_for('reset_admin_password'))

        # Update the password in config (runtime only - need env var for persistence)
        app.config['APP_PASSWORD'] = new_password
        flash('Admin password updated successfully! Note: Update APP_PASSWORD environment variable for persistence.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('reset_admin_password.html')


# Rate limit error handler
@app.errorhandler(429)
def ratelimit_handler(e):
    security_logger.warning(f'RATE_LIMIT_EXCEEDED - IP: {request.remote_addr}, Path: {request.path}')
    flash('Too many requests. Please try again later.', 'error')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
