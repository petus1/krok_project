from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from dotenv import load_dotenv
import secrets

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL is None:
    raise ValueError("Не установлена переменная окружения DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

db_session = db.session

# Модели базы данных
class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # A, B (Безопасность), BU (Бухгалтерия), GR, R, S, K, TK, Z
    manager_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    passport_data = db.Column(db.Text)
    department = db.Column(db.String(100))

    manager = db.relationship('User', remote_side=[id], backref='subordinates')
    created_trips = db.relationship('BusinessTrip', backref='employee', foreign_keys='BusinessTrip.employee_id')
    managed_trips = db.relationship('BusinessTrip', backref='manager_rel', foreign_keys='BusinessTrip.manager_id')
    email = db.Column(db.String(100))  # Email для уведомлений


class BusinessTrip(db.Model):
    __tablename__ = 'business_trip'
    id = db.Column(db.Integer, primary_key=True)
    trip_number = db.Column(db.String(20), unique=True)
    created_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(50), default='Планируемая')

    # Основная информация
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    manager_id = db.Column(db.Integer, db.ForeignKey('user.id'))
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
    cost_details = db.Column(db.Text)
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
    booking_overrun_approved = db.Column(db.Boolean, default=False)  # Перерасход по бронированию согласован

    # Отчет
    geo_location = db.Column(db.String(200))
    geo_location_date = db.Column(db.DateTime)  # Дата установки геолокации
    report_prepared = db.Column(db.Boolean, default=False)
    report_reviewed = db.Column(db.Boolean, default=False)
    trip_closed = db.Column(db.Boolean, default=False)
    report_overrun_approved = db.Column(db.Boolean, default=False)  # Перерасход в отчете согласован

    # Закупки
    procurement_needed = db.Column(db.Boolean, default=False)
    procurement_done = db.Column(db.Boolean, default=False)
    procurement_costs = db.Column(db.Float)
    procurement_details = db.Column(db.Text)  # Детализация задания к закупке
    procurement_report = db.Column(db.Text)  # Отчет по закупке материалов


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
            # Используем современный синтаксис
            user = db_session.get(User, session['user_id'])
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
                    db_session.commit()


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

    # Используем современный синтаксис
    user = db_session.get(User, session['user_id'])
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
    
    # Используем современный синтаксис
    user = db_session.get(User, session['user_id'])
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
            # Используем современный синтаксис
            user = db_session.get(User, session['user_id'])
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

            # Используем современный синтаксис
            employee = db_session.get(User, employee_id)
            if not employee:
                flash('Сотрудник не найден', 'error')
                return redirect(url_for('create_trip'))

            # Остальная логика создания заявки...
            start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
            end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
            duration = (end_date - start_date).days + 1

            # --- НОВАЯ ЛОГИКА ---
            make_active = request.form.get('make_active') == 'on'

            # Определяем статус и активацию
            initial_status = 'Активированная' if make_active else 'Планируемая'
            is_activated_value = make_active # True если активировать, False если нет

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
                cost_details=request.form.get('cost_details', ''),
                trip_format=request.form.get('trip_format', ''),
                project_number=request.form.get('project_number', ''),
                regularity=request.form.get('regularity', ''),
                receiving_party=request.form.get('receiving_party', ''),
                over_limit=request.form.get('over_limit') == 'on',
                status=initial_status,
                is_activated=is_activated_value # Устанавливаем флаг активации
            )
            db_session.add(trip)
            db_session.commit()
            flash('Заявка на командировку создана', 'success')
            return redirect(url_for('trips'))
        except Exception as e:
            db_session.rollback()
            flash(f'Ошибка при создании заявки: {str(e)}', 'error')

    # Используем современный синтаксис
    user = db_session.get(User, session['user_id'])
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

    # Используем современный синтаксис
    user = db_session.get(User, session['user_id'])
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

    # Используем современный синтаксис
    trip = db_session.get(BusinessTrip, trip_id)
    if not trip:
        flash('Заявка не найдена', 'error')
        return redirect(url_for('dashboard'))

    user = db_session.get(User, session['user_id'])
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
    # Используем современный синтаксис
    user = db_session.get(User, session['user_id'])
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
        # Сортируем по перерасходу (фактические - предполагаемые)
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

    # Данные для графиков - обеспечиваем, что они никогда не будут пустыми
    status_counts = defaultdict(int)
    monthly_costs = defaultdict(float)
    monthly_actual = defaultdict(float)
    department_costs = defaultdict(float)

    for trip in trips:
        status_counts[trip.status] += 1
        if trip.start_date:
            month_key = trip.start_date.strftime('%Y-%m')
            monthly_costs[month_key] += trip.estimated_costs or 0
            monthly_actual[month_key] += trip.actual_costs or 0
        if trip.department:
            department_costs[trip.department] += trip.estimated_costs or 0

    # Если нет данных, создаем заглушки для графиков
    if not status_counts:
        status_counts = {'Нет данных': 1}
    if not monthly_costs:
        monthly_costs = {datetime.now(timezone.utc).strftime('%Y-%m'): 0}
        monthly_actual = {datetime.now(timezone.utc).strftime('%Y-%m'): 0}
    if not department_costs:
        department_costs = {'Нет данных': 0}

    return render_template('reports.html', user=user, trips=trips,
                           total_trips=total_trips, total_costs=total_costs,
                           total_actual_costs=total_actual_costs, overrun_trips=len(overrun_trips),
                           overrun_amount=overrun_amount,
                           status_counts=dict(status_counts),
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
    # Используем современный синтаксис
    user = db_session.get(User, session['user_id'])
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('login'))

    # Запланированные командировки с учетом ролей
    base_query = BusinessTrip.query.filter_by(status='Планируемая')

    if user.role == 'A' or user.role == 'B' or user.role == 'BU' or user.role == 'GR':
        planned_trips = base_query.all()
    elif user.role == 'R':
        # Руководитель видит свои заявки и заявки подчиненных
        subordinate_ids = [sub.id for sub in user.subordinates]
        planned_trips = base_query.filter(
            (BusinessTrip.employee_id == user.id) |
            (BusinessTrip.employee_id.in_(subordinate_ids))
        ).all()
    elif user.role == 'S':
        # Сотрудник видит только свои заявки
        planned_trips = base_query.filter_by(employee_id=user.id).all()
    else:
        planned_trips = base_query.all()

    return render_template('planning.html', user=user, trips=planned_trips)


