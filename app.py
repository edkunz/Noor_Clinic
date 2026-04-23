from flask import Flask, render_template, request, jsonify
from sqlalchemy import create_engine, text, Column, Integer, String, Boolean, DateTime, Date, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func
import os
from dotenv import load_dotenv
import plotly
import plotly.graph_objects as go
import json
import math
from datetime import datetime
from collections import defaultdict

load_dotenv()

app = Flask(__name__)

# Database configuration
DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'sqlite:///noor_clinic.db'
)

engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)

# Define database models
Base = declarative_base()

class Patient(Base):
    __tablename__ = 'patients'
    
    patient_id = Column(Integer, primary_key=True, autoincrement=True)
    patient_identifier = Column(String(50), unique=True, nullable=False)
    sex = Column(String(10))
    age_at_registration = Column(Integer)
    city = Column(String(100))
    state = Column(String(2))
    postal_code = Column(String(10))
    most_recent_visit_date = Column(Date)
    active = Column(Boolean, default=True)
    fake = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationship
    observations = relationship("LabObservation", back_populates="patient")

class LabObservation(Base):
    __tablename__ = 'lab_observations'
    
    observation_id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey('patients.patient_id'), nullable=False)
    lab_observation_code = Column(String(20))
    lab_observation_description = Column(String(255))
    lab_observation_value = Column(String(50))
    lab_observation_unit = Column(String(50))
    observation_datetime = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    
    # Relationship
    patient = relationship("Patient", back_populates="observations")

# Create tables
Base.metadata.create_all(engine)

TREND_DIRECTION_EPSILON = 0.1
AGE_GROUP_OPTIONS = ['20-39', '40-49', '50-64', '65+']

def get_db_session():
    return Session()


def parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def get_patient_clinic(patient):
    return getattr(patient, 'clinic', None)


def normalize_age_group(value):
    if value is None:
        return 'all'

    normalized = str(value).strip()
    return normalized if normalized in AGE_GROUP_OPTIONS else 'all'


def patient_matches_age_group(age, age_group):
    if age_group == 'all':
        return True
    if age is None:
        return False

    if age_group == '20-39':
        return 20 <= age <= 39
    if age_group == '40-49':
        return 40 <= age <= 49
    if age_group == '50-64':
        return 50 <= age <= 64
    if age_group == '65+':
        return age >= 65

    return True


def classify_trend_direction(values):
    if len(values) < 2:
        return 'single_visit'

    delta = values[-1] - values[0]
    if delta > TREND_DIRECTION_EPSILON:
        return 'increasing'
    if delta < -TREND_DIRECTION_EPSILON:
        return 'decreasing'
    return 'stable'


def compute_percentile(sorted_values, percentile):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]

    position = (len(sorted_values) - 1) * percentile
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))

    if lower_index == upper_index:
        return sorted_values[lower_index]

    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    weight = position - lower_index
    return lower_value + (upper_value - lower_value) * weight


def build_monthly_summary(patient_records):
    monthly_groups = defaultdict(list)

    for patient in patient_records:
        latest_by_month = {}
        for point in patient['trend']:
            month_key = point['date'][:7]
            latest_by_month[month_key] = point['value']

        for month_key, value in latest_by_month.items():
            monthly_groups[month_key].append(value)

    summary = []
    for month_key in sorted(monthly_groups.keys()):
        values = sorted(monthly_groups[month_key])
        summary.append({
            'month': month_key,
            'median': round(compute_percentile(values, 0.50), 2),
            'p25': round(compute_percentile(values, 0.25), 2),
            'p75': round(compute_percentile(values, 0.75), 2),
            'p10': round(compute_percentile(values, 0.10), 2),
            'p90': round(compute_percentile(values, 0.90), 2),
            'patient_count': len(values)
        })

    return summary


def build_latest_a1c_buckets(latest_values):
    bucket_definitions = [
        ('<7.0', lambda value: value < 7.0),
        ('7.0-8.9', lambda value: 7.0 <= value < 9.0),
        ('9.0-9.9', lambda value: 9.0 <= value < 10.0),
        ('10.0-11.9', lambda value: 10.0 <= value < 12.0),
        ('12.0+', lambda value: value >= 12.0),
    ]

    buckets = []
    total = len(latest_values)
    for label, predicate in bucket_definitions:
        count = sum(1 for value in latest_values if predicate(value))
        percent = round((count / total) * 100, 1) if total else 0
        buckets.append({
            'label': label,
            'count': count,
            'percent': percent
        })

    return buckets


