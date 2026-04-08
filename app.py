from flask import Flask, render_template, request, jsonify
from sqlalchemy import create_engine, text, Column, Integer, String, Boolean, DateTime, Date, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func
import os
from dotenv import load_dotenv
import plotly
import plotly.graph_objects as go
import json
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
        
        # Add target range (7% is typical target for most diabetics)
        fig.add_hline(
            y=7,
            line_dash="dash",
            line_color="green",
            annotation_text="Target: 7%",
            annotation_position="right"
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

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Server error'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
