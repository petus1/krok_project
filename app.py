from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from dotenv import load_dotenv
from io import BytesIO
import zipfile
from flask import send_file
import secrets
from sqlalchemy import func

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Лучше использовать переменную окружения

DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL is None:
    raise ValueError("Не установлена переменная окружения DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Убрали db_session - используем db.session напрямую

# Конфигурация для загрузки файлов
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx', 'xls', 'xlsx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB (было 25MB)

# Создаем папку для загрузок, если её нет
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Модели базы данных
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # A, B (Безопасность), BU (Бухгалтерия), GR, R, S, K, TK, Z
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    passport_data = db.Column(db.Text)
    department = db.Column(db.String(100))
    email = db.Column(db.String(100))  # Email для уведомлений

    # Исправлены отношения с явным указанием foreign_keys
    manager = db.relationship('User', remote_side=[id], backref='subordinates')
    created_trips = db.relationship('BusinessTrip', backref='employee', 
                                   foreign_keys='BusinessTrip.employee_id')
    managed_trips = db.relationship('BusinessTrip', backref='manager_rel',
                                   foreign_keys='BusinessTrip.manager_id')


class BusinessTrip(db.Model):
    __tablename__ = 'business_trip'
    id = db.Column(db.Integer, primary_key=True)
    trip_number = db.Column(db.String(20), unique=True)
    created_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(50), default='Планируемая')

    # Основная информация
    employee_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    department = db.Column(db.String(100))

    # Детали поездки
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    duration = db.Column(db.Integer)
    trip_format = db.Column(db.String(20))  # Онлайн/Оффлайн
    destination = db.Column(db.String(200))
    purpose = db.Column(db.String(200))
    project_number = db.Column(db.String(50))
    regularity = db.Column(db.String(50))  # Регулярность
    receiving_party = db.Column(db.String(200))  # Принимающая сторона
    cancellation_reason = db.Column(db.String(200))  # Причина отмены/несогласования
    is_activated = db.Column(db.Boolean, default=False)  # Активирована ли командировка
    approval_date = db.Column(db.DateTime)  # Дата согласования
    approval_request_date = db.Column(db.DateTime)  # Дата запроса на согласование

    # Расходы
    estimated_costs = db.Column(db.Float)
    cost_details_text = db.Column(db.Text)  # Исправлено: было cost_details, стало cost_details_text
    over_limit = db.Column(db.Boolean, default=False)
    overrun_approved = db.Column(db.Boolean, default=False)  # Перерасход согласован
    actual_costs = db.Column(db.Float)  # Фактические расходы

    # Бронирование
    transport_type = db.Column(db.String(50))
    transport_type_return = db.Column(db.String(50))  # Тип транспорта обратно
    departure_city = db.Column(db.String(100))
    arrival_city = db.Column(db.String(100))
    departure_city_return = db.Column(db.String(100))
    arrival_city_return = db.Column(db.String(100))
    departure_date_min = db.Column(db.DateTime)  # Не раньше (туда)
    arrival_date_max = db.Column(db.DateTime)  # Не позже (туда)
    departure_date_min_return = db.Column(db.DateTime)  # Не раньше (обратно)
    arrival_date_max_return = db.Column(db.DateTime)  # Не позже (обратно)
    transfer_to = db.Column(db.String(200))  # Трансфер до
    transfer_from = db.Column(db.String(200))  # Трансфер обратно
    hotel_name = db.Column(db.String(200))
    check_in = db.Column(db.DateTime)
    check_out = db.Column(db.DateTime)
    hotel_rooms = db.Column(db.Integer)  # Количество мест/номеров
    contact_phone = db.Column(db.String(50))  # Контактный телефон
    booking_notes = db.Column(db.Text)  # Дополнительная информация для ТК
    booking_completed = db.Column(db.Boolean, default=False)  # Бронирование выполнено
    booking_completed_date = db.Column(db.DateTime)
    booking_overrun_approved = db.Column(db.Boolean, default=False)  # Перерасход по бронированию согласован

    # Отчет
    geo_location = db.Column(db.String(200))
    geo_location_date = db.Column(db.DateTime)  # Дата установки геолокации
    report_overrun_approved = db.Column(db.Boolean, default=False)  # Перерасход в отчете согласован
    report_prepared = db.Column(db.Boolean, default=False)  # Отчёт подготовлен
    report_reviewed = db.Column(db.Boolean, default=False)  # Отчёт проверен
    trip_closed = db.Column(db.Boolean, default=False)  # Командировка закрыта
    geo_location_verified = db.Column(db.Boolean, default=False)  # Проверено руководителем
    geo_location_verified_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    geo_location_verified_date = db.Column(db.DateTime)

    # Закупки
    procurement_needed = db.Column(db.Boolean, default=False)
    procurement_done = db.Column(db.Boolean, default=False)
    procurement_costs = db.Column(db.Float)
    procurement_details = db.Column(db.Text)  # Детализация задания к закупке
    procurement_report = db.Column(db.Text)  # Отчет по закупке материалов


class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('business_trip.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50))  # Тип файла: ticket, hotel, report, other
    description = db.Column(db.Text)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    trip = db.relationship('BusinessTrip', backref='documents')
    uploaded_by = db.relationship('User')


class TripCost(db.Model):
    __tablename__ = 'trip_costs'
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('business_trip.id'), nullable=False)
    category = db.Column(db.String(100))
    amount = db.Column(db.Float)
    comment = db.Column(db.Text)

    trip = db.relationship('BusinessTrip', backref='cost_details')

# Добавьте в модели (рядом с другими моделями)
class GeoLocationHistory(db.Model):
    __tablename__ = 'geo_location_history'
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('business_trip.id'), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    location_type = db.Column(db.String(20))  # 'auto', 'manual', 'ip'
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    accuracy = db.Column(db.Float)  # Точность в метрах
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    trip = db.relationship('BusinessTrip', backref='geo_history')
    created_by = db.relationship('User')

# Декораторы для проверки прав доступа
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            user = db.session.get(User, session['user_id'])
            if not user:
                flash('Пользователь не найден', 'error')
                return redirect(url_for('login'))
            if user.role not in roles:
                flash('Недостаточно прав для доступа к этой странице', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Функция для проверки просроченных согласований и перенаправления на ГР
def check_and_redirect_overdue_approvals():
    """Проверяет заявки, ожидающие согласования более 1 рабочего дня, и перенаправляет на ГР"""
    now = datetime.now(timezone.utc)
    one_working_day = timedelta(days=1)

    overdue_trips = BusinessTrip.query.filter(
        BusinessTrip.status == 'Ожидают согласования',
        BusinessTrip.approval_request_date.isnot(None)
    ).all()

    for trip in overdue_trips:
        if trip.approval_request_date:
            time_diff = now - trip.approval_request_date
            if time_diff > one_working_day:
                # Находим главного руководителя
                gr_manager = User.query.filter_by(role='GR').first()
                if gr_manager:
                    # Перенаправляем на ГР
                    trip.manager_id = gr_manager.id
                    # Обновляем дату запроса на согласование
                    trip.approval_request_date = now
                    db.session.commit()

# Маршруты аутентификации
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['full_name'] = user.full_name
            flash('Вы успешно вошли в систему', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))


# Основные маршруты
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    # Проверяем просроченные согласования
    check_and_redirect_overdue_approvals()

    user = db.session.get(User, session['user_id'])
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('login'))

    # Логика отображения заявок в зависимости от роли
    if user.role == 'A':  # Администратор
        trips = BusinessTrip.query.all()
    elif user.role == 'B':  # Отдел безопасности
        trips = BusinessTrip.query.all()
    elif user.role == 'BU':  # Бухгалтерия
        trips = BusinessTrip.query.all()
    elif user.role == 'GR':  # Главный руководитель
        trips = BusinessTrip.query.all()
    elif user.role == 'R':  # Руководитель
        # Свои заявки и заявки подчиненных
        subordinate_ids = [sub.id for sub in user.subordinates]
        trips = BusinessTrip.query.filter(
            (BusinessTrip.employee_id == user.id) |
            (BusinessTrip.employee_id.in_(subordinate_ids))
        ).all()
    elif user.role == 'S':  # Сотрудник
        trips = BusinessTrip.query.filter_by(employee_id=user.id).all()
    elif user.role == 'K':  # Отдел кадров
        trips = BusinessTrip.query.all()
    elif user.role == 'TK':  # Travel-координатор
        trips = BusinessTrip.query.all()
    elif user.role == 'Z':  # Отдел закупок
        # Видит только заявки, где нужна закупка
        trips = BusinessTrip.query.filter_by(procurement_needed=True).all()
    else:
        trips = BusinessTrip.query.all()

    return render_template('dashboard.html', user=user, trips=trips, now=datetime.now(timezone.utc))


