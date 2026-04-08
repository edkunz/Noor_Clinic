import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from datetime import datetime
from app import Patient, LabObservation, Base

load_dotenv()

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'sqlite:///noor_clinic.db'
)

def import_data_from_csv():
    """Import patient data from SNFReport.csv into the database"""
    
    # Create engine and session
    engine = create_engine(DATABASE_URL, echo=False)
    
    # Create tables if they don't exist
    Base.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Read CSV file
        csv_file = 'SNFReport.csv'
        print(f"Reading data from {csv_file}...")
        df = pd.read_csv(csv_file)
        
        print(f"Loaded {len(df)} records from CSV")
        
        # Get unique patients
        patients_df = df[['Patient Identifier', 'Sex', 'Age', 'City', 'State', 'Postal Code', 
                          'Most Recent Visit Date', 'Active']].drop_duplicates(subset=['Patient Identifier'])
        
        print(f"Found {len(patients_df)} unique patients")
        
        # Insert patients
        print("Inserting patients...")
        for idx, row in patients_df.iterrows():
            try:
                # Check if patient exists
                existing = session.query(Patient).filter_by(
                    patient_identifier=str(row['Patient Identifier'])
                ).first()
                
                if not existing:
                    # Parse age (format: "56 yrs")
                    age = None
                    if pd.notna(row['Age']):
                        age_str = str(row['Age']).replace(' yrs', '').strip()
                        try:
                            age = int(age_str)
                        except:
                            age = None
                    
                    # Parse most recent visit date
                    visit_date = None
                    if pd.notna(row['Most Recent Visit Date']):
                        try:
                            visit_date = pd.to_datetime(row['Most Recent Visit Date']).date()
                        except:
                            visit_date = None
                    
                    patient = Patient(
                        patient_identifier=str(row['Patient Identifier']),
                        sex=row['Sex'] if pd.notna(row['Sex']) else None,
                        age_at_registration=age,
                        city=row['City'] if pd.notna(row['City']) else None,
                        state=row['State'] if pd.notna(row['State']) else None,
                        postal_code=row['Postal Code'] if pd.notna(row['Postal Code']) else None,
                        most_recent_visit_date=visit_date,
                        active=True if str(row['Active']).lower() == 'yes' else False,
                        fake=True if str(row.get('Fake', 'No')).lower() == 'yes' else False
                    )
                    session.add(patient)
                    session.commit()  # Commit each patient to get the ID
            except Exception as e:
                print(f"Error inserting patient {row['Patient Identifier']}: {e}")
                session.rollback()
        
        # Insert lab observations
        print("Inserting lab observations...")
        for idx, row in df.iterrows():
            try:
                # Get patient
                patient = session.query(Patient).filter_by(
                    patient_identifier=str(row['Patient Identifier'])
                ).first()
                
                if patient:
                    # Parse observation datetime
                    obs_datetime = None
                    if pd.notna(row['Lab Observation DateTime']):
                        try:
                            obs_datetime = pd.to_datetime(row['Lab Observation DateTime'])
                        except:
                            obs_datetime = None
                    
                    observation = LabObservation(
                        patient_id=patient.patient_id,
                        lab_observation_code=row['Lab Observation Code'] if pd.notna(row['Lab Observation Code']) else None,
                        lab_observation_description=row['Lab Observation Description'] if pd.notna(row['Lab Observation Description']) else None,
                        lab_observation_value=str(row['Lab Observation Value']),
                        lab_observation_unit=row['Lab Observation Unit of Measure'] if pd.notna(row['Lab Observation Unit of Measure']) else None,
                        observation_datetime=obs_datetime
                    )
                    session.add(observation)
            except Exception as e:
                print(f"Error inserting observation for patient {row['Patient Identifier']}: {e}")
                session.rollback()
        
        session.commit()
        print("Data import completed successfully!")
        
    except Exception as e:
        print(f"Import failed: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == '__main__':
    import_data_from_csv()
