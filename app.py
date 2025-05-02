from flask import Flask, request, render_template, redirect, url_for, session, flash, Response
import firebase_admin
from firebase_admin import credentials, auth, firestore
from firebase_admin.exceptions import FirebaseError
from datetime import datetime
from slugify import slugify
from collections import defaultdict
import csv
from io import StringIO

app = Flask(__name__)
app.secret_key = ''  #Rotation period 30 days

# Initialize Firebase Admin SDK
cred = credentials.Certificate('')
try:
    firebase_admin.initialize_app(cred)
except Exception as e:
    print(f"Error initializing Firebase: {e}")

db = firestore.client()  # Initialize Firestore client

#Crear ruta para testear la app
@app.route('/')
def index():
    return "Welcome to myPresupuestoApp!"

#Route to redirect to the register form
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            user = auth.create_user(
                email=email,
                password=password
            )
            print(f'Successfully created new user: {user.uid}')
            # Redirect to login page after successful registration
            #return redirect(url_for('login'))
        except auth.EmailAlreadyExistsError:
            error = 'Email address is already in use.'
            return render_template('registro.html', error=error)
        except auth.InvalidEmailError:
            error = 'Invalid email address.'
            return render_template('registro.html', error=error)
        except auth.WeakPasswordError:
            error = 'Password should be at least 6 characters.'
            return render_template('registro.html', error=error)
        except Exception as e:
            error = f'An error occurred: {e}'
            return render_template('registro.html', error=error)
    return render_template('registro.html')

#Route to redirect to the login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        id_token = request.form.get('idToken')  # Expecting the ID token from the frontend
        if id_token:
            try:
                decoded_token = auth.verify_id_token(id_token)
                uid = decoded_token['uid']
                session['uid'] = uid  # Store the Firebase UID in the session
                return redirect(url_for('dashboard'))
            except auth.InvalidIdTokenError:
                error = 'Invalid ID Token.'
            except Exception as e:
                error = f'An unexpected error occurred: {e}'
            return render_template('login.html', error=error)
        else:
            error = 'No ID Token provided.'
            return render_template('login.html', error=error)
    return render_template('login.html')

#Route to redirecto to the dashboard for logged in users
@app.route('/dashboard')
def dashboard():
    if 'uid' in session:
        user_id = session['uid']
        expenses_ref = db.collection('expenses')
        query = expenses_ref.where('user_id', '==', user_id)

        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        selected_category = request.args.get('category')

        # Aplicar filtros a la consulta (como antes)
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                query = query.where('date', '>=', start_date.strftime('%Y-%m-%d'))
            except ValueError:
                pass

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                query = query.where('date', '<=', end_date.strftime('%Y-%m-%d'))
            except ValueError:
                pass

        if selected_category:
            query = query.where('category', '==', selected_category)

        query = query.order_by('date', direction=firestore.Query.DESCENDING)
        expenses_stream = query.stream()
        expenses_list = []
        for expense in expenses_stream:
            expense_dict = expense.to_dict()
            expense_dict['id'] = expense.id
            expenses_list.append(expense_dict)

        # Calcular totales de gasto por categoría (aplicando los mismos filtros)
        category_totals = {}
        expenses_query_for_totals = expenses_ref.where('user_id', '==', user_id)
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                expenses_query_for_totals = expenses_query_for_totals.where('date', '>=', start_date.strftime('%Y-%m-%d'))
            except ValueError:
                pass
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                expenses_query_for_totals = expenses_query_for_totals.where('date', '<=', end_date.strftime('%Y-%m-%d'))
            except ValueError:
                pass
        if selected_category:
            expenses_query_for_totals = expenses_query_for_totals.where('category', '==', selected_category)

        expenses_stream_for_totals = expenses_query_for_totals.stream()
        for expense in expenses_stream_for_totals:
            expense_data = expense.to_dict()
            category = expense_data.get('category')
            amount = expense_data.get('amount', 0)
            if category in category_totals:
                category_totals[category] += amount
            else:
                category_totals[category] = amount

        # Calcular totales de gasto por mes (aplicando los mismos filtros)
        monthly_totals = {}
        expenses_query_for_monthly = expenses_ref.where('user_id', '==', user_id)
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                expenses_query_for_monthly = expenses_query_for_monthly.where('date', '>=', start_date.strftime('%Y-%m-%d'))
            except ValueError:
                pass
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                expenses_query_for_monthly = expenses_query_for_monthly.where('date', '<=', end_date.strftime('%Y-%m-%d'))
            except ValueError:
                pass
        if selected_category:
            expenses_query_for_monthly = expenses_query_for_monthly.where('category', '==', selected_category)

        expenses_stream_for_monthly = expenses_query_for_monthly.stream()
        for expense in expenses_stream_for_monthly:
            expense_data = expense.to_dict()
            date_obj = datetime.strptime(expense_data.get('date'), '%Y-%m-%d')
            month_year = date_obj.strftime('%Y-%m')
            amount = expense_data.get('amount', 0)
            if month_year in monthly_totals:
                monthly_totals[month_year] += amount
            else:
                monthly_totals[month_year] = amount

        # Ordenar los totales mensuales por mes
        sorted_monthly_totals = dict(sorted(monthly_totals.items()))

        return render_template('dashboard.html', expenses=expenses_list, category_totals=category_totals, start_date=start_date_str, end_date=end_date_str, selected_category=selected_category, monthly_totals=sorted_monthly_totals, datetime=datetime)
    return redirect(url_for('login'))