def parse_a1c_value(value):
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = value.replace('>', '').replace('<', '').strip()
        cleaned_lower = cleaned.lower()
        if cleaned_lower in {'nan', 'inf', '-inf', 'infinity', '-infinity', 'none', ''}:
            return None
        try:
            parsed = float(cleaned)
        except ValueError:
            return None
    else:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None

    if math.isnan(parsed) or not math.isfinite(parsed):
        return None
    return parsed


@app.route('/')
def index():
    """Main search page"""
    return render_template('index.html')

@app.route('/api/search', methods=['GET'])
def search_patients():
    """Search patients by identifier, name components, or city"""
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 20, type=int)
    
    if not query or len(query) < 2:
        return jsonify({'error': 'Search query must be at least 2 characters'}), 400
    
    session = get_db_session()
    try:
        # Search patients by identifier or city
        patients = session.query(Patient).filter(
            (Patient.patient_identifier.ilike(f'%{query}%')) |
            (Patient.city.ilike(f'%{query}%'))
        ).limit(limit).all()
        
        results = []
        for patient in patients:
            results.append({
                'patient_id': patient.patient_id,
                'patient_identifier': patient.patient_identifier,
                'sex': patient.sex,
                'age_at_registration': patient.age_at_registration,
                'city': patient.city,
                'state': patient.state,
                'postal_code': patient.postal_code,
                'active': patient.active
            })
        
        return jsonify({'patients': results})
    finally:
        session.close()

@app.route('/api/patient/<int:patient_id>', methods=['GET'])
def get_patient_detail(patient_id):
    """Get detailed patient information"""
    session = get_db_session()
    try:
        patient = session.query(Patient).filter_by(patient_id=patient_id).first()
        
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404
        
        # Get A1c observations
        observations = session.query(LabObservation).filter(
            LabObservation.patient_id == patient_id,
            LabObservation.lab_observation_description.ilike('%A1c%') |
            LabObservation.lab_observation_description.ilike('%HEMOGLOBIN%')
        ).order_by(LabObservation.observation_datetime.asc()).all()
        
        patient_dict = {
            'patient_id': patient.patient_id,
            'patient_identifier': patient.patient_identifier,
            'sex': patient.sex,
            'age_at_registration': patient.age_at_registration,
            'city': patient.city,
            'state': patient.state,
            'postal_code': patient.postal_code,
            'most_recent_visit_date': patient.most_recent_visit_date.isoformat() if patient.most_recent_visit_date else None,
            'active': patient.active
        }
        
        observations_list = [{
            'observation_id': obs.observation_id,
            'lab_observation_description': obs.lab_observation_description,
            'lab_observation_value': obs.lab_observation_value,
            'lab_observation_unit': obs.lab_observation_unit,
            'observation_datetime': obs.observation_datetime.isoformat() if obs.observation_datetime else None
        } for obs in observations]
        
        return jsonify({
            'patient': patient_dict,
            'observations': observations_list
        })
    finally:
        session.close()

@app.route('/api/patient/<int:patient_id>/a1c-graph', methods=['GET'])
def get_a1c_graph(patient_id):
    """Generate A1c trend graph for patient"""
    session = get_db_session()
    try:
        patient = session.query(Patient).filter_by(patient_id=patient_id).first()
        
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404
        
        # Get A1c observations
        observations = session.query(LabObservation).filter(
            LabObservation.patient_id == patient_id,
            LabObservation.lab_observation_description.ilike('%A1c%') |
            LabObservation.lab_observation_description.ilike('%HEMOGLOBIN%')
        ).order_by(LabObservation.observation_datetime.asc()).all()
        
        if not observations:
            return jsonify({'error': 'No A1c data available for this patient'}), 404
        
        # Parse A1c values
        dates = []
        values = []
        
        for obs in observations:
            if obs.observation_datetime:
                dates.append(obs.observation_datetime)
                # Clean up the value (handle ranges like ">14.0")
                value_str = obs.lab_observation_value.replace('>', '').replace('<', '').strip()
                try:
                    values.append(float(value_str))
                except ValueError:
                    values.append(None)
        
        # Create Plotly graph
        fig = go.Figure()
        
        # Add A1c line
        fig.add_trace(go.Scatter(
            x=dates,
            y=values,
            mode='lines+markers',
            name='A1c Level',
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=8)
        ))
        
        # Add target range
        fig.add_hline(
            y=9,
            line_dash="dash",
            line_color="green",
            annotation_text="Target: 9%",
            annotation_position="right"
        )
        
        # For a single A1c entry, show month/year labels instead of exact times
        if len(dates) == 1:
            fig.update_xaxes(
                tickformat='%b %Y',
                tickmode='auto'
            )

        # Update layout
        fig.update_layout(
            title=f'A1c Trend for Patient {patient.patient_identifier}',
            xaxis_title='Date',
            yaxis_title='A1c Level (%)',
            hovermode='x unified',
            template='plotly_white',
            height=500,
            margin=dict(l=50, r=50, t=80, b=50)
        )
        
        graph_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        return jsonify({'graph': graph_json})
    
    finally:
        session.close()

