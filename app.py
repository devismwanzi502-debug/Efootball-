from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, timezone, date
from models import db, User, Pull, Session
import os

app = Flask(__name__)

# ===================== CONFIGURATION FOR RENDER =====================
# Secret key - use environment variable in production
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-to-a-random-secret')

# Database - use PostgreSQL on Render, SQLite locally
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Render uses postgres:// but SQLAlchemy needs postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Local development fallback
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ===================== INITIALIZATION =====================

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create tables on first request
with app.app_context():
    db.create_all()

# ===================== ROUTES =====================

@app.route('/')
def index():
    return render_template('index.html')

# ===== AUTH =====

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('register.html')
        
        # Create user
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Account created! You can now log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not user.check_password(password):
            flash('Invalid username or password.', 'danger')
            return render_template('login.html')
        
        login_user(user)
        flash(f'Welcome back, {user.username}!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# ===== PROFILE =====

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        # Update eFootball account details
        current_user.efootball_username = request.form.get('efootball_username')
        current_user.platform = request.form.get('platform')
        
        creation_date_str = request.form.get('account_creation_date')
        if creation_date_str:
            try:
                current_user.account_creation_date = datetime.strptime(creation_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format.', 'danger')
        else:
            current_user.account_creation_date = None
        
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('profile'))
    
    # Get recent pulls
    recent_pulls = Pull.query.filter_by(user_id=current_user.id)\
        .order_by(Pull.pulled_at.desc()).limit(20).all()
    
    # Calculate account age
    account_age_days = None
    if current_user.account_creation_date:
        account_age_days = (date.today() - current_user.account_creation_date).days
    
    return render_template('profile.html', 
                         pulls=recent_pulls,
                         account_age_days=account_age_days)


# ===== PULLS =====

@app.route('/add_pull', methods=['GET', 'POST'])
@login_required
def add_pull():
    if request.method == 'POST':
        player_name = request.form.get('player_name')
        rating = request.form.get('rating')
        position = request.form.get('position')
        card_type = request.form.get('card_type')
        pack_name = request.form.get('pack_name')
        pack_type = request.form.get('pack_type')
        coins_spent = request.form.get('coins_spent', 0)
        
        # Validation
        if not player_name or not rating:
            flash('Player name and rating are required.', 'danger')
            return render_template('add_pull.html')
        
        try:
            rating = int(rating)
            if rating < 60 or rating > 99:
                flash('Rating must be between 60 and 99.', 'danger')
                return render_template('add_pull.html')
        except ValueError:
            flash('Rating must be a number.', 'danger')
            return render_template('add_pull.html')
        
        # Create pull
        pull = Pull(
            user_id=current_user.id,
            player_name=player_name,
            rating=rating,
            position=position,
            card_type=card_type,
            pack_name=pack_name,
            pack_type=pack_type,
            coins_spent=int(coins_spent) if coins_spent else 0
        )
        db.session.add(pull)
        
        # Update user stats
        current_user.total_spins += 1
        current_user.total_spent_coins += pull.coins_spent
        if rating > current_user.best_pull_rating:
            current_user.best_pull_rating = rating
        if rating >= 95:
            current_user.total_legendary_pulls += 1
        
        db.session.commit()
        flash(f'Added: {player_name} ({rating})', 'success')
        
        if 'add_another' in request.form:
            return redirect(url_for('add_pull'))
        return redirect(url_for('profile'))
    
    return render_template('add_pull.html')


@app.route('/pulls')
@login_required
def view_all_pulls():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Filtering
    rating_min = request.args.get('rating_min', type=int)
    rating_max = request.args.get('rating_max', type=int)
    card_type = request.args.get('card_type')
    position = request.args.get('position')
    sort_by = request.args.get('sort_by', 'date_desc')
    
    query = Pull.query.filter_by(user_id=current_user.id)
    
    if rating_min:
        query = query.filter(Pull.rating >= rating_min)
    if rating_max:
        query = query.filter(Pull.rating <= rating_max)
    if card_type:
        query = query.filter(Pull.card_type == card_type)
    if position:
        query = query.filter(Pull.position == position)
    
    # Sorting
    if sort_by == 'rating_desc':
        query = query.order_by(Pull.rating.desc())
    elif sort_by == 'rating_asc':
        query = query.order_by(Pull.rating.asc())
    elif sort_by == 'date_asc':
        query = query.order_by(Pull.pulled_at.asc())
    else:
        query = query.order_by(Pull.pulled_at.desc())
    
    pulls = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('pulls.html', pulls=pulls)


@app.route('/delete_pull/<int:pull_id>', methods=['POST'])
@login_required
def delete_pull(pull_id):
    pull = Pull.query.get_or_404(pull_id)
    
    if pull.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('view_all_pulls'))
    
    db.session.delete(pull)
    current_user.update_stats()
    db.session.commit()
    
    flash('Pull deleted.', 'info')
    return redirect(url_for('view_all_pulls'))


# ===== ANALYTICS =====

@app.route('/analytics')
@login_required
def analytics():
    all_pulls = Pull.query.filter_by(user_id=current_user.id).all()
    
    if not all_pulls:
        flash('No data yet. Add some pulls first!', 'info')
        return render_template('analytics.html', has_data=False)
    
    # Basic stats
    total = len(all_pulls)
    ratings = [p.rating for p in all_pulls]
    avg_rating = sum(ratings) / total if total else 0
    best_rating = max(ratings) if ratings else 0
    worst_rating = min(ratings) if ratings else 0
    
    # Rating distribution
    rating_dist = {}
    for r in range(60, 100):
        count = sum(1 for p in all_pulls if p.rating == r)
        if count > 0:
            rating_dist[str(r)] = count
    
    # Card type distribution
    card_type_dist = {}
    for p in all_pulls:
        ct = p.card_type or 'Unknown'
        card_type_dist[ct] = card_type_dist.get(ct, 0) + 1
    
    # Position distribution
    pos_dist = {}
    for p in all_pulls:
        pos = p.position or 'Unknown'
        pos_dist[pos] = pos_dist.get(pos, 0) + 1
    
    # Top pulls
    top_pulls = Pull.query.filter_by(user_id=current_user.id)\
        .order_by(Pull.rating.desc()).limit(10).all()
    
    # Monthly activity
    monthly_pulls = {}
    for p in all_pulls:
        month_key = p.pulled_at.strftime('%Y-%m')
        monthly_pulls[month_key] = monthly_pulls.get(month_key, 0) + 1
    
    return render_template('analytics.html', 
                         has_data=True,
                         total=total,
                         avg_rating=round(avg_rating, 1),
                         best_rating=best_rating,
                         worst_rating=worst_rating,
                         rating_dist=rating_dist,
                         card_type_dist=card_type_dist,
                         pos_dist=pos_dist,
                         top_pulls=top_pulls,
                         monthly_pulls=monthly_pulls)


# ===== HEALTH CHECK (for Render) =====

@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200


# ===== ERROR HANDLERS =====

@app.errorhandler(404)
def not_found(e):
    return render_template('base.html', content='<h2>404 - Page Not Found</h2>'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('base.html', content='<h2>500 - Server Error</h2>'), 500


# ===== RUN =====

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