@app.route('/trips')
@login_required
def trips():
    check_and_redirect_overdue_approvals()
    
    user = db.session.get(User, session['user_id'])
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('login'))

    # Базовый запрос в зависимости от роли
    if user.role == 'A':  # Администратор
        base_query = BusinessTrip.query
    elif user.role == 'B':  # Отдел безопасности
        base_query = BusinessTrip.query
    elif user.role == 'BU':  # Бухгалтерия
        base_query = BusinessTrip.query
    elif user.role == 'GR':  # Главный руководитель
        base_query = BusinessTrip.query
    elif user.role == 'R':  # Руководитель
        subordinate_ids = [sub.id for sub in user.subordinates]
        base_query = BusinessTrip.query.filter(
            (BusinessTrip.employee_id == user.id) |
            (BusinessTrip.employee_id.in_(subordinate_ids))
        )
    elif user.role == 'S':  # Сотрудник
        base_query = BusinessTrip.query.filter_by(employee_id=user.id)
    elif user.role == 'K':  # Отдел кадров
        base_query = BusinessTrip.query
    elif user.role == 'TK':  # Travel-координатор
        base_query = BusinessTrip.query
    elif user.role == 'Z':  # Отдел закупок
        base_query = BusinessTrip.query.filter_by(procurement_needed=True)
    else:
        base_query = BusinessTrip.query

    # Применяем фильтры
    project_number = request.args.get('project_number')
    department = request.args.get('department')
    status = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    employee_id = request.args.get('employee_id')

    if project_number:
        base_query = base_query.filter(BusinessTrip.project_number.contains(project_number))
    if department:
        base_query = base_query.filter(BusinessTrip.department.contains(department))
    if status:
        base_query = base_query.filter(BusinessTrip.status == status)
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            base_query = base_query.filter(BusinessTrip.start_date >= date_from_obj)
        except ValueError:
            pass
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            base_query = base_query.filter(BusinessTrip.end_date <= date_to_obj)
        except ValueError:
            pass
    if employee_id:
        try:
            base_query = base_query.filter(BusinessTrip.employee_id == int(employee_id))
        except ValueError:
            pass

    # Только активированные заявки
    base_query = base_query.filter(BusinessTrip.is_activated == True)

    trips = base_query.order_by(BusinessTrip.created_date.desc()).all()

    # Получаем списки для фильтров
    departments = db.session.query(BusinessTrip.department).distinct().all()
    departments = [d[0] for d in departments if d[0]]
    statuses = db.session.query(BusinessTrip.status).distinct().all()
    statuses = [s[0] for s in statuses if s[0]]
    employees = User.query.all() if user.role in ['A', 'B', 'GR'] else []

    return render_template('trips.html', user=user, trips=trips,
                           departments=departments, statuses=statuses, employees=employees,
                           current_filters={'project_number': project_number, 'department': department,
                                            'status': status, 'date_from': date_from, 'date_to': date_to,
                                            'employee_id': employee_id})


@app.route('/create_trip', methods=['GET', 'POST'])
@login_required
@role_required(['A', 'GR', 'R', 'S'])
def create_trip():
    if request.method == 'POST':
        try:
            user = db.session.get(User, session['user_id'])
            if not user:
                flash('Пользователь не найден', 'error')
                return redirect(url_for('login'))

            # Определяем employee_id
            employee_id = request.form.get('employee_id')
            if not employee_id:
                employee_id = session['user_id']
            else:
                employee_id = int(employee_id)

            # Проверка прав
            if user.role == 'R' and employee_id != user.id:
                subordinate_ids = [sub.id for sub in user.subordinates]
                if employee_id not in subordinate_ids:
                    flash('Вы можете создавать заявки только для своих подчиненных', 'error')
                    return redirect(url_for('create_trip'))

            employee = db.session.get(User, employee_id)
            if not employee:
                flash('Сотрудник не найден', 'error')
                return redirect(url_for('create_trip'))

            start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
            end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
            duration = (end_date - start_date).days + 1

            make_active = request.form.get('make_active') == 'on'

            # Определяем статус и активацию
            initial_status = 'Активированная' if make_active else 'Планируемая'
            is_activated_value = make_active

            trip = BusinessTrip(
                trip_number=f"BT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
                employee_id=employee_id,
                manager_id=employee.manager_id,
                department=request.form.get('department') or employee.department,
                start_date=start_date,
                end_date=end_date,
                duration=duration,
                destination=request.form['destination'],
                purpose=request.form['purpose'],
                estimated_costs=float(request.form['estimated_costs']),
                cost_details_text=request.form.get('cost_details', ''),  # Исправлено
                trip_format=request.form.get('trip_format', ''),
                project_number=request.form.get('project_number', ''),
                regularity=request.form.get('regularity', ''),
                receiving_party=request.form.get('receiving_party', ''),
                over_limit=request.form.get('over_limit') == 'on',
                status=initial_status,
                is_activated=is_activated_value
            )
            db.session.add(trip)
            db.session.commit()
            flash('Заявка на командировку создана', 'success')
            return redirect(url_for('trips'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при создании заявки: {str(e)}', 'error')

    user = db.session.get(User, session['user_id'])
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('login'))

    managers = User.query.filter(User.role.in_(['R', 'GR'])).all()
    employees = []
    if user.role == 'A' or user.role == 'GR':
        employees = User.query.filter(User.role == 'S').all()
    elif user.role == 'R':
        employees = user.subordinates
    return render_template('create_trip.html', user=user, managers=managers, employees=employees)


@app.route('/trip/<int:trip_id>')
@login_required
def trip_detail(trip_id):
    check_and_redirect_overdue_approvals()

    trip = db.session.get(BusinessTrip, trip_id)
    if not trip:
        flash('Заявка не найдена', 'error')
        return redirect(url_for('dashboard'))

    user = db.session.get(User, session['user_id'])
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('login'))

    # Проверка прав доступа
    if user.role == 'S' and trip.employee_id != user.id:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('dashboard'))
    elif user.role == 'R' and trip.employee_id != user.id and trip.employee_id not in [sub.id for sub in user.subordinates]:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('dashboard'))
    elif user.role == 'Z' and not trip.procurement_needed:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('dashboard'))

    return render_template('trip_detail.html', user=user, trip=trip)


