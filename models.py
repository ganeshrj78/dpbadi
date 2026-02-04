from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Player(db.Model):
    __tablename__ = 'players'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(20), nullable=False, default='regular')  # regular, adhoc, kid
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    password_hash = db.Column(db.String(255))
    zelle_preference = db.Column(db.String(10), default='email')  # 'email' or 'phone'
    is_admin = db.Column(db.Boolean, default=False)  # Player admin flag
    is_active = db.Column(db.Boolean, default=True)  # Active/Inactive status
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    attendances = db.relationship('Attendance', backref='player', lazy='dynamic', cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='player', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        """Set password hash from plain text password"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        """Check if provided password matches hash"""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def get_total_charges(self):
        """Calculate total charges from attended sessions"""
        total = 0
        for attendance in self.attendances.filter_by(status='YES').all():
            session = attendance.session
            attendee_count = session.attendances.filter_by(status='YES').count()
            if attendee_count > 0:
                court_cost_per_player = (session.courts * session.court_cost) / attendee_count
                total += court_cost_per_player + session.birdie_cost
        return round(total, 2)

    def get_total_payments(self):
        """Calculate total payments made"""
        return round(sum(p.amount for p in self.payments.all()), 2)

    def get_balance(self):
        """Calculate outstanding balance (charges - payments)"""
        return round(self.get_total_charges() - self.get_total_payments(), 2)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'phone': self.phone,
            'email': self.email,
            'zelle_preference': self.zelle_preference,
            'total_charges': self.get_total_charges(),
            'total_payments': self.get_total_payments(),
            'balance': self.get_balance()
        }


class Session(db.Model):
    __tablename__ = 'sessions'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(20), nullable=False)  # "6:30 AM"
    end_time = db.Column(db.String(20), nullable=False)    # "9:30 AM"
    courts = db.Column(db.Integer, nullable=False, default=1)
    court_cost = db.Column(db.Float, nullable=False, default=0)
    birdie_cost = db.Column(db.Float, nullable=False, default=0)
    notes = db.Column(db.Text)

    attendances = db.relationship('Attendance', backref='session', lazy='dynamic', cascade='all, delete-orphan')

    def get_attendee_count(self):
        """Count players who attended (status=YES)"""
        return self.attendances.filter_by(status='YES').count()

    def get_total_cost(self):
        """Calculate total session cost"""
        return self.courts * self.court_cost

    def get_cost_per_player(self):
        """Calculate cost per attending player"""
        attendee_count = self.get_attendee_count()
        if attendee_count == 0:
            return 0
        court_cost_per_player = self.get_total_cost() / attendee_count
        return round(court_cost_per_player + self.birdie_cost, 2)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'start_time': self.start_time,
            'end_time': self.end_time,
            'courts': self.courts,
            'court_cost': self.court_cost,
            'birdie_cost': self.birdie_cost,
            'notes': self.notes,
            'attendee_count': self.get_attendee_count(),
            'total_cost': self.get_total_cost(),
            'cost_per_player': self.get_cost_per_player()
        }


class Attendance(db.Model):
    __tablename__ = 'attendances'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='NO')  # YES, NO, TENTATIVE, DROPOUT, FILLIN
    category = db.Column(db.String(20), default='regular')  # regular, adhoc, kid - category for this session

    __table_args__ = (db.UniqueConstraint('player_id', 'session_id', name='unique_player_session'),)

    def to_dict(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'session_id': self.session_id,
            'status': self.status,
            'category': self.category,
            'player_name': self.player.name if self.player else None
        }


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(20), nullable=False)  # Zelle, Cash, Venmo
    date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

    def to_dict(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'player_name': self.player.name if self.player else None,
            'amount': self.amount,
            'method': self.method,
            'date': self.date.isoformat(),
            'notes': self.notes
        }