@app.route('/employees')
@login_required
@role_required(['A', 'B'])  # Только Администратор и Отдел безопасности
def employees():
    # Используем современный синтаксис
    user = db_session.get(User, session['user_id'])
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('login'))

    employees_list = User.query.all()
    managers = User.query.filter(User.role.in_(['R', 'GR'])).all()
    return render_template('employees.html', user=user, employees=employees_list, managers=managers)


@app.route('/employees/create', methods=['GET', 'POST'])
@login_required
@role_required(['A'])  # Только Администратор может создавать
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
            db_session.add(employee)
            db_session.commit()
            flash('Сотрудник успешно создан', 'success')
            return redirect(url_for('employees'))
        except Exception as e:
            db_session.rollback()
            flash(f'Ошибка при создании сотрудника: {str(e)}', 'error')

    managers = User.query.filter(User.role.in_(['R', 'GR'])).all()
    return render_template('employee_form.html', user=None, managers=managers,
                           roles=['A', 'B', 'BU', 'GR', 'R', 'S', 'K', 'TK', 'Z'])


@app.route('/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['A'])  # Только Администратор может редактировать
def edit_employee(employee_id):
    # Используем современный синтаксис
    employee = db_session.get(User, employee_id)
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

            db_session.commit()
            flash('Сотрудник успешно обновлен', 'success')
            return redirect(url_for('employees'))
        except Exception as e:
            db_session.rollback()
            flash(f'Ошибка при обновлении сотрудника: {str(e)}', 'error')

    managers = User.query.filter(User.role.in_(['R', 'GR'])).all()
    return render_template('employee_form.html', user=employee, managers=managers,
                           roles=['A', 'B', 'BU', 'GR', 'R', 'S', 'K', 'TK', 'Z'])


@app.route('/employees/<int:employee_id>/delete', methods=['POST'])
@login_required
@role_required(['A'])  # Только Администратор может удалять
def delete_employee(employee_id):
    # Используем современный синтаксис
    employee = db_session.get(User, employee_id)
    if not employee:
        flash('Сотрудник не найден', 'error')
        return redirect(url_for('employees'))
        
    if employee.id == session['user_id']:
        flash('Нельзя удалить самого себя', 'error')
        return redirect(url_for('employees'))

    try:
        db_session.delete(employee)
        db_session.commit()
        flash('Сотрудник успешно удален', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Ошибка при удалении сотрудника: {str(e)}', 'error')

    return redirect(url_for('employees'))


# API endpoints для AJAX операций
@app.route('/api/update_trip_status/<int:trip_id>', methods=['POST'])
@login_required
def update_trip_status(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})

        new_status = request.json.get('status')
        if new_status:
            trip.status = new_status
            db_session.commit()
            return jsonify({'success': True, 'new_status': new_status})

        return jsonify({'success': False})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/activate', methods=['POST'])
@login_required
def activate_trip(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'GR', 'R'] and trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.is_activated = True
        trip.status = 'Активированная'
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/send_for_approval', methods=['POST'])
@login_required
def send_for_approval(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'GR', 'R'] and trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.status = 'Ожидают согласования'
        trip.approval_request_date = datetime.now(timezone.utc)
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/deactivate', methods=['POST'])
@login_required
def deactivate_trip(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'GR', 'R'] and trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.is_activated = False
        trip.status = 'Планируемая'
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/reject', methods=['POST'])
@login_required
def reject_trip(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['R', 'GR']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.status = 'Не согласована'
        trip.cancellation_reason = request.json.get('reason', '')
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/cancel', methods=['POST'])
@login_required
def cancel_trip(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'GR', 'R'] and trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.status = 'Отменена'
        trip.cancellation_reason = request.json.get('reason', '')
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/approve_overrun', methods=['POST'])
@login_required
def approve_overrun(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['R', 'GR']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.overrun_approved = True
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/approve_booking_overrun', methods=['POST'])
@login_required
def approve_booking_overrun(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'TK']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.booking_overrun_approved = True
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/complete_booking', methods=['POST'])
@login_required
def complete_booking(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'TK']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.booking_completed = True
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/procurement', methods=['POST'])
@login_required
def toggle_procurement(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'Z']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.procurement_needed = request.json.get('needed', False)
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/procurement_done', methods=['POST'])
@login_required
def toggle_procurement_done(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'Z']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.procurement_done = request.json.get('done', False)
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/geo_location', methods=['POST'])
@login_required
def set_geo_location(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Только сотрудник может установить геолокацию'})
        trip.geo_location = request.json.get('location', '')
        trip.geo_location_date = datetime.now(timezone.utc)
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/approve_report_overrun', methods=['POST'])
@login_required
def approve_report_overrun(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['R', 'GR']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.report_overrun_approved = True
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/report_prepared', methods=['POST'])
@login_required
def toggle_report_prepared(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if trip.employee_id != user.id:
            return jsonify({'success': False, 'error': 'Только сотрудник может отметить отчет как подготовленный'})
        trip.report_prepared = request.json.get('prepared', False)
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/report_reviewed', methods=['POST'])
@login_required
def toggle_report_reviewed(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['R', 'GR']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.report_reviewed = request.json.get('reviewed', False)
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trip/<int:trip_id>/trip_closed', methods=['POST'])
@login_required
def toggle_trip_closed(trip_id):
    try:
        # Используем современный синтаксис
        trip = db_session.get(BusinessTrip, trip_id)
        if not trip:
            return jsonify({'success': False, 'error': 'Заявка не найдена'})
            
        user = db_session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        if user.role not in ['A', 'BU']:
            return jsonify({'success': False, 'error': 'Недостаточно прав'})
        trip.trip_closed = request.json.get('closed', False)
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)})


# Инициализация базы данных с тестовыми данными
def init_db():
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

        # Главный руководитель
        gr_manager = User(
            username='gr_manager',
            password_hash=generate_password_hash('gr123'),
            full_name='Главный Руководитель',
            role='GR',
            department='Руководство'
        )

        db_session.add_all([admin, gr_manager])
        db_session.commit()

        # Руководитель
        manager = User(
            username='manager',
            password_hash=generate_password_hash('manager123'),
            full_name='Руководитель Отдела',
            role='R',
            manager_id=gr_manager.id,
            department='Отдел разработки'
        )

        # Сотрудник
        employee = User(
            username='employee',
            password_hash=generate_password_hash('employee123'),
            full_name='Сотрудник Тестовый',
            role='S',
            manager_id=manager.id,
            department='Отдел разработки'
        )

        db_session.add_all([manager, employee])
        db_session.commit()
        print("Тестовые пользователи созданы")

        # Создаем тестовую командировку
        trip = BusinessTrip(
            trip_number="BT-20250101-0001",
            employee_id=employee.id,
            manager_id=manager.id,
            department='Отдел разработки',
            start_date=datetime(2025, 1, 15),
            end_date=datetime(2025, 1, 20),
            duration=6,
            destination='Москва',
            purpose='Участие в конференции',
            estimated_costs=15000.0,
            status='Планируемая'
        )

        db_session.add(trip)
        db_session.commit()
        print("Тестовая командировка создана")


# Инициализация при запуске приложения
with app.app_context():
    db.drop_all()
    init_db()

if __name__ == '__main__':
    app.run(debug=True)