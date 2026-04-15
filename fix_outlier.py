from app import Patient, LabObservation, get_db_session
from sqlalchemy import text

# Get database session
session = get_db_session()

try:
    # Find the A1c observation with value 119
    outlier = session.query(LabObservation).filter(
        (LabObservation.lab_observation_value == '119') | 
        (LabObservation.lab_observation_value == 119),
        (LabObservation.lab_observation_description.ilike('%A1c%') |
         LabObservation.lab_observation_description.ilike('%HEMOGLOBIN%'))
    ).first()
    
    if outlier:
        # Get patient info for confirmation
        patient = session.query(Patient).filter_by(patient_id=outlier.patient_id).first()
        print(f"Found outlier:")
        print(f"  Patient: {patient.patient_identifier}")
        print(f"  Current A1c value: {outlier.lab_observation_value}")
        print(f"  Date: {outlier.observation_datetime}")
        print(f"  Description: {outlier.lab_observation_description}")
        
        # Update the value
        outlier.lab_observation_value = '19'
        session.commit()
        print(f"\n✓ Updated A1c value to: {outlier.lab_observation_value}")
    else:
        print("No outlier with A1c value of 119 found.")
        # List all A1c values for reference
        all_a1cs = session.query(LabObservation).filter(
            LabObservation.lab_observation_description.ilike('%A1c%') |
            LabObservation.lab_observation_description.ilike('%HEMOGLOBIN%')
        ).all()
        
        values = [float(obs.lab_observation_value.replace('>', '').replace('<', '').strip()) 
                  for obs in all_a1cs if obs.lab_observation_value]
        values.sort(reverse=True)
        print(f"\nTop A1c values in database:")
        for val in values[:10]:
            print(f"  {val}")

finally:
    session.close()
