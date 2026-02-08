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
    profile_photo = db.Column(db.String(255))  # filename of uploaded photo
    managed_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)  # Parent player who can vote/pay for this player
    is_admin = db.Column(db.Boolean, default=False)  # Player admin flag
    is_active = db.Column(db.Boolean, default=True)  # Active/Inactive status
    is_approved = db.Column(db.Boolean, default=False)  # Registration approval status

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    attendances = db.relationship('Attendance', backref='player', lazy='dynamic', cascade='all, delete-orphan', foreign_keys='Attendance.player_id')
    payments = db.relationship('Payment', backref='player', lazy='dynamic', cascade='all, delete-orphan', foreign_keys='Payment.player_id')

    # Managed players relationship (players this player can vote/pay for)
    managed_players = db.relationship('Player', backref=db.backref('manager', remote_side=[id]), foreign_keys=[managed_by])

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
            # Kids pay flat $11 per session
            if attendance.category == 'kid':
                total += 11.0
            else:
                attendee_count = session.attendances.filter_by(status='YES').count()
                if attendee_count > 0:
                    court_cost_per_player = session.get_total_cost() / attendee_count
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
    birdie_cost = db.Column(db.Float, nullable=False, default=0)
    notes = db.Column(db.Text)
    is_archived = db.Column(db.Boolean, default=False)
    voting_frozen = db.Column(db.Boolean, default=False)  # If True, players cannot change their votes

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    attendances = db.relationship('Attendance', backref='session', lazy='dynamic', cascade='all, delete-orphan')
    courts = db.relationship('Court', backref='session', lazy='dynamic', cascade='all, delete-orphan', order_by='Court.id')

    def get_attendee_count(self):
        """Count players who attended (status=YES)"""
        return self.attendances.filter_by(status='YES').count()

    def get_court_count(self):
        """Get number of courts booked"""
        return self.courts.count()

    def get_suggested_courts(self):
        """Suggest number of courts based on attendees (6 players per court)"""
        attendees = self.get_attendee_count()
        if attendees == 0:
            return 1
        import math
        return math.ceil(attendees / 6)

    def get_total_cost(self):
        """Calculate total session cost from all courts"""
        return sum(court.cost for court in self.courts.all())

    def get_time_range(self):
        """Get overall time range from all courts"""
        court_list = self.courts.all()
        if not court_list:
            return "No courts", "No courts"
        start_times = [c.start_time for c in court_list]
        end_times = [c.end_time for c in court_list]
        return min(start_times), max(end_times)

    def get_cost_per_player(self):
        """Calculate cost per attending player"""
        attendee_count = self.get_attendee_count()
        if attendee_count == 0:
            return 0
        court_cost_per_player = self.get_total_cost() / attendee_count
        return round(court_cost_per_player + self.birdie_cost, 2)

    def get_dropout_count(self):
        """Count players who dropped out"""
        return self.attendances.filter_by(status='DROPOUT').count()

    def get_fillin_count(self):
        """Count fill-in players"""
        return self.attendances.filter_by(status='FILLIN').count()

    def calculate_suggested_refund(self):
        """
        Calculate suggested refund amount for a dropout.
        Logic:
        - If there are fill-ins >= dropouts, suggest full refund (someone took their spot)
        - Otherwise, suggest partial refund (cost per player minus birdie cost)
        """
        fillin_count = self.get_fillin_count()
        dropout_count = self.get_dropout_count()

        if fillin_count >= dropout_count and fillin_count > 0:
            # Full refund possible since fill-ins covered the spots
            return self.get_cost_per_player()
        else:
            # Partial refund - they still used some resources (birdie cost is sunk)
            # Refund the court cost portion only
            attendee_count = self.get_attendee_count()
            if attendee_count > 0:
                court_cost_per_player = self.get_total_cost() / attendee_count
                return round(court_cost_per_player, 2)
            return 0

    def get_regular_court_cost(self):
        """Get total cost of regular courts"""
        return sum(court.cost for court in self.courts.all() if court.court_type == 'regular')

    def get_adhoc_court_cost(self):
        """Get total cost of adhoc courts"""
        return sum(court.cost for court in self.courts.all() if court.court_type == 'adhoc')

    def get_total_refunds(self):
        """Get total refunds given for this session"""
        return sum(r.refund_amount for r in self.dropout_refunds if r.status == 'processed')

    def get_total_collection(self):
        """
        Calculate total expected collection from players for this session.
        Sum of cost per player for all attending players (excluding kids who pay flat rate).
        """
        total = 0
        for attendance in self.attendances.filter_by(status='YES').all():
            if attendance.category == 'kid':
                total += 11.0  # Kids pay flat $11
            else:
                total += self.get_cost_per_player()
        return round(total, 2)

    def get_birdie_cost_total(self):
        """Get total birdie cost for the session (birdie_cost * number of attendees)"""
        return round(self.birdie_cost * self.get_attendee_count(), 2)

    def get_regular_player_charges(self):
        """Get total charges from regular players for this session"""
        total = 0
        for attendance in self.attendances.filter_by(status='YES').all():
            if attendance.category == 'regular':
                total += self.get_cost_per_player()
        return round(total, 2)

    def get_adhoc_player_charges(self):
        """Get total charges from adhoc players for this session"""
        total = 0
        for attendance in self.attendances.filter_by(status='YES').all():
            if attendance.category == 'adhoc':
                total += self.get_cost_per_player()
        return round(total, 2)

    def get_kid_player_charges(self):
        """Get total charges from kid players for this session"""
        total = 0
        for attendance in self.attendances.filter_by(status='YES').all():
            if attendance.category == 'kid':
                total += 11.0  # Kids pay flat $11
        return round(total, 2)

    def to_dict(self):
        start_time, end_time = self.get_time_range()
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'start_time': start_time,
            'end_time': end_time,
            'court_count': self.get_court_count(),
            'birdie_cost': self.birdie_cost,
            'notes': self.notes,
            'attendee_count': self.get_attendee_count(),
            'total_cost': self.get_total_cost(),
            'cost_per_player': self.get_cost_per_player()
        }


