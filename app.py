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

def get_db_session():
    return Session()


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

@app.route('/api/stats/filters', methods=['GET'])
def get_stats_filters():
    """Get available filter options for stats page"""
    session = get_db_session()
    try:
        # Get unique cities
        cities = session.query(Patient.city).filter(
            Patient.active == True,
            Patient.city.isnot(None)
        ).distinct().all()
        cities = sorted(list(set(city[0].strip() for city in cities if city[0] and city[0].strip())))
        
        # Hardcode sex options to Male and Female
        sexes = ['Male', 'Female']
        
        # Get date range
        date_range = session.query(
            func.min(Patient.most_recent_visit_date),
            func.max(Patient.most_recent_visit_date)
        ).filter(Patient.active == True).first()
        
        min_date = date_range[0].isoformat() if date_range[0] else None
        max_date = date_range[1].isoformat() if date_range[1] else None
        
        return jsonify({
            'cities': cities,
            'sexes': sexes,
            'date_range': {
                'min': min_date,
                'max': max_date
            }
        })
    finally:
        session.close()
@app.route('/api/stats', methods=['GET'])
def get_statistics():
    """Return aggregated patient statistics and recent A1c trends"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    sex_filter = request.args.get('sex')
    city_filter = request.args.get('city')
    age_group = request.args.get('age_group')
    a1c_range = request.args.get('a1c_range', 'all')
    
    session = get_db_session()
    try:
        # Build base query with filters
        query = session.query(Patient).filter(Patient.active == True)
        
        # Apply date range filter (based on most_recent_visit_date)
        if start_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                query = query.filter(Patient.most_recent_visit_date >= start)
            except ValueError:
                pass  # Invalid date format, ignore filter
        
        if end_date:
            try:
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
                query = query.filter(Patient.most_recent_visit_date <= end)
            except ValueError:
                pass  # Invalid date format, ignore filter
        
        # Apply sex filter
        if sex_filter and sex_filter != 'all':
            query = query.filter(Patient.sex.ilike(sex_filter))
        
        # Apply city filter
        if city_filter and city_filter != 'all':
            query = query.filter(Patient.city.ilike(f'%{city_filter.strip()}%'))
        
        # Apply age group filter
        if age_group and age_group != 'all':
            if age_group == '0-18':
                query = query.filter(Patient.age_at_registration.between(0, 18))
            elif age_group == '19-35':
                query = query.filter(Patient.age_at_registration.between(19, 35))
            elif age_group == '36-50':
                query = query.filter(Patient.age_at_registration.between(36, 50))
            elif age_group == '51-65':
                query = query.filter(Patient.age_at_registration.between(51, 65))
            elif age_group == '66+':
                query = query.filter(Patient.age_at_registration >= 66)
        
        patients = query.all()
        total_patients = len(patients)
        low_count = 0  # 0-5.5%
        normal_count = 0  # 5.5-9%
        high_count = 0  # 9%+
        sum_a1c = 0.0
        count_with_a1c = 0
        patient_records = []

        for patient in patients:
            observations = session.query(LabObservation).filter(
                LabObservation.patient_id == patient.patient_id,
                LabObservation.lab_observation_description.ilike('%A1c%') |
                LabObservation.lab_observation_description.ilike('%HEMOGLOBIN%')
            ).order_by(LabObservation.observation_datetime.asc()).all()

            trend = []
            latest_a1c = None
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

            if trend:
                latest_a1c = trend[-1]['value']
                sum_a1c += latest_a1c
                count_with_a1c += 1
                
                # Categorize by A1c range
                if latest_a1c < 5.5:
                    low_count += 1
                    a1c_category = 'low'
                elif latest_a1c < 9.0:
                    normal_count += 1
                    a1c_category = 'normal'
                else:
                    high_count += 1
                    a1c_category = 'high'
            else:
                a1c_category = 'no_data'

            patient_records.append({
                'patient_id': patient.patient_id,
                'patient_identifier': patient.patient_identifier,
                'city': patient.city,
                'state': patient.state,
                'sex': patient.sex,
                'age_at_registration': patient.age_at_registration,
                'latest_a1c': latest_a1c,
                'trend': trend,
                'a1c_category': a1c_category
            })
        
        # Apply A1c range filter
        if a1c_range != 'all':
            if a1c_range == 'low':
                patient_records = [p for p in patient_records if p['a1c_category'] == 'low']
            elif a1c_range == 'normal':
                patient_records = [p for p in patient_records if p['a1c_category'] == 'normal']
            elif a1c_range == 'high':
                patient_records = [p for p in patient_records if p['a1c_category'] == 'high']
        
        average_a1c = round(sum_a1c / count_with_a1c, 2) if count_with_a1c else None
        if average_a1c is not None and (math.isnan(average_a1c) or not math.isfinite(average_a1c)):
            average_a1c = None

        # Return mixed sample: patients from different categories to show the filtering difference
        # Take up to 40 from each category
        low_patients = [p for p in patient_records if p['a1c_category'] == 'low']
        normal_patients = [p for p in patient_records if p['a1c_category'] == 'normal']
        high_patients = [p for p in patient_records if p['a1c_category'] == 'high']
        
        display_patients = (low_patients[:40] + normal_patients[:40] + high_patients[:40])

        return jsonify({
            'total_patients': total_patients,
            'low_count': low_count,
            'normal_count': normal_count,
            'high_count': high_count,
            'average_a1c': average_a1c,
            'patients': display_patients
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