@app.route('/categories')
def categories():
    if 'uid' not in session:
        return redirect(url_for('login'))

    user_id = session['uid']
    user_categories_ref = db.collection('user_categories').document(user_id)
    user_categories_doc = user_categories_ref.get()
    user_categories = user_categories_doc.to_dict().get('categories', []) if user_categories_doc.exists else []

    return render_template('categories.html', user_categories=user_categories)

@app.route('/categories/add', methods=['POST'])
def add_category():
    if 'uid' not in session:
        return redirect(url_for('login'))

    user_id = session['uid']
    new_category = request.form.get('new_category')

    if new_category:
        user_categories_ref = db.collection('user_categories').document(user_id)
        user_categories_doc = user_categories_ref.get()

        if user_categories_doc.exists:
            user_categories = user_categories_doc.to_dict().get('categories', [])
            if new_category not in user_categories:
                user_categories.append(new_category)
                user_categories_ref.update({'categories': user_categories})
                print(f"Categoría '{new_category}' agregada por el usuario {user_id}")
        else:
            user_categories_ref.set({'categories': [new_category]})
            print(f"Primera categoría '{new_category}' agregada por el usuario {user_id}")

    return redirect(url_for('categories'))

@app.route('/add_expense', methods=['GET', 'POST'])
def add_expense():
    if 'uid' not in session:
        return redirect(url_for('login'))

    user_id = session['uid']
    user_categories_ref = db.collection('user_categories').document(user_id)
    user_categories_doc = user_categories_ref.get()
    custom_categories = user_categories_doc.to_dict().get('categories', []) if user_categories_doc.exists else []

    default_categories = [
        "Mercado",
        "Transporte",
        "Entretenimiento",
        "Servicios",
        "Vivienda",
        "Salud",
        "Otro"
    ]
    all_categories = default_categories + custom_categories

    if request.method == 'POST':
        date = request.form['date']
        description = request.form['description']
        category = request.form['category']
        amount = float(request.form['amount'])
        payment_method = request.form.get('payment_method') # Obtener el método de pago

        db.collection('expenses').add({
            'user_id': user_id,
            'date': date,
            'description': description,
            'category': category,
            'amount': amount,
            'timestamp': firestore.SERVER_TIMESTAMP,
            'payment_method': payment_method # Guardar el método de pago
        })
        return redirect(url_for('dashboard'))
    return render_template('add_expense.html', categories=all_categories)