@app.route('/reports')
@login_required
@role_required(['A', 'B', 'BU', 'GR', 'R', 'S', 'TK', 'Z'])
def reports():
    user = db.session.get(User, session['user_id'])
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('login'))

    # Базовый запрос - только активированные заявки
    base_query = BusinessTrip.query.filter(BusinessTrip.is_activated == True)

    # Фильтрация по ролям
    if user.role == 'R':
        subordinate_ids = [sub.id for sub in user.subordinates]
        base_query = base_query.filter(
            (BusinessTrip.employee_id == user.id) |
            (BusinessTrip.employee_id.in_(subordinate_ids))
        )
    elif user.role == 'S':
        base_query = base_query.filter_by(employee_id=user.id)
    elif user.role == 'Z':
        base_query = base_query.filter_by(procurement_needed=True)

    # Применяем фильтры
    project_number = request.args.get('project_number')
    purpose = request.args.get('purpose')
    status_cancel = request.args.get('status_cancel') == 'true'
    status_not_approved = request.args.get('status_not_approved') == 'true'
    status_closed = request.args.get('status_closed') == 'true'
    sort_by = request.args.get('sort_by', 'costs')  # costs, overrun
    

    if project_number:
        base_query = base_query.filter(BusinessTrip.project_number.contains(project_number))
    if purpose:
        base_query = base_query.filter(BusinessTrip.purpose.contains(purpose))
    if status_cancel:
        base_query = base_query.filter(BusinessTrip.status == 'Отменена')
    if status_not_approved:
        base_query = base_query.filter(BusinessTrip.status == 'Не согласована')
    if status_closed:
        base_query = base_query.filter(BusinessTrip.trip_closed == True)

    # Сортировка
    if sort_by == 'costs':
        trips = base_query.order_by(BusinessTrip.estimated_costs.desc()).all()
    elif sort_by == 'overrun':
        trips = base_query.all()
        trips.sort(key=lambda t: (t.actual_costs or t.estimated_costs or 0) - (t.estimated_costs or 0), reverse=True)
    else:
        trips = base_query.order_by(BusinessTrip.created_date.desc()).all()

    # Статистика для графиков
    total_trips = len(trips)
    total_costs = sum(t.estimated_costs or 0 for t in trips)
    total_actual_costs = sum(t.actual_costs or 0 for t in trips if t.actual_costs)
    overrun_trips = [t for t in trips if t.over_limit]
    overrun_amount = sum((t.actual_costs or t.estimated_costs or 0) - (t.estimated_costs or 0)
                         for t in overrun_trips if
                         (t.actual_costs or t.estimated_costs or 0) > (t.estimated_costs or 0))

    # Данные для графиков
    status_counts = defaultdict(int)
    monthly_costs = defaultdict(float)
    monthly_actual = defaultdict(float)
    department_costs = defaultdict(float)
    total_trips_with_overrun = 0
    total_trips_without_overrun = 0

    for trip in trips:
        status_counts[trip.status] += 1
        if trip.overrun_approved or trip.booking_overrun_approved or trip.report_overrun_approved:
            total_trips_with_overrun += 1
        else:
            total_trips_without_overrun += 1
        
        if trip.start_date:
            month_key = trip.start_date.strftime('%Y-%m')
            monthly_costs[month_key] += trip.estimated_costs or 0
            monthly_actual[month_key] += trip.actual_costs or 0
        if trip.department:
            department_costs[trip.department] += trip.estimated_costs or 0
    
    status_overrun_counts = {
        'Согласованный перерасход': total_trips_with_overrun,
        'Без согласованного перерасхода': total_trips_without_overrun
    }

    return render_template('reports.html', user=user, trips=trips,
                           total_trips=total_trips, total_costs=total_costs,
                           total_actual_costs=total_actual_costs, overrun_trips=len(overrun_trips),
                           overrun_amount=overrun_amount,
                           status_counts=dict(status_counts),
                           status_overrun_counts=dict(status_overrun_counts),
                           monthly_costs=dict(monthly_costs),
                           monthly_actual=dict(monthly_actual),
                           department_costs=dict(department_costs),
                           current_filters={'project_number': project_number, 'purpose': purpose,
                                            'status_cancel': status_cancel, 'status_not_approved': status_not_approved,
                                            'status_closed': status_closed, 'sort_by': sort_by})


@app.route('/planning')
@login_required
@role_required(['A', 'B', 'BU', 'GR', 'R', 'S'])
def planning():
    user = db.session.get(User, session['user_id'])
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('login'))

    # Запланированные командировки с учетом ролей
    base_query = BusinessTrip.query.filter_by(status='Планируемая')

    if user.role == 'A' or user.role == 'B' or user.role == 'BU' or user.role == 'GR':
        planned_trips = base_query.all()
    elif user.role == 'R':
        subordinate_ids = [sub.id for sub in user.subordinates]
        planned_trips = base_query.filter(
            (BusinessTrip.employee_id == user.id) |
            (BusinessTrip.employee_id.in_(subordinate_ids))
        ).all()
    elif user.role == 'S':
        planned_trips = base_query.filter_by(employee_id=user.id).all()
    else:
        planned_trips = base_query.all()

    return render_template('planning.html', user=user, trips=planned_trips)


@app.route('/employees')
@login_required
@role_required(['A', 'B'])
def employees():
    user = db.session.get(User, session['user_id'])
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('login'))

    employees_list = User.query.all()
    managers = User.query.filter(User.role.in_(['R', 'GR'])).all()
    return render_template('employees.html', user=user, employees=employees_list, managers=managers)


