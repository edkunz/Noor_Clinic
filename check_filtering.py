from app import Patient, LabObservation, get_db_session, parse_a1c_value

session = get_db_session()

try:
    threshold = 9.0
    patients = session.query(Patient).filter(Patient.active == True).all()
    
    diabetic_patients = []
    non_diabetic_patients = []
    
    for patient in patients:
        observations = session.query(LabObservation).filter(
            LabObservation.patient_id == patient.patient_id,
            LabObservation.lab_observation_description.ilike('%A1c%') |
            LabObservation.lab_observation_description.ilike('%HEMOGLOBIN%')
        ).order_by(LabObservation.observation_datetime.asc()).all()
        
        if observations:
            # Get latest A1c
            values = []
            for obs in observations:
                value = parse_a1c_value(obs.lab_observation_value)
                if value is not None:
                    values.append(value)
            
            if values:
                latest_a1c = values[-1]
                if latest_a1c >= threshold:
                    diabetic_patients.append({
                        'patient': patient.patient_identifier,
                        'latest_a1c': latest_a1c,
                        'num_readings': len(values),
                        'min_a1c': min(values),
                        'max_a1c': max(values)
                    })
                else:
                    non_diabetic_patients.append({
                        'patient': patient.patient_identifier,
                        'latest_a1c': latest_a1c,
                        'num_readings': len(values),
                        'min_a1c': min(values),
                        'max_a1c': max(values)
                    })
    
    print(f"\n=== PATIENT SUMMARY ===")
    print(f"Total Active Patients: {len(patients)}")
    print(f"Diabetic (latest A1c >= {threshold}%): {len(diabetic_patients)}")
    print(f"Non-Diabetic (latest A1c < {threshold}%): {len(non_diabetic_patients)}")
    
    print(f"\n=== NON-DIABETIC PATIENTS ===")
    if non_diabetic_patients:
        for p in non_diabetic_patients[:10]:
            print(f"  {p['patient']}: Latest={p['latest_a1c']:.1f}%, Range=[{p['min_a1c']:.1f}-{p['max_a1c']:.1f}%], Readings={p['num_readings']}")
        if len(non_diabetic_patients) > 10:
            print(f"  ... and {len(non_diabetic_patients) - 10} more")
    else:
        print("  None - all patients are diabetic!")
    
    print(f"\n=== DIABETIC PATIENTS (Sample) ===")
    for p in diabetic_patients[:5]:
        print(f"  {p['patient']}: Latest={p['latest_a1c']:.1f}%, Range=[{p['min_a1c']:.1f}-{p['max_a1c']:.1f}%], Readings={p['num_readings']}")
    if len(diabetic_patients) > 5:
        print(f"  ... and {len(diabetic_patients) - 5} more")

finally:
    session.close()