@app.route('/delete_expense', methods=['POST'])
def delete_expense():
    if 'uid' not in session:
        return redirect(url_for('login'))

    expense_id = request.form.get('expense_id')
    user_id = session['uid']

    if expense_id:
        expense_ref = db.collection('expenses').document(expense_id)
        expense_doc = expense_ref.get()

        if expense_doc.exists:
            if expense_doc.to_dict().get('user_id') == user_id:
                expense_ref.delete()
                print(f"Gasto con ID {expense_id} eliminado por el usuario {user_id}")
            else:
                print(f"Usuario {user_id} intentó eliminar el gasto con ID {expense_id} que no le pertenece.")
                # Considera mostrar un mensaje de error al usuario si lo deseas
        else:
            print(f"No se encontró el gasto con ID {expense_id}.")
            # Considera mostrar un mensaje de error al usuario si lo deseas

    return redirect(url_for('dashboard'))

@app.route('/edit_expense/<expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    if 'uid' not in session:
        return redirect(url_for('login'))

    user_id = session['uid']
    expense_ref = db.collection('expenses').document(expense_id)
    expense = expense_ref.get().to_dict()
    if expense is None or expense['user_id'] != user_id:
        return redirect(url_for('dashboard'))

    user_categories_ref = db.collection('user_categories').document(user_id)
    user_categories_doc = user_categories_ref.get()
    custom_categories = user_categories_doc.to_dict().get('categories', []) if user_categories_doc.exists else []
    default_categories = [
        "Mercado",
        "Transporte",
        "Entretenimiento",
        "Servicios",
        "Vivienda",
        "Salud",
        "Otro"
    ]
    all_categories = default_categories + custom_categories

    if request.method == 'POST':
        date = request.form['date']
        description = request.form['description']
        category = request.form['category']
        amount = float(request.form['amount'])
        payment_method = request.form.get('payment_method') # Obtener el método de pago

        expense_ref.update({
            'date': date,
            'description': description,
            'category': category,
            'amount': amount,
            'payment_method': payment_method # Actualizar el método de pago
        })
        return redirect(url_for('dashboard'))

    return render_template('edit_expense.html', expense=expense, categories=all_categories)

@app.route('/reports', methods=['GET', 'POST'])
def reports():
    if 'uid' not in session:
        return redirect(url_for('login'))

    user_id = session['uid']
    user_categories_ref = db.collection('user_categories').document(user_id)
    user_categories_doc = user_categories_ref.get()
    custom_categories = user_categories_doc.to_dict().get('categories', []) if user_categories_doc.exists else []
    default_categories = [
        "Mercado",
        "Transporte",
        "Entretenimiento",
        "Servicios",
        "Vivienda",
        "Salud",
        "Otro"
    ]
    all_categories = default_categories + custom_categories

    if request.method == 'POST':
        start_date_str = request.form['start_date']
        end_date_str = request.form['end_date']
        selected_categories = request.form.getlist('categories')
        group_by = request.form.get('group_by')

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Formato de fecha inválido.', 'error')
            return redirect(url_for('reports'))

        expenses_ref = db.collection('expenses').where('user_id', '==', user_id)
        query = expenses_ref.where('date', '>=', start_date.strftime('%Y-%m-%d')).where('date', '<=', end_date.strftime('%Y-%m-%d'))

        if selected_categories and selected_categories[0] != '':
            query = query.where('category', 'in', selected_categories)

        expenses = query.order_by('date').stream()
        report_data = []
        for expense in expenses:
            report_data.append(expense.to_dict())

        grouped_report = defaultdict(list)
        total_spent = 0

        if group_by == 'category':
            for item in report_data:
                grouped_report[item['category']].append(item)
                total_spent += item['amount']
        elif group_by == 'payment_method':
            for item in report_data:
                payment = item.get('payment_method', 'No Especificado')
                grouped_report[payment].append(item)
                total_spent += item['amount']
        else:
            total_spent = sum(item['amount'] for item in report_data)
            return render_template('report.html', report_data=report_data, start_date=start_date_str, end_date=end_date_str, total_spent=total_spent, grouped_by=None)

        grouped_total = {}
        overall_total = 0
        for group, items in grouped_report.items():
            group_total = sum(item['amount'] for item in items)
            grouped_total[group] = group_total
            overall_total += group_total

        return render_template('report.html', grouped_report=grouped_report, start_date=start_date_str, end_date=end_date_str, total_spent=overall_total, grouped_by=group_by, grouped_total=grouped_total)

    return render_template('reports.html', all_categories=all_categories)

@app.route('/budgets', methods=['GET', 'POST'])
def budgets():
    if 'uid' not in session:
        return redirect(url_for('login'))

    user_id = session['uid']
    user_categories_ref = db.collection('user_categories').document(user_id)
    user_categories_doc = user_categories_ref.get()
    custom_categories = user_categories_doc.to_dict().get('categories', []) if user_categories_doc.exists else []

    default_categories = [
        "Mercado",
        "Transporte",
        "Entretenimiento",
        "Servicios",
        "Vivienda",
        "Salud",
        "Otro"
    ]
    all_categories = default_categories + custom_categories

    budgets_ref = db.collection('budgets').where('user_id', '==', user_id)
    budgets_docs = budgets_ref.stream()
    user_budgets = {}
    for budget in budgets_docs:
        user_budgets[budget.to_dict()['category']] = budget.to_dict()['limit']

    if request.method == 'POST':
        for category in all_categories:
            limit = request.form.get(category)
            if limit is not None and limit != '':
                limit = float(limit)
                budget_ref = db.collection('budgets')
                # Buscar si ya existe un límite para esta categoría
                query = budget_ref.where('user_id', '==', user_id).where('category', '==', category).limit(1)
                existing_budget = next(query.stream(), None)
                if existing_budget:
                    existing_budget.reference.update({'limit': limit, 'timestamp': firestore.SERVER_TIMESTAMP})
                    print(f"Presupuesto actualizado para {category} a {limit} por el usuario {user_id}")
                else:
                    budget_ref.add({
                        'user_id': user_id,
                        'category': category,
                        'limit': limit,
                        'timestamp': firestore.SERVER_TIMESTAMP
                    })
                    print(f"Presupuesto establecido para {category} a {limit} por el usuario {user_id}")
            else:
                # Si el campo está vacío, podríamos eliminar el presupuesto existente para esa categoría
                query = budget_ref.where('user_id', '==', user_id).where('category', '==', category).limit(1)
                existing_budget = next(query.stream(), None)
                if existing_budget:
                    existing_budget.reference.delete()
                    print(f"Presupuesto eliminado para {category} por el usuario {user_id}")

        return redirect(url_for('budgets'))

    return render_template('budgets.html', categories=all_categories, budgets=user_budgets)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'uid' not in session:
        return redirect(url_for('login'))

    user_id = session['uid']
    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()
    display_name = user_doc.to_dict().get('displayName') if user_doc.exists else None

    if request.method == 'POST':
        new_display_name = request.form.get('displayName')
        user_ref.set({'displayName': new_display_name}, merge=True)
        print(f"Perfil del usuario {user_id} actualizado. Nombre para mostrar: {new_display_name}")
        return redirect(url_for('profile'))  # Redirigir de vuelta al perfil para ver los cambios
    else:
        return render_template('profile.html', display_name=display_name)

@app.route('/categories/edit/<category_name>', methods=['GET', 'POST'])
def edit_category(category_name):
    if 'uid' not in session:
        return redirect(url_for('login'))

    user_id = session['uid']
    user_categories_ref = db.collection('user_categories').document(user_id)
    user_categories_doc = user_categories_ref.get()

    if not user_categories_doc.exists or 'categories' not in user_categories_doc.to_dict():
        return redirect(url_for('categories'))

    user_categories = user_categories_doc.to_dict()['categories']

    if request.method == 'POST':
        original_category_name = request.form.get('original_category_name')
        new_category_name = request.form.get('new_category_name')

        if original_category_name in user_categories:
            index = user_categories.index(original_category_name)
            user_categories[index] = new_category_name
            user_categories_ref.update({'categories': user_categories})
            print(f"Categoría '{original_category_name}' editada a '{new_category_name}' por el usuario {user_id}")
            # También deberíamos actualizar los gastos existentes con esta categoría (lo haremos en un paso posterior si es necesario)
            return redirect(url_for('categories'))
        else:
            # La categoría original no se encontró (esto no debería pasar si la interfaz funciona correctamente)
            return redirect(url_for('categories'))
    else:
        return render_template('edit_category.html', category_name=category_name)

@app.route('/categories/delete/<category_name>', methods=['POST'])
def delete_category(category_name):
    if 'uid' not in session:
        return redirect(url_for('login'))

    user_id = session['uid']
    user_categories_ref = db.collection('user_categories').document(user_id)
    user_categories_doc = user_categories_ref.get()

    if user_categories_doc.exists and 'categories' in user_categories_doc.to_dict():
        user_categories = user_categories_doc.to_dict()['categories']
        if category_name in user_categories:
            user_categories.remove(category_name)
            user_categories_ref.update({'categories': user_categories})
            print(f"Categoría '{category_name}' eliminada por el usuario {user_id}")

            # Actualizar los gastos existentes que tienen esta categoría a "Otro"
            expenses_ref = db.collection('expenses')
            query = expenses_ref.where('user_id', '==', user_id).where('category', '==', category_name)
            expenses_to_update = query.stream()
            for expense in expenses_to_update:
                expense.reference.update({'category': 'Otro'})
                print(f"Gasto con ID {expense.id} actualizado a la categoría 'Otro' debido a la eliminación de la categoría '{category_name}'.")

    return redirect(url_for('categories'))

@app.route('/export_report')
def export_report():
    if 'uid' not in session:
        return redirect(url_for('login'))

    user_id = session['uid']
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    selected_categories = request.args.getlist('categories')
    group_by = request.args.get('group_by')

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        flash('Formato de fecha inválido para la exportación.', 'error')
        return redirect(url_for('reports'))

    expenses_ref = db.collection('expenses').where('user_id', '==', user_id)
    query = expenses_ref.where('date', '>=', start_date.strftime('%Y-%m-%d')).where('date', '<=', end_date.strftime('%Y-%m-%d'))

    if selected_categories and selected_categories[0] != '':
        query = query.where('category', 'in', selected_categories)

    expenses = query.order_by('date').stream()
    report_data = [expense.to_dict() for expense in expenses]

    si = StringIO()
    writer = csv.writer(si)

    writer.writerow(['Fecha', 'Descripción', 'Categoría', 'Monto (COP)', 'Método de Pago']) # Escribir encabezado

    if group_by:
        writer.writerow([f'Agrupado por: {group_by.capitalize()}'])
        grouped_report = defaultdict(list)
        for item in report_data:
            key = item.get(group_by, 'Sin Agrupar')
            grouped_report[key].append(item)

        for group, items in grouped_report.items():
            writer.writerow([group])
            for item in items:
                writer.writerow([item['date'], item['description'], item['category'], item['amount'], item.get('payment_method', '')])
            writer.writerow([]) # Línea en blanco entre grupos
    else:
        for item in report_data:
            writer.writerow([item['date'], item['description'], item['category'], item['amount'], item.get('payment_method', '')])

    output = si.getvalue()

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=reporte_gastos_{start_date_str}_a_{end_date_str}.csv"}
    )

#Route to log out
@app.route('/logout')
def logout():
    session.pop('uid', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