@app.route('/employees/create', methods=['GET', 'POST'])
@login_required
@role_required(['A'])
def create_employee():
    if request.method == 'POST':
        try:
            employee = User(
                username=request.form['username'],
                password_hash=generate_password_hash(request.form['password']),
                full_name=request.form['full_name'],
                role=request.form['role'],
                manager_id=int(request.form['manager_id']) if request.form.get('manager_id') else None,
                department=request.form.get('department', ''),
                passport_data=request.form.get('passport_data', ''),
                email=request.form.get('email', '')
            )
            db.session.add(employee)
            db.session.commit()
            flash('Сотрудник успешно создан', 'success')
            return redirect(url_for('employees'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при создании сотрудника: {str(e)}', 'error')

    managers = User.query.filter(User.role.in_(['R', 'GR'])).all()
    return render_template('employee_form.html', user=None, managers=managers,
                           roles=['A', 'B', 'BU', 'GR', 'R', 'S', 'K', 'TK', 'Z'])


@app.route('/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['A'])
def edit_employee(employee_id):
    employee = db.session.get(User, employee_id)
    if not employee:
        flash('Сотрудник не найден', 'error')
        return redirect(url_for('employees'))

    if request.method == 'POST':
        try:
            employee.username = request.form['username']
            if request.form.get('password'):
                employee.password_hash = generate_password_hash(request.form['password'])
            employee.full_name = request.form['full_name']
            employee.role = request.form['role']
            employee.manager_id = int(request.form['manager_id']) if request.form.get('manager_id') else None
            employee.department = request.form.get('department', '')
            employee.passport_data = request.form.get('passport_data', '')
            employee.email = request.form.get('email', '')

            db.session.commit()
            flash('Сотрудник успешно обновлен', 'success')
            return redirect(url_for('employees'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении сотрудника: {str(e)}', 'error')

    managers = User.query.filter(User.role.in_(['R', 'GR'])).all()
    return render_template('employee_form.html', user=employee, managers=managers,
                           roles=['A', 'B', 'BU', 'GR', 'R', 'S', 'K', 'TK', 'Z'])


@app.route('/employees/<int:employee_id>/delete', methods=['POST'])
@login_required
@role_required(['A'])
def delete_employee(employee_id):
    employee = db.session.get(User, employee_id)
    if not employee:
        flash('Сотрудник не найден', 'error')
        return redirect(url_for('employees'))
        
    if employee.id == session['user_id']:
        flash('Нельзя удалить самого себя', 'error')
        return redirect(url_for('employees'))

    try:
        db.session.delete(employee)
        db.session.commit()
        flash('Сотрудник успешно удален', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении сотрудника: {str(e)}', 'error')

    return redirect(url_for('employees'))


# API endpoints для AJAX операций
@app.route('/api/update_trip_status/<int:trip_id>', methods=['POST'])
@login_required
def update_trip_status(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})

        new_status = request.json.get('status')
        if new_status:
            trip.status = new_status
            db.session.commit()
            return jsonify({'success': True, 'new_status': new_status})

        return jsonify({'success': False})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/trip/<int:trip_id>/verify_geo_location', methods=['POST'])
@login_required
def verify_geo_location(trip_id):
    """Проверка геолокации руководителем"""
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['R', 'GR']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        
        verified = request.json.get('verified', False)
        
        trip.geo_location_verified = verified
        if verified:
            trip.geo_location_verified_by = user.id
            trip.geo_location_verified_date = datetime.now(timezone.utc)
        else:
            trip.geo_location_verified_by = None
            trip.geo_location_verified_date = None
        
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/trip/<int:trip_id>/activate', methods=['POST'])
@login_required
def activate_trip(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'GR', 'R'] and trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.is_activated = True
        trip.status = 'Активированная'
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/send_for_approval', methods=['POST'])
@login_required
def send_for_approval(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'GR', 'R'] and trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.status = 'Ожидают согласования'
        trip.approval_request_date = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/upload_document', methods=['POST'])
@login_required
def upload_document(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        # Проверка прав доступа
        if user.role == 'S' and trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Вы можете загружать документы только для своих командировок'})
        elif user.role == 'R' and trip.employee_id != user.id and trip.employee_id not in [sub.id for sub in user.subordinates]:
            return jsonify({'success': False, 'error': 'Доступ запрещен'})
        elif user.role == 'Z' and not trip.procurement_needed:
            return jsonify({'success': False, 'error': 'Доступ запрещен'})
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'Файл не найден'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Файл не выбран'})
        
        if file and allowed_file(file.filename):
            # Проверяем размер файла
            file.seek(0, os.SEEK_END)
            file_length = file.tell()
            file.seek(0)
            
            if file_length > MAX_FILE_SIZE:
                return jsonify({'success': False, 'error': 'Размер файла превышает 10MB'})
            
            # Создаем уникальное имя файла
            filename = secure_filename(file.filename)
            unique_filename = f"{trip_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{filename}"
            file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
            
            # Сохраняем файл
            file.save(file_path)
            
            # Создаем запись в базе данных
            document = Document(
                trip_id=trip_id,
                filename=filename,
                file_path=f"/static/uploads/{unique_filename}",
                file_type=request.form.get('file_type', 'other'),
                description=request.form.get('description', ''),
                uploaded_by_id=user.id
            )
            
            db.session.add(document)
            db.session.commit()
            
            # Если тип файла - отчет, обновляем статус отчета
            if request.form.get('file_type') == 'report' and user.role == 'S':
                trip.report_prepared = True
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'document': {
                    'id': document.id,
                    'filename': document.filename,
                    'file_path': document.file_path,
                    'file_type': document.file_type,
                    'description': document.description,
                    'upload_date': document.upload_date.strftime('%d.%m.%Y %H:%M'),
                    'uploaded_by': document.uploaded_by.full_name
                }
            })
        else:
            return jsonify({'success': False, 'error': 'Недопустимый формат файла'})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/document/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    try:
        document = db.session.get(Document, document_id)
        if not document:
            return jsonify({'success': False, 'error': 'Документ не найден'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        # Проверка прав доступа
        trip = document.trip
        can_delete = False
        
        if user.role in ['A', 'B', 'BU', 'GR']:
            can_delete = True
        elif user.role == 'R':
            subordinate_ids = [sub.id for sub in user.subordinates]
            if trip.employee_id == user.id or trip.employee_id in subordinate_ids:
                can_delete = True
        elif user.role == 'S' and trip.employee_id == user.id:
            can_delete = True
        elif user.id == document.uploaded_by_id:
            can_delete = True
        
        if not can_delete:
            return jsonify({'success': False, 'error': 'Недостаточно прав для удаления документа'})
        
        # Удаляем файл с диска
        try:
            file_path = document.file_path.replace('/static/', '')
            full_path = os.path.join(app.root_path, file_path)
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception as e:
            print(f"Ошибка при удалении файла: {str(e)}")
        
        # Удаляем запись из базы данных
        db.session.delete(document)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/documents')
@login_required
def get_trip_documents(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        # Проверка прав доступа
        if user.role == 'S' and trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Доступ запрещен'})
        elif user.role == 'R' and trip.employee_id != user.id and trip.employee_id not in [sub.id for sub in user.subordinates]:
            return jsonify({'success': False, 'error': 'Доступ запрещен'})
        elif user.role == 'Z' and not trip.procurement_needed:
            return jsonify({'success': False, 'error': 'Доступ запрещен'})
        
        # Получаем документы и группируем по типам
        documents = Document.query.filter_by(trip_id=trip_id).order_by(Document.upload_date.desc()).all()
        
        documents_by_type = {
            'ticket': [],
            'hotel': [],
            'report': [],
            'receipt': [],
            'other': []
        }
        
        for doc in documents:
            doc_dict = {
                'id': doc.id,
                'filename': doc.filename,
                'file_path': doc.file_path,
                'file_type': doc.file_type or 'other',
                'description': doc.description,
                'upload_date': doc.upload_date.strftime('%d.%m.%Y %H:%M'),
                'uploaded_by': doc.uploaded_by.full_name,
                'can_delete': (
                    user.role in ['A', 'B', 'BU', 'GR'] or
                    user.role == 'R' and (trip.employee_id == user.id or trip.employee_id in [sub.id for sub in user.subordinates]) or
                    user.id == doc.uploaded_by_id or
                    user.role == 'S' and trip.employee_id == user.id
                )
            }
            
            if doc.file_type in documents_by_type:
                documents_by_type[doc.file_type].append(doc_dict)
            else:
                documents_by_type['other'].append(doc_dict)
        
        return jsonify({
            'success': True,
            'documents': documents_by_type,
            'total': len(documents)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/deactivate', methods=['POST'])
@login_required
def deactivate_trip(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'GR', 'R'] and trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.is_activated = False
        trip.status = 'Планируемая'
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/reject', methods=['POST'])
@login_required
def reject_trip(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['R', 'GR']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.status = 'Не согласована'
        trip.cancellation_reason = request.json.get('reason', '')
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/cancel', methods=['POST'])
@login_required
def cancel_trip(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'GR', 'R'] and trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.status = 'Отменена'
        trip.cancellation_reason = request.json.get('reason', '')
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/approve_overrun', methods=['POST'])
@login_required
def approve_overrun(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['R', 'GR']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.overrun_approved = True
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/approve_booking_overrun', methods=['POST'])
@login_required
def approve_booking_overrun(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'TK']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.booking_overrun_approved = True
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/complete_booking', methods=['POST'])
@login_required
def complete_booking(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        # Разрешаем сотруднику отмечать бронирование выполненным
        if user.role not in ['A', 'TK'] and (user.role != 'S' or trip.employee_id != user.id):
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        
        if trip.booking_completed:
            return jsonify({'success': False, 'error': 'Бронирование уже отмечено как выполненное'})
        
        # Проверяем заполнены ли основные поля бронирования
        required_fields = ['transport_type', 'departure_city', 'arrival_city']
        missing_fields = []
        for field in required_fields:
            if not getattr(trip, field):
                missing_fields.append(field)
        
        if missing_fields:
            return jsonify({
                'success': False, 
                'error': 'Заполните обязательные поля бронирования: ' + ', '.join(missing_fields)
            })
        
        trip.booking_completed = True
        trip.booking_completed_date = datetime.now(timezone.utc)
        db.session.commit()
        
        # Отправляем уведомление travel-координаторам
        send_booking_completion_notification(trip, user)
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


def send_booking_completion_notification(trip, completed_by):
    """Отправка уведомления о выполнении бронирования"""
    try:
        # Находим travel-координаторов
        tk_users = User.query.filter_by(role='TK').all()
        message = f"Бронирование для командировки {trip.trip_number} отмечено как выполненное пользователем {completed_by.full_name}"
        
        for tk_user in tk_users:
            # Здесь можно реализовать отправку email или других уведомлений
            print(f"УВЕДОМЛЕНИЕ для travel-координатора {tk_user.full_name}: {message}")
            
    except Exception as e:
        print(f"Ошибка отправки уведомлений: {e}")


@app.route('/api/trip/<int:trip_id>/procurement', methods=['POST'])
@login_required
def toggle_procurement(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'Z']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.procurement_needed = request.json.get('needed', False)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/procurement_done', methods=['POST'])
@login_required
def toggle_procurement_done(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'Z']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.procurement_done = request.json.get('done', False)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/geo_location', methods=['POST'])
@login_required
def set_geo_location(trip_id):
    """Установка геолокации командируемым сотрудником"""
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        # Проверяем, что геопозицию устанавливает командируемый сотрудник
        if user.id != trip.employee_id:
            return jsonify({'success': False, 'error': 'Только командируемый сотрудник может установить геопозицию'})
        
        location = request.json.get('location', '')
        location_type = request.json.get('location_type', 'auto')  # auto, manual
        accuracy = request.json.get('accuracy')
        
        if not location:
            return jsonify({'success': False, 'error': 'Не указано местоположение'})
        
        # Сохраняем геопозицию
        trip.geo_location = location
        trip.geo_location_date = datetime.now(timezone.utc)
        trip.geo_location_verified = False  # Сбрасываем проверку при обновлении
        
        # Сохраняем в историю
        geo_history = GeoLocationHistory(
            trip_id=trip_id,
            location=location,
            location_type=location_type,
            accuracy=accuracy,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            created_by_id=user.id
        )
        
        # Парсим координаты если есть
        if ',' in location:
            try:
                parts = location.split(',')
                if len(parts) >= 2:
                    geo_history.latitude = float(parts[0].strip())
                    geo_history.longitude = float(parts[1].strip())
            except:
                pass
        
        db.session.add(geo_history)
        db.session.commit()
        
        # Уведомление руководителям
        send_geo_notification_to_managers(trip, user, location)
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# Получение истории геолокаций
@app.route('/api/trip/<int:trip_id>/geo_history')
@login_required
def get_geo_history(trip_id):
    """Получение истории геолокаций командируемого"""
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        # Только руководители и администраторы видят историю
        if user.role not in ['A', 'R', 'GR', 'B']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        
        history = GeoLocationHistory.query.filter_by(trip_id=trip_id).order_by(GeoLocationHistory.created_date.desc()).all()
        
        history_list = []
        for record in history:
            history_list.append({
                'id': record.id,
                'location': record.location,
                'location_type': record.location_type,
                'accuracy': record.accuracy,
                'created_by': record.created_by.full_name,
                'created_date': record.created_date.strftime('%d.%m.%Y %H:%M:%S'),
                'ip_address': record.ip_address[:15] + '...' if record.ip_address and len(record.ip_address) > 15 else record.ip_address,
                'user_agent': record.user_agent[:50] + '...' if record.user_agent and len(record.user_agent) > 50 else record.user_agent
            })
        
        return jsonify({
            'success': True,
            'history': history_list,
            'total': len(history_list)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
# Функция уведомления руководителей
def send_geo_notification_to_managers(trip, employee, location):
    """Отправка уведомлений руководителям об установке геопозиции"""
    try:
        # Находим руководителей сотрудника
        managers = []
        
        # Непосредственный руководитель
        if trip.manager_rel:
            managers.append(trip.manager_rel)
        
        # Главный руководитель
        gr_manager = User.query.filter_by(role='GR').first()
        if gr_manager and gr_manager not in managers:
            managers.append(gr_manager)
        
        # Администраторы
        admins = User.query.filter_by(role='A').all()
        managers.extend([admin for admin in admins if admin not in managers])
        
        for manager in managers:
            print(f"УВЕДОМЛЕНИЕ руководителю {manager.full_name}: "
                  f"Сотрудник {employee.full_name} установил геопозицию: {location}")
    except Exception as e:
        print(f"Ошибка отправки уведомлений: {e}")


@app.route('/api/trip/<int:trip_id>/approve_report_overrun', methods=['POST'])
@login_required
def approve_report_overrun(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['R', 'GR']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        
        trip.report_overrun_approved = True
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/report_prepared', methods=['POST'])
@login_required
def toggle_report_prepared(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Только сотрудник может отметить отчет как подготовленный'})
        
        prepared = request.json.get('prepared', False)
        
        if prepared:
            # Проверяем заполнены ли расходы
            if not trip.actual_costs or trip.actual_costs == 0:
                return jsonify({'success': False, 'error': 'Заполните таблицу фактических расходов'})
            
            # Проверяем наличие документов
            documents_count = Document.query.filter_by(trip_id=trip_id).count()
            if documents_count == 0:
                return jsonify({'success': False, 'error': 'Необходимо прикрепить хотя бы один документ'})
        
        trip.report_prepared = prepared
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/trip/<int:trip_id>/report_reviewed', methods=['POST'])
@login_required
def toggle_report_reviewed(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['R', 'GR']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        
        reviewed = request.json.get('reviewed', False)
        
        if reviewed:
            # Проверяем наличие геолокации
            if not trip.geo_location:
                return jsonify({'success': False, 'error': 'Не установлена геолокация сотрудником'})
            
            # Проверяем наличие документов
            documents_count = Document.query.filter_by(trip_id=trip_id).count()
            if documents_count == 0:
                return jsonify({'success': False, 'error': 'Нет прикрепленных документов для проверки'})
            
            # Проверяем, что отчет подготовлен
            if not trip.report_prepared:
                return jsonify({'success': False, 'error': 'Отчет должен быть подготовлен сотрудником'})
        
        trip.report_reviewed = reviewed
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/update_booking', methods=['POST'])
@login_required
def update_booking(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        # Проверка прав доступа
        can_edit = False
        
        if user.role in ['A', 'TK']:
            can_edit = True
        elif user.role == 'S' and trip.employee_id == user.id and not trip.booking_completed:
            can_edit = True
        
        if not can_edit:
            return jsonify({'success': False, 'error': 'Недостаточно прав для редактирования бронирования'})
        
        data = request.json
        
        # Обновляем поля бронирования
        if 'transport_type' in data:
            trip.transport_type = data['transport_type']
        if 'departure_city' in data:
            trip.departure_city = data['departure_city']
        if 'arrival_city' in data:
            trip.arrival_city = data['arrival_city']
        if 'departure_date_min' in data and data['departure_date_min']:
            try:
                trip.departure_date_min = datetime.fromisoformat(data['departure_date_min'].replace('Z', '+00:00'))
            except ValueError:
                try:
                    trip.departure_date_min = datetime.strptime(data['departure_date_min'], '%Y-%m-%dT%H:%M')
                except ValueError:
                    trip.departure_date_min = None
        if 'arrival_date_max' in data and data['arrival_date_max']:
            try:
                trip.arrival_date_max = datetime.fromisoformat(data['arrival_date_max'].replace('Z', '+00:00'))
            except ValueError:
                try:
                    trip.arrival_date_max = datetime.strptime(data['arrival_date_max'], '%Y-%m-%dT%H:%M')
                except ValueError:
                    trip.arrival_date_max = None
        if 'transfer_to' in data:
            trip.transfer_to = data['transfer_to']
        if 'transport_type_return' in data:
            trip.transport_type_return = data['transport_type_return']
        if 'departure_city_return' in data:
            trip.departure_city_return = data['departure_city_return']
        if 'arrival_city_return' in data:
            trip.arrival_city_return = data['arrival_city_return']
        if 'departure_date_min_return' in data and data['departure_date_min_return']:
            try:
                trip.departure_date_min_return = datetime.fromisoformat(data['departure_date_min_return'].replace('Z', '+00:00'))
            except ValueError:
                try:
                    trip.departure_date_min_return = datetime.strptime(data['departure_date_min_return'], '%Y-%m-%dT%H:%M')
                except ValueError:
                    trip.departure_date_min_return = None
        if 'arrival_date_max_return' in data and data['arrival_date_max_return']:
            try:
                trip.arrival_date_max_return = datetime.fromisoformat(data['arrival_date_max_return'].replace('Z', '+00:00'))
            except ValueError:
                try:
                    trip.arrival_date_max_return = datetime.strptime(data['arrival_date_max_return'], '%Y-%m-%dT%H:%M')
                except ValueError:
                    trip.arrival_date_max_return = None
        if 'transfer_from' in data:
            trip.transfer_from = data['transfer_from']
        if 'hotel_name' in data:
            trip.hotel_name = data['hotel_name']
        if 'check_in' in data and data['check_in']:
            try:
                trip.check_in = datetime.fromisoformat(data['check_in'])
            except ValueError:
                try:
                    trip.check_in = datetime.strptime(data['check_in'], '%Y-%m-%d')
                except ValueError:
                    trip.check_in = None
        if 'check_out' in data and data['check_out']:
            try:
                trip.check_out = datetime.fromisoformat(data['check_out'])
            except ValueError:
                try:
                    trip.check_out = datetime.strptime(data['check_out'], '%Y-%m-%d')
                except ValueError:
                    trip.check_out = None
        if 'hotel_rooms' in data:
            trip.hotel_rooms = int(data['hotel_rooms']) if data['hotel_rooms'] else None
        if 'contact_phone' in data:
            trip.contact_phone = data['contact_phone']
        if 'booking_notes' in data:
            trip.booking_notes = data['booking_notes']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Данные бронирования обновлены',
            'booking_completed': trip.booking_completed
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/trip_closed', methods=['POST'])
@login_required
def toggle_trip_closed(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'BU']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        
        closed = request.json.get('closed', False)
        
        if closed:
            # Проверяем, что отчет проверен руководителем
            if not trip.report_reviewed:
                return jsonify({'success': False, 'error': 'Отчет должен быть проверен руководителем'})
        
        trip.trip_closed = closed
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# Управление расходами
@app.route('/api/trip/<int:trip_id>/costs', methods=['GET', 'POST', 'DELETE'])
@login_required
def manage_trip_costs(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        # Проверяем, не закрыта ли командировка
        if trip.trip_closed and request.method != 'GET':
            return jsonify({'success': False, 'error': 'Командировка закрыта. Редактирование невозможно.'})
        
        # Для POST и DELETE проверяем, что это командируемый сотрудник
        if request.method in ['POST', 'DELETE']:
            if user.role != 'S' or user.id != trip.employee_id:
                return jsonify({'success': False, 'error': 'Только командируемый сотрудник может управлять расходами'})
        
        if request.method == 'GET':
            # Получаем все расходы для командировки
            costs = TripCost.query.filter_by(trip_id=trip_id).order_by(TripCost.id).all()
            costs_list = []
            for cost in costs:
                costs_list.append({
                    'id': cost.id,
                    'category': cost.category,
                    'amount': cost.amount,
                    'comment': cost.comment
                })
            
            total_sum = sum(c.amount for c in costs) if costs else 0
            
            return jsonify({
                'success': True,
                'costs': costs_list,
                'total': total_sum
            })
        
        elif request.method == 'POST':
            # Добавляем или обновляем расход
            data = request.json
            cost_id = data.get('id')
            
            if cost_id:
                # Обновляем существующий расход
                cost = db.session.get(TripCost, cost_id)
                if not cost or cost.trip_id != trip_id:
                    return jsonify({'success': False, 'error': 'Расход не найден'})
                
                cost.category = data['category']
                cost.amount = float(data['amount'])
                cost.comment = data.get('comment', '')
            else:
                # Добавляем новый расход
                cost = TripCost(
                    trip_id=trip_id,
                    category=data['category'],
                    amount=float(data['amount']),
                    comment=data.get('comment', '')
                )
                db.session.add(cost)
            
            db.session.commit()
            
            # Обновляем общую сумму фактических расходов
            update_actual_costs(trip_id)
            
            return jsonify({'success': True, 'cost_id': cost.id})
        
        elif request.method == 'DELETE':
            # Удаляем расход
            cost_id = request.args.get('cost_id')
            if not cost_id:
                return jsonify({'success': False, 'error': 'Не указан ID расхода'})
            
            cost = db.session.get(TripCost, cost_id)
            if not cost or cost.trip_id != trip_id:
                return jsonify({'success': False, 'error': 'Расход не найден'})
            
            db.session.delete(cost)
            db.session.commit()
            
            # Обновляем общую сумму фактических расходов
            update_actual_costs(trip_id)
            
            return jsonify({'success': True})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# Функция для обновления общей суммы фактических расходов
def update_actual_costs(trip_id):
    """Обновляет общую сумму фактических расходов на основе детализации"""
    try:
        total = db.session.query(func.sum(TripCost.amount)).filter_by(trip_id=trip_id).scalar()
        trip = db.session.get(BusinessTrip, trip_id)
        if trip:
            trip.actual_costs = total or 0
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка при обновлении суммы расходов: {e}")

@app.route('/api/trip/<int:trip_id>/send_notification', methods=['POST'])
@login_required
def send_trip_notification(trip_id):
    """Отправка уведомлений о закрытии командировки"""
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        data = request.json
        message = data.get('message', '')
        roles = data.get('roles', [])
        
        if not message:
            return jsonify({'success': False, 'error': 'Не указано сообщение'})
        
        # Находим пользователей для отправки уведомлений
        users_to_notify = []
        if roles:
            users_to_notify = User.query.filter(User.role.in_(roles)).all()
        
        # Отправляем уведомления
        notification_sent = []
        for user_to_notify in users_to_notify:
            # Здесь можно реализовать отправку email, push-уведомлений, Telegram и т.д.
            # Пока просто логируем
            print(f"Уведомление для {user_to_notify.full_name} ({user_to_notify.role}): {message}")
            notification_sent.append({
                'id': user_to_notify.id,
                'name': user_to_notify.full_name,
                'role': user_to_notify.role,
                'email': user_to_notify.email
            })
        
        return jsonify({
            'success': True,
            'message': f'Уведомления отправлены {len(notification_sent)} пользователям',
            'notifications_sent': notification_sent
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
# Функция для отправки уведомлений
def send_notification_to_roles(roles, message):
    """Отправляет уведомления пользователям с указанными ролями"""
    try:
        users = User.query.filter(User.role.in_(roles)).all()
        for user in users:
            # Здесь можно реализовать отправку email, push-уведомлений и т.д.
            # Пока просто логируем
            print(f"Уведомление для {user.full_name} ({user.role}): {message}")
            
            # В реальном приложении можно использовать:
            # 1. Отправку email
            # 2. Сохранение в таблицу уведомлений в БД
            # 3. WebSocket для реальных уведомлений
            # 4. Интеграцию с Telegram/Slack и т.д.
    except Exception as e:
        print(f"Ошибка при отправке уведомлений: {e}")

# Функция для обновления общей суммы фактических расходов
def update_actual_costs(trip_id):
    try:
        total = db.session.query(db.func.sum(TripCost.amount)).filter_by(trip_id=trip_id).scalar()
        trip = db.session.get(BusinessTrip, trip_id)
        if trip:
            trip.actual_costs = total or 0
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка при обновлении суммы расходов: {e}")

# Функция для скачивания всех документов в формате архива
# Скачивание всех документов в формате архива
@app.route('/api/trip/<int:trip_id>/download_all_documents')
@login_required
def download_all_documents(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            flash('Заявка не найдена', 'error')
            return redirect(url_for('dashboard'))
            
        user = db.session.get(User, session['user_id'])
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('login'))
        
        # Проверка прав доступа
        if user.role == 'S' and trip.employee_id != user.id:
            flash('Доступ запрещен', 'error')
            return redirect(url_for('dashboard'))
        elif user.role == 'R' and trip.employee_id != user.id and trip.employee_id not in [sub.id for sub in user.subordinates]:
            flash('Доступ запрещен', 'error')
            return redirect(url_for('dashboard'))
        
        # Получаем все документы для командировки
        documents = Document.query.filter_by(trip_id=trip_id).all()
        
        if not documents:
            flash('Нет документов для скачивания', 'info')
            return redirect(url_for('trip_detail', trip_id=trip_id))
        
        # Создаем архив в памяти
        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for doc in documents:
                # Получаем полный путь к файлу
                file_path = doc.file_path.replace('/static/', '')
                full_path = os.path.join(app.root_path, file_path)
                
                if os.path.exists(full_path):
                    # Добавляем файл в архив
                    arcname = f"{doc.filename}"
                    zf.write(full_path, arcname)
        
        memory_file.seek(0)
        
        # Отправляем архив пользователю
        return send_file(
            memory_file,
            download_name=f'documents_{trip.trip_number}.zip',
            as_attachment=True,
            mimetype='application/zip'
        )
        
    except Exception as e:
        flash(f'Ошибка при создании архива: {str(e)}', 'error')
        return redirect(url_for('trip_detail', trip_id=trip_id))

# Добавляем возможность загрузки документов через сканирование (камера)
@app.route('/api/trip/<int:trip_id>/upload_from_camera', methods=['POST'])
@login_required
def upload_from_camera(trip_id):
    try:
        trip = db.session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        # Проверка прав доступа
        if user.role == 'S' and trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Вы можете загружать документы только для своих командировок'})
        elif user.role == 'R' and trip.employee_id != user.id and trip.employee_id not in [sub.id for sub in user.subordinates]:
            return jsonify({'success': False, 'error': 'Доступ запрещен'})
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'Файл не найден'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Файл не выбран'})
        
        # Принимаем изображения от камеры
        ALLOWED_CAMERA_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        
        if file and '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in ALLOWED_CAMERA_EXTENSIONS:
            # Проверяем размер файла
            file.seek(0, os.SEEK_END)
            file_length = file.tell()
            file.seek(0)
            
            if file_length > MAX_FILE_SIZE:
                return jsonify({'success': False, 'error': 'Размер файла превышает 10MB'})
            
            # Создаем уникальное имя файла
            filename = secure_filename(file.filename)
            unique_filename = f"scan_{trip_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{filename}"
            file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
            
            # Сохраняем файл
            file.save(file_path)
            
            # Создаем запись в базе данных
            document = Document(
                trip_id=trip_id,
                filename=filename,
                file_path=f"/static/uploads/{unique_filename}",
                file_type='receipt',  # По умолчанию для сканированных документов
                description=request.form.get('description', 'Сканированный документ'),
                uploaded_by_id=user.id
            )
            
            db.session.add(document)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'document': {
                    'id': document.id,
                    'filename': document.filename,
                    'file_path': document.file_path,
                    'file_type': document.file_type,
                    'description': document.description,
                    'upload_date': document.upload_date.strftime('%d.%m.%Y %H:%M'),
                    'uploaded_by': document.uploaded_by.full_name
                }
            })
        else:
            return jsonify({'success': False, 'error': 'Недопустимый формат файла. Допустимы: PNG, JPG, JPEG, GIF, WEBP'})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/trip/<int:trip_id>/toggle_flag', methods=['POST'])
@login_required
def toggle_flag(trip_id):
    
    flag = request.json.get('flag')
    trip = db.session.get(BusinessTrip, trip_id)
    if not trip:
        return jsonify({'error': 'Командировка не найдена'}), 404

    if flag == 'report_prepared':
        trip.report_prepared = True
        if not trip.actual_costs or not trip.documents:
            return jsonify({'error': 'Заполните поля расходов и прикрепите документы'}), 400
        message = f"Отчёт по командировке {trip.trip_number} подготовлен."
    elif flag == 'report_reviewed':
        trip.report_reviewed = True
        message = f"Отчёт по командировке {trip.trip_number} проверен."
    elif flag == 'trip_closed':
        trip.trip_closed = True
        message = f"Командировка {trip.trip_number} закрыта."
    else:
        return jsonify({'error': 'Неверный флаг'}), 400

    db.session.commit()

    # Уведомление
    users_to_notify = User.query.filter(User.role.in_(['A', 'B', 'GR', 'R', 'S', 'BU'])).all()
    for user in users_to_notify:
        # Здесь можно реализовать отправку email или push-уведомлений
        print(f"Уведомление для {user.full_name}: {message}")
    return jsonify({'success': True})


def init_db():
    from datetime import datetime, timedelta
    # Создаем все таблицы
    db.create_all()
    print("Таблицы базы данных созданы")

    # Создание тестовых пользователей если их нет
    if not User.query.first():
        print("Создание тестовых пользователей...")
        # Администратор
        admin = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            full_name='Администратор Системы',
            role='A',
            department='ИТ'
        )
        # Главный руководитель (CEO)
        gr_manager = User(
            username='gr_manager',
            password_hash=generate_password_hash('gr123'),
            full_name='Иванов Иван Иванович',
            role='GR',
            department='Руководство',
            passport_data='Паспорт РФ 1234 567890 выдан 01.01.2020 ОВД г. Москва',
            email='ivanov.ii@company.com'
        )
        db.session.add_all([admin, gr_manager])
        db.session.commit()

        # Руководитель отдела продаж
        sales_manager = User(
            username='sales_manager',
            password_hash=generate_password_hash('sales123'),
            full_name='Петров Петр Петрович',
            role='R',
            manager_id=gr_manager.id,
            department='Отдел продаж',
            passport_data='Паспорт РФ 2345 678901 выдан 02.02.2021 ОВД г. Санкт-Петербург',
            email='petrov.pp@sales.company.com'
        )
        # Руководитель отдела проектов
        projects_manager = User(
            username='projects_manager',
            password_hash=generate_password_hash('projects123'),
            full_name='Сидоров Сидор Сидорович',
            role='R',
            manager_id=gr_manager.id,
            department='Отдел проектов',
            passport_data='Паспорт РФ 3456 789012 выдан 03.03.2022 ОВД г. Екатеринбург',
            email='sidorov.ss@projects.company.com'
        )
        # Руководитель ИТ отдела
        it_manager = User(
            username='it_manager',
            password_hash=generate_password_hash('it123'),
            full_name='Кузнецов Кузьма Кузьмич',
            role='R',
            manager_id=gr_manager.id,
            department='ИТ',
            passport_data='Паспорт РФ 4567 890123 выдан 04.04.2023 ОВД г. Новосибирск',
            email='kuznetsov.kk@it.company.com'
        )
        # Бухгалтер
        accountant = User(
            username='accountant',
            password_hash=generate_password_hash('bu123'),
            full_name='Васильева Анна Сергеевна',
            role='BU',
            manager_id=gr_manager.id,
            department='Бухгалтерия',
            passport_data='Паспорт РФ 5678 901234 выдан 05.05.2024 ОВД г. Казань',
            email='vasilieva.as@accounting.company.com'
        )
        # Менеджер по закупкам
        procurement_manager = User(
            username='procurement_manager',
            password_hash=generate_password_hash('z123'),
            full_name='Михайлов Михаил Михайлович',
            role='Z',
            manager_id=gr_manager.id,
            department='Закупки',
            passport_data='Паспорт РФ 6789 012345 выдан 06.06.2025 ОВД г. Нижний Новгород',
            email='mikhailov.mm@procurement.company.com'
        )
        # Travel-координатор 1
        tk1 = User(
            username='tk1',
            password_hash=generate_password_hash('tk123'),
            full_name='Александрова Елена Викторовна',
            role='TK',
            manager_id=gr_manager.id,
            department='Трэвел-координация',
            passport_data='Паспорт РФ 7890 123456 выдан 07.07.2026 ОВД г. Самара',
            email='alexandrova.ev@travel.company.com'
        )
        # Travel-координатор 2
        tk2 = User(
            username='tk2',
            password_hash=generate_password_hash('tk456'),
            full_name='Николаев Николай Николаевич',
            role='TK',
            manager_id=gr_manager.id,
            department='Трэвел-координация',
            passport_data='Паспорт РФ 8901 234567 выдан 08.08.2027 ОВД г. Омск',
            email='nikolaev.nn@travel.company.com'
        )
        db.session.add_all([sales_manager, projects_manager, it_manager, accountant, procurement_manager, tk1, tk2])
        db.session.commit()

        # Сотрудники отдела продаж
        sales_emp1 = User(
            username='sales_emp1',
            password_hash=generate_password_hash('salesemp1'),
            full_name='Сергеев Сергей Сергеевич',
            role='S',
            manager_id=sales_manager.id,
            department='Отдел продаж',
            passport_data='Паспорт РФ 9012 345678 выдан 09.09.2028 ОВД г. Ростов-на-Дону',
            email='sergeev.ss@sales.company.com'
        )
        sales_emp2 = User(
            username='sales_emp2',
            password_hash=generate_password_hash('salesemp2'),
            full_name='Андреева Мария Ивановна',
            role='S',
            manager_id=sales_manager.id,
            department='Отдел продаж',
            passport_data='Паспорт РФ 0123 456789 выдан 10.10.2029 ОВД г. Уфа',
            email='andreeva.mi@sales.company.com'
        )
        sales_emp3 = User(
            username='sales_emp3',
            password_hash=generate_password_hash('salesemp3'),
            full_name='Федоров Федор Федорович',
            role='S',
            manager_id=sales_manager.id,
            department='Отдел продаж',
            passport_data='Паспорт РФ 1234 567890 выдан 11.11.2030 ОВД г. Красноярск',
            email='fedorov.ff@sales.company.com'
        )

        # Сотрудники отдела проектов
        projects_emp1 = User(
            username='projects_emp1',
            password_hash=generate_password_hash('projectsemp1'),
            full_name='Григорьев Григорий Григорьевич',
            role='S',
            manager_id=projects_manager.id,
            department='Отдел проектов',
            passport_data='Паспорт РФ 2345 678901 выдан 12.12.2031 ОВД г. Воронеж',
            email='grigorev.gg@projects.company.com'
        )
        projects_emp2 = User(
            username='projects_emp2',
            password_hash=generate_password_hash('projectsemp2'),
            full_name='Дмитриева Ольга Дмитриевна',
            role='S',
            manager_id=projects_manager.id,
            department='Отдел проектов',
            passport_data='Паспорт РФ 3456 789012 выдан 01.01.2032 ОВД г. Волгоград',
            email='dmitrieva.od@projects.company.com'
        )
        projects_emp3 = User(
            username='projects_emp3',
            password_hash=generate_password_hash('projectsemp3'),
            full_name='Егоров Егор Егорович',
            role='S',
            manager_id=projects_manager.id,
            department='Отдел проектов',
            passport_data='Паспорт РФ 4567 890123 выдан 02.02.2033 ОВД г. Пермь',
            email='egorov.ee@projects.company.com'
        )

        # ИТ сотрудники - инженеры
        it_eng1 = User(
            username='it_eng1',
            password_hash=generate_password_hash('iteng1'),
            full_name='Зайцев Захар Захарович',
            role='S',
            manager_id=it_manager.id,
            department='ИТ',
            passport_data='Паспорт РФ 5678 901234 выдан 03.03.2034 ОВД г. Челябинск',
            email='zaitsev.zz@it.company.com'
        )
        it_eng2 = User(
            username='it_eng2',
            password_hash=generate_password_hash('iteng2'),
            full_name='Иванова Светлана Петровна',
            role='S',
            manager_id=it_manager.id,
            department='ИТ',
            passport_data='Паспорт РФ 6789 012345 выдан 04.04.2035 ОВД г. Тюмень',
            email='ivanova.sp@it.company.com'
        )
        it_eng3 = User(
            username='it_eng3',
            password_hash=generate_password_hash('iteng3'),
            full_name='Ковалев Коваль Ковалев',
            role='S',
            manager_id=it_manager.id,
            department='ИТ',
            passport_data='Паспорт РФ 7890 123456 выдан 05.05.2036 ОВД г. Ижевск',
            email='kovalev.kk@it.company.com'
        )

        # ИТ сотрудники - программисты
        it_prog1 = User(
            username='it_prog1',
            password_hash=generate_password_hash('itprog1'),
            full_name='Лебедев Леонид Леонидович',
            role='S',
            manager_id=it_manager.id,
            department='ИТ',
            passport_data='Паспорт РФ 8901 234567 выдан 06.06.2037 ОВД г. Барнаул',
            email='lebedev.ll@it.company.com'
        )
        it_prog2 = User(
            username='it_prog2',
            password_hash=generate_password_hash('itprog2'),
            full_name='Морозова Анна Александровна',
            role='S',
            manager_id=it_manager.id,
            department='ИТ',
            passport_data='Паспорт РФ 9012 345678 выдан 07.07.2038 ОВД г. Владивосток',
            email='morozova.aa@it.company.com'
        )
        it_prog3 = User(
            username='it_prog3',
            password_hash=generate_password_hash('itprog3'),
            full_name='Новиков Новиков Новикович',
            role='S',
            manager_id=it_manager.id,
            department='ИТ',
            passport_data='Паспорт РФ 0123 456789 выдан 08.08.2039 ОВД г. Ярославль',
            email='novikov.nn@it.company.com'
        )

        # ИТ сотрудники - техподдержка
        it_support1 = User(
            username='it_support1',
            password_hash=generate_password_hash('itsupport1'),
            full_name='Орлов Олег Олегович',
            role='S',
            manager_id=it_manager.id,
            department='ИТ',
            passport_data='Паспорт РФ 1234 567890 выдан 09.09.2040 ОВД г. Иркутск',
            email='orlov.oo@it.company.com'
        )
        it_support2 = User(
            username='it_support2',
            password_hash=generate_password_hash('itsupport2'),
            full_name='Павлова Павла Павловна',
            role='S',
            manager_id=it_manager.id,
            department='ИТ',
            passport_data='Паспорт РФ 2345 678901 выдан 10.10.2041 ОВД г. Томск',
            email='pavlova.pp@it.company.com'
        )
        it_support3 = User(
            username='it_support3',
            password_hash=generate_password_hash('itsupport3'),
            full_name='Романов Роман Романович',
            role='S',
            manager_id=it_manager.id,
            department='ИТ',
            passport_data='Паспорт РФ 3456 789012 выдан 11.11.2042 ОВД г. Оренбург',
            email='romanov.rr@it.company.com'
        )

        # Старый тестовый руководитель и сотрудник
        old_manager = User(
            username='manager',
            password_hash=generate_password_hash('manager123'),
            full_name='Руководитель Отдела',
            role='R',
            manager_id=gr_manager.id,
            department='Отдел разработки'
        )
        old_employee = User(
            username='employee',
            password_hash=generate_password_hash('employee123'),
            full_name='Иванов Дмитрий Дмитриевич',
            role='S',
            manager_id=old_manager.id,
            department='Отдел разработки'
        )

        all_employees = [sales_emp1, sales_emp2, sales_emp3, projects_emp1, projects_emp2, projects_emp3,
                        it_eng1, it_eng2, it_eng3, it_prog1, it_prog2, it_prog3,
                        it_support1, it_support2, it_support3, old_manager, old_employee]
        db.session.add_all(all_employees)
        db.session.commit()
        print("Тестовые пользователи созданы")

    else:
        print("Тестовые пользователи уже существуют. Пропускаем создание.")

    # Создание тестовых командировок
    employee = User.query.filter_by(username='employee').first()
    if not employee:
        employee = User.query.filter_by(role='S').first()
    if not employee:
        print("Предупреждение: Не найден ни один сотрудник. Пропуск создания тестовых командировок.")
        return

    manager = User.query.filter_by(username='manager').first()
    if not manager:
        manager = User.query.filter(User.role.in_(['R', 'GR'])).first()
    if not manager:
        print("Предупреждение: Не найден ни один руководитель. Пропуск создания тестовых командировок.")
        return

    print("Создание дополнительных тестовых заявок...")

    base_date = datetime(2025, 1, 1)
    destinations = ['Москва', 'Санкт-Петербург', 'Новосибирск', 'Екатеринбург', 'Казань']
    purposes = ['Участие в конференции', 'Обучение', 'Консультации', 'Переговоры', 'Аудит']

    # Проверим, есть ли уже тестовые заявки с префиксом BT-2025, чтобы не дублировать
    existing_trips = BusinessTrip.query.filter(BusinessTrip.trip_number.like('BT-2025%')).count()
    if existing_trips > 0:
        print(f"Найдено {existing_trips} существующих тестовых заявок. Пропуск создания новых.")
        return

    for i in range(50): # Увеличим количество тестовых заявок до 50
        start_date = base_date + timedelta(days=i*3)
        end_date = start_date + timedelta(days=2)
        trip_number = f"BT-2025{i+1:04d}"

        # Примерно 1/5 заявок будут иметь какой-то согласованный перерасход
        overrun_approved = True if i % 5 == 0 else False
        booking_overrun_approved = True if i % 5 == 1 else False
        report_overrun_approved = True if i % 5 == 2 else False

        # Примерно половина заявок будет активирована
        is_activated = True if i % 2 == 0 else False
        status = 'Активированная' if is_activated else 'Планируемая'
        if i % 7 == 0:
            status = 'Согласована'
        elif i % 7 == 1:
            status = 'Ожидают согласования'
        elif i % 7 == 2:
            status = 'Отменена'
        elif i % 7 == 3:
            status = 'Не согласована'
        elif i % 7 == 4:
            status = 'Закрыта'

        trip = BusinessTrip(
            trip_number=trip_number,
            employee_id=employee.id,
            manager_id=manager.id,
            department='Отдел разработки',
            start_date=start_date,
            end_date=end_date,
            duration=3,
            destination=destinations[i % len(destinations)],
            purpose=purposes[i % len(purposes)],
            estimated_costs=10000.0 + (i * 500),
            actual_costs=None,
            status=status,
            is_activated=is_activated,
            over_limit = (i % 4 == 0),
            overrun_approved=overrun_approved,
            booking_overrun_approved=booking_overrun_approved,
            report_overrun_approved=report_overrun_approved,
            trip_closed=(status == 'Закрыта')
        )
        db.session.add(trip)

    db.session.commit()
    print(f"Создано {50} тестовых командировок")


# Инициализация при запуске приложения
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True)