class Court(db.Model):
    __tablename__ = 'courts'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    name = db.Column(db.String(50), default='Court')  # e.g., "Court 1", "Court A"
    start_time = db.Column(db.String(20), nullable=False)  # "6:30 AM"
    end_time = db.Column(db.String(20), nullable=False)    # "9:30 AM"
    cost = db.Column(db.Float, nullable=False, default=0)
    court_type = db.Column(db.String(20), default='regular')  # 'regular' or 'adhoc'

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'name': self.name,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'cost': self.cost
        }


class Attendance(db.Model):
    __tablename__ = 'attendances'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='NO')  # YES, NO, TENTATIVE, DROPOUT, FILLIN
    category = db.Column(db.String(20), default='regular')  # regular, adhoc, kid - category for this session

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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


class DropoutRefund(db.Model):
    """Track refunds for players who drop out of sessions"""
    __tablename__ = 'dropout_refunds'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    refund_amount = db.Column(db.Float, nullable=False, default=0)
    suggested_amount = db.Column(db.Float, default=0)  # System-calculated suggestion
    instructions = db.Column(db.Text)  # Admin instructions/notes
    status = db.Column(db.String(20), default='pending')  # pending, processed, cancelled
    processed_date = db.Column(db.DateTime, nullable=True)

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    player = db.relationship('Player', foreign_keys=[player_id], backref='dropout_refunds')
    session = db.relationship('Session', backref='dropout_refunds')

    def to_dict(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'player_name': self.player.name if self.player else None,
            'session_id': self.session_id,
            'refund_amount': self.refund_amount,
            'suggested_amount': self.suggested_amount,
            'instructions': self.instructions,
            'status': self.status,
            'processed_date': self.processed_date.isoformat() if self.processed_date else None
        }


class BirdieBank(db.Model):
    """Track birdie (shuttlecock) inventory - purchases and usage"""
    __tablename__ = 'birdie_bank'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'purchase' or 'usage'
    quantity = db.Column(db.Integer, nullable=False)  # positive for purchase, positive for usage (stored as positive, type determines direction)
    cost = db.Column(db.Float, default=0)  # cost for purchases
    notes = db.Column(db.Text)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=True)  # link to session for usage

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session = db.relationship('Session', backref='birdie_transactions')

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'transaction_type': self.transaction_type,
            'quantity': self.quantity,
            'cost': self.cost,
            'notes': self.notes,
            'session_id': self.session_id
        }

    @staticmethod
    def get_current_stock():
        """Calculate current birdie stock"""
        purchases = db.session.query(db.func.sum(BirdieBank.quantity)).filter_by(transaction_type='purchase').scalar() or 0
        usage = db.session.query(db.func.sum(BirdieBank.quantity)).filter_by(transaction_type='usage').scalar() or 0
        return purchases - usage

    @staticmethod
    def get_total_spent():
        """Calculate total amount spent on birdies"""
        return db.session.query(db.func.sum(BirdieBank.cost)).filter_by(transaction_type='purchase').scalar() or 0