@app.route('/patient/<int:patient_id>')
def patient_detail(patient_id):
    """Patient detail page"""
    return render_template('patient.html', patient_id=patient_id)

@app.route('/api/patients/all-active', methods=['GET'])
def get_all_active_patients():
    """Get all active patients for dashboard"""
    limit = request.args.get('limit', 100, type=int)
    
    session = get_db_session()
    try:
        # Get active patients with their latest A1c
        patients = session.query(Patient).filter(Patient.active == True).limit(limit).all()
        
        results = []
        for patient in patients:
            # Get latest A1c observation
            latest_a1c = session.query(LabObservation.lab_observation_value).filter(
                LabObservation.patient_id == patient.patient_id,
                LabObservation.lab_observation_description.ilike('%A1c%') |
                LabObservation.lab_observation_description.ilike('%HEMOGLOBIN%')
            ).order_by(LabObservation.observation_datetime.desc()).first()
            
            results.append({
                'patient_id': patient.patient_id,
                'patient_identifier': patient.patient_identifier,
                'age_at_registration': patient.age_at_registration,
                'city': patient.city,
                'state': patient.state,
                'latest_a1c': latest_a1c[0] if latest_a1c else None
            })
        
        return jsonify({'patients': results})
    finally:
        session.close()

@app.route('/stats')
def stats_page():
    """Overall clinic statistics page"""
    return render_template('stats.html')

@app.route('/api/stats', methods=['GET'])
def get_statistics():
    """Return clinician-oriented population summaries for A1c management"""
    threshold = request.args.get('threshold', 9.0, type=float)
    city = request.args.get('city', '', type=str).strip()
    age_group = normalize_age_group(request.args.get('age_group', 'all', type=str))
    clinic = request.args.get('clinic', '', type=str).strip()
    trend_direction = request.args.get('trend_direction', 'all', type=str).strip().lower()
    exclude_single_visit = parse_bool(request.args.get('exclude_single_visit'), default=False)

    if trend_direction not in {'all', 'increasing', 'decreasing'}:
        trend_direction = 'all'

    session = get_db_session()
    try:
        clinic_filter_supported = hasattr(Patient, 'clinic')

        city_options = [
            row[0] for row in session.query(Patient.city)
            .filter(Patient.active == True, Patient.city.isnot(None), Patient.city != '')
            .distinct()
            .order_by(Patient.city.asc())
            .all()
        ]

        clinic_options = []
        if clinic_filter_supported:
            clinic_column = getattr(Patient, 'clinic')
            clinic_options = [
                row[0] for row in session.query(clinic_column)
                .filter(Patient.active == True, clinic_column.isnot(None), clinic_column != '')
                .distinct()
                .order_by(clinic_column.asc())
                .all()
            ]

        patients_query = session.query(Patient).filter(Patient.active == True)
        if city and city != 'all':
            patients_query = patients_query.filter(Patient.city == city)

        patients = patients_query.all()
        def build_patient_dataset(selected_age_group):
            patient_records = []

            for patient in patients:
                if not patient_matches_age_group(patient.age_at_registration, selected_age_group):
                    continue

                observations = session.query(LabObservation).filter(
                    LabObservation.patient_id == patient.patient_id,
                    LabObservation.lab_observation_description.ilike('%A1c%') |
                    LabObservation.lab_observation_description.ilike('%HEMOGLOBIN%')
                ).order_by(LabObservation.observation_datetime.asc()).all()

                trend = []
                for obs in observations:
                    if obs.observation_datetime is None:
                        continue

                    value = parse_a1c_value(obs.lab_observation_value)
                    if value is None:
                        continue

                    trend.append({
                        'date': obs.observation_datetime.isoformat(),
                        'value': value
                    })

                visit_count = len(trend)
                latest_a1c = trend[-1]['value'] if trend else None
                trend_values = [point['value'] for point in trend]
                patient_trend_direction = classify_trend_direction(trend_values)
                patient_clinic = get_patient_clinic(patient)

                if clinic and clinic != 'all':
                    if not clinic_filter_supported or patient_clinic != clinic:
                        continue

                if exclude_single_visit and visit_count < 2:
                    continue

                if trend_direction != 'all' and patient_trend_direction != trend_direction:
                    continue

                patient_records.append({
                    'patient_id': patient.patient_id,
                    'patient_identifier': patient.patient_identifier,
                    'age_at_registration': patient.age_at_registration,
                    'city': patient.city,
                    'state': patient.state,
                    'clinic': patient_clinic,
                    'visit_count': visit_count,
                    'latest_a1c': latest_a1c,
                    'trend': trend,
                    'diabetic': latest_a1c is not None and latest_a1c >= threshold,
                    'trend_direction': patient_trend_direction
                })

            total_patients = len(patient_records)
            records_with_a1c = [p for p in patient_records if p['latest_a1c'] is not None]

            for patient in records_with_a1c:
                first_a1c = patient['trend'][0]['value']
                delta = round(patient['latest_a1c'] - first_a1c, 2)
                patient['first_a1c'] = first_a1c
                patient['delta_from_first'] = delta
                patient['latest_date'] = patient['trend'][-1]['date']

            diabetic_records = [p for p in records_with_a1c if p['diabetic']]
            non_diabetic_records = [p for p in records_with_a1c if not p['diabetic']]

            diabetic_records.sort(key=lambda p: p['latest_a1c'], reverse=True)
            non_diabetic_records.sort(key=lambda p: p['latest_a1c'], reverse=True)

            return {
                'total_patients': total_patients,
                'records_with_a1c': records_with_a1c,
                'sorted_records': diabetic_records + non_diabetic_records,
            }

        chart_dataset = build_patient_dataset(age_group)
        priority_dataset = build_patient_dataset('all')

        total_patients = chart_dataset['total_patients']
        records_with_a1c = chart_dataset['records_with_a1c']
        diabetic_count = sum(1 for p in records_with_a1c if p['diabetic'])
        count_with_a1c = len(records_with_a1c)
        latest_values = sorted(p['latest_a1c'] for p in records_with_a1c)
        sum_a1c = sum(latest_values)
        average_a1c = round(sum_a1c / count_with_a1c, 2) if count_with_a1c else None
        if average_a1c is not None and (math.isnan(average_a1c) or not math.isfinite(average_a1c)):
            average_a1c = None
        median_latest_a1c = round(compute_percentile(latest_values, 0.50), 2) if latest_values else None

        patient_records = records_with_a1c
        sorted_patients = chart_dataset['sorted_records']
        priority_patients = priority_dataset['sorted_records']

        improved_count = sum(1 for p in patient_records if p['trend_direction'] == 'decreasing')
        worsened_count = sum(1 for p in patient_records if p['trend_direction'] == 'increasing')
        stable_count = sum(1 for p in patient_records if p['trend_direction'] == 'stable')
        single_visit_count = sum(1 for p in patient_records if p['trend_direction'] == 'single_visit')
        above_threshold_percent = round((diabetic_count / count_with_a1c) * 100, 1) if count_with_a1c else 0
        improved_percent = round((improved_count / count_with_a1c) * 100, 1) if count_with_a1c else 0

        monthly_summary = build_monthly_summary(patient_records)
        latest_a1c_buckets = build_latest_a1c_buckets(latest_values)
        priority_patients.sort(
            key=lambda p: (
                p['latest_a1c'] < threshold,
                p['delta_from_first'] <= 0,
                -p['latest_a1c'],
                -p['delta_from_first'],
                -p['visit_count']
            )
        )

        return jsonify({
            'total_patients': total_patients,
            'diabetic_count': diabetic_count,
            'non_diabetic_count': len(patient_records) - diabetic_count,
            'average_a1c': average_a1c,
            'median_latest_a1c': median_latest_a1c,
            'threshold': threshold,
            'patients': sorted_patients,
            'monthly_summary': monthly_summary,
            'latest_a1c_buckets': latest_a1c_buckets,
            'trend_summary': {
                'improving': improved_count,
                'worsening': worsened_count,
                'stable': stable_count,
                'single_visit': single_visit_count
            },
            'priority_patients': priority_patients,
            'metrics': {
                'patients_with_a1c': count_with_a1c,
                'above_threshold_percent': above_threshold_percent,
                'improved_percent': improved_percent
            },
            'filters': {
                'city': city or 'all',
                'age_group': age_group,
                'clinic': clinic or 'all',
                'trend_direction': trend_direction,
                'exclude_single_visit': exclude_single_visit
            },
            'filter_options': {
                'age_groups': AGE_GROUP_OPTIONS,
                'cities': city_options,
                'clinics': clinic_options,
                'clinic_filter_supported': clinic_filter_supported
            }
        })
    finally:
        session.close()

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Server error'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